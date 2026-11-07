package engine

import (
	"bufio"
	"context"
	"errors"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/security"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/state"
)

type Event struct {
	Line string
	Err  error
	Done bool
}
type LogFunc func(Event)

type Runner struct{ RepoRoot string }

func (r Runner) Plan(c core.Config) ([]string, error) {
	if _, err := os.Stat(filepath.Join(r.RepoRoot, "crear_odoo20.sh")); err != nil {
		return nil, fmt.Errorf("no encuentro crear_odoo20.sh en %s", r.RepoRoot)
	}
	c.Normalize()
	// Planning is intentionally safe without secrets, so `--dry-run` can validate
	// every non-secret field without forcing users to put a password in a flag.
	validationConfig := c
	if validationConfig.AdminPassword == "" {
		validationConfig.AdminPassword = "dry-run-only-placeholder"
	}
	if err := validationConfig.Validate(true); err != nil {
		return nil, err
	}
	args := []string{"--non-interactive", "--deploy", "--name", c.DeploymentPath(), "--port", fmt.Sprint(c.Port), "--callback-port", fmt.Sprint(c.CallbackPort), "--profile", core.LegacyProfileName(c.Profile), "--company", c.Company, "--company-short", c.ProjectName, "--cuit", c.CUIT, "--address", c.Address, "--city", c.City, "--responsibility", c.Responsibility, "--billing-pos", fmt.Sprint(c.BillingPOS), "--pos-pos", fmt.Sprint(c.POSPOS), "--admin-email", c.AdminEmail, "--admin-name", c.AdminName, "--init-db", c.InitDB}
	if c.DemoMode == core.DemoDolan {
		args = append(args, "--demo-mode", "dolan")
	} else if c.DemoData || c.DemoMode == core.DemoOdoo {
		args = append(args, "--demo-data")
	}
	if len(c.Modules) > 0 {
		args = append(args, "--modules", strings.Join(c.Modules, ","))
	}
	return args, nil
}

func (r Runner) Install(ctx context.Context, c core.Config, onLog LogFunc) error {
	if runtime.GOOS != "linux" {
		return errors.New("la instalación local Linux es el único backend habilitado en este MVP; en Windows usá WSL2 o el instalador PowerShell existente")
	}
	args, err := r.Plan(c)
	if err != nil {
		return err
	}
	if c.AdminPassword == "" {
		return errors.New("falta la contraseña inicial del administrador")
	}
	if strings.ContainsRune(c.AdminPassword, '\n') || strings.ContainsRune(c.AdminPassword, '\r') {
		return errors.New("la contraseña no puede contener saltos de línea")
	}
	if strings.ContainsRune(c.MasterPassword, '\n') || strings.ContainsRune(c.MasterPassword, '\r') {
		return errors.New("la contraseña maestra no puede contener saltos de línea")
	}
	uid, err := exec.Command("id", "-u").Output()
	if err != nil || strings.TrimSpace(string(uid)) != "0" {
		return errors.New("la preparación instala paquetes y activa Docker; ejecutá `sudo dolan-installer install` después de revisar el plan")
	}
	if err := os.MkdirAll(c.ProjectRoot, 0750); err != nil {
		return fmt.Errorf("no se pudo preparar la ruta de instalaciones: %w", err)
	}
	logPath := filepath.Join(c.ProjectRoot, c.ProjectName+"-install-"+time.Now().Format("20060102-150405")+".log")
	logFile, err := os.OpenFile(logPath, os.O_CREATE|os.O_EXCL|os.O_WRONLY, 0600)
	if err != nil {
		return fmt.Errorf("no se pudo crear el log privado: %w", err)
	}
	defer logFile.Close()
	secrets := []string{c.AdminPassword, c.MasterPassword}
	prepare := exec.CommandContext(ctx, "bash", filepath.Join(r.RepoRoot, "bootstrap.sh"), "--prepare-only")
	prepare.Dir = r.RepoRoot
	if err := streamCommand(prepare, logFile, onLog, secrets); err != nil {
		return fmt.Errorf("no se pudieron preparar los paquetes del host: %w (log: %s)", err, logPath)
	}
	if err := resetExistingDeployment(ctx, c, logFile, onLog, secrets); err != nil {
		return fmt.Errorf("no se pudo preparar el destino: %w (log: %s)", err, logPath)
	}
	install := exec.CommandContext(ctx, "bash", append([]string{filepath.Join(r.RepoRoot, "crear_odoo20.sh")}, args...)...)
	install.Dir = r.RepoRoot
	install.Env = replaceEnv(os.Environ(), map[string]string{
		"DOLAN_ADMIN_LOGIN_PASSWORD": c.AdminPassword,
		"DOLAN_DB_MASTER_PASSWORD":   c.MasterPassword,
	})
	if err := streamCommand(install, logFile, onLog, secrets); err != nil {
		return fmt.Errorf("el instalador terminó con error: %w (log: %s)", err, logPath)
	}
	if _, err := os.Stat(filepath.Join(c.DeploymentPath(), "docker-compose.yml")); err != nil {
		return fmt.Errorf("el motor terminó pero no se encontró docker-compose.yml en el destino: %w", err)
	}
	m := state.Manifest{
		Name:         c.ProjectName,
		Deployment:   string(c.Target),
		VMID:         c.LXC.VMID,
		OdooVersion:  "20.0",
		DolanVersion: "20.0.1",
		Company:      c.Company,
		Profile:      string(core.CanonicalProfile(c.Profile)),
		Modules:      c.Modules,
		DemoData:     c.DemoData || c.DemoMode != core.DemoNone,
		DemoMode:     string(c.DemoMode),
		Database:     c.InitDB,
		Port:         c.Port,
		CallbackPort: c.CallbackPort,
		ProjectPath:  c.DeploymentPath(),
		CreatedAt:    time.Now().UTC(),
		Services:     []string{"odoo", "db", "waha", "whisper"},
	}
	if err := state.Write(c.DeploymentPath(), m); err != nil {
		return fmt.Errorf("despliegue completado, pero no se pudo guardar el manifiesto: %w", err)
	}
	if onLog != nil {
		onLog(Event{Line: fmt.Sprintf("Manifiesto guardado en %s", filepath.Join(c.DeploymentPath(), state.ManifestName))})
	}
	return nil
}

func resetExistingDeployment(ctx context.Context, c core.Config, logFile *os.File, onLog LogFunc, secrets []string) error {
	target := c.DeploymentPath()
	info, err := os.Lstat(target)
	if os.IsNotExist(err) {
		if c.ResetExistingName != "" {
			return fmt.Errorf("se solicitó reemplazar %q pero no existe en %s", c.ResetExistingName, target)
		}
		return nil
	}
	if err != nil {
		return err
	}
	if c.ResetExistingName == "" {
		return fmt.Errorf("el destino ya existe; no se sobrescribe sin --reset-existing: %s", target)
	}
	if c.ResetExistingName != c.ProjectName {
		return errors.New("el nombre a reemplazar debe coincidir exactamente con el nombre del proyecto")
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return errors.New("el destino existente debe ser un directorio real, no un archivo ni un enlace simbólico")
	}
	root, err := filepath.EvalSymlinks(c.ProjectRoot)
	if err != nil {
		return fmt.Errorf("resolver la ruta base: %w", err)
	}
	if filepath.Clean(root) == string(os.PathSeparator) {
		return errors.New("por seguridad no se puede reemplazar un deployment desde la raíz del sistema")
	}
	realTarget, err := filepath.EvalSymlinks(target)
	if err != nil {
		return fmt.Errorf("resolver el deployment existente: %w", err)
	}
	rel, err := filepath.Rel(root, realTarget)
	if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return errors.New("el deployment a reemplazar debe quedar dentro de la ruta base y no puede ser la ruta base misma")
	}
	composeFile := filepath.Join(realTarget, "docker-compose.yml")
	if st, err := os.Stat(composeFile); err != nil || !st.Mode().IsRegular() {
		return errors.New("no encontré un docker-compose.yml regular en el deployment; no voy a borrarlo")
	}
	if onLog != nil {
		onLog(Event{Line: fmt.Sprintf("Eliminando deployment confirmado %s y sus volúmenes/imágenes locales", realTarget)})
	}
	stop := exec.CommandContext(ctx, "docker", "compose", "down", "--volumes", "--rmi", "local", "--remove-orphans")
	stop.Dir = realTarget
	if err := streamCommand(stop, logFile, onLog, secrets); err != nil {
		return fmt.Errorf("docker compose down: %w", err)
	}
	if err := os.RemoveAll(realTarget); err != nil {
		return fmt.Errorf("borrar la carpeta del deployment y sus datos locales: %w", err)
	}
	return nil
}

func streamCommand(cmd *exec.Cmd, logFile *os.File, onLog LogFunc, secrets []string) error {
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return err
	}
	stderr, err := cmd.StderrPipe()
	if err != nil {
		return err
	}
	if err := cmd.Start(); err != nil {
		return err
	}
	var writers sync.WaitGroup
	lines := make(chan string, 64)
	scan := func(reader io.Reader) {
		defer writers.Done()
		scanner := bufio.NewScanner(reader)
		scanner.Buffer(make([]byte, 4096), 1024*1024)
		for scanner.Scan() {
			lines <- scanner.Text()
		}
		if err := scanner.Err(); err != nil {
			lines <- "[Aviso] No pude leer una línea del log: " + err.Error()
		}
	}
	writers.Add(2)
	go scan(stdout)
	go scan(stderr)
	go func() { writers.Wait(); close(lines) }()
	for line := range lines {
		clean := security.Redact(line, secrets...)
		_, _ = fmt.Fprintln(logFile, clean)
		if onLog != nil {
			onLog(Event{Line: clean})
		}
	}
	return cmd.Wait()
}

func replaceEnv(in []string, set map[string]string) []string {
	out := make([]string, 0, len(in)+len(set))
	for _, item := range in {
		key, _, ok := strings.Cut(item, "=")
		if _, replace := set[key]; !ok || !replace {
			out = append(out, item)
		}
	}
	for key, value := range set {
		if value != "" {
			out = append(out, key+"="+value)
		}
	}
	return out
}
