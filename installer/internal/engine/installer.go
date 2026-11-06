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
	args := []string{"--non-interactive", "--deploy", "--name", c.DeploymentPath(), "--port", fmt.Sprint(c.Port), "--callback-port", fmt.Sprint(c.CallbackPort), "--profile", string(c.Profile), "--company", c.Company, "--company-short", c.ProjectName, "--cuit", c.CUIT, "--address", c.Address, "--city", c.City, "--responsibility", c.Responsibility, "--billing-pos", fmt.Sprint(c.BillingPOS), "--pos-pos", fmt.Sprint(c.POSPOS), "--admin-email", c.AdminEmail, "--admin-name", c.AdminName, "--init-db", c.InitDB}
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
	if _, err := os.Stat(c.DeploymentPath()); err == nil {
		return fmt.Errorf("el destino ya existe; no voy a sobrescribirlo: %s", c.DeploymentPath())
	} else if !os.IsNotExist(err) {
		return err
	}
	logPath := filepath.Join(c.ProjectRoot, c.ProjectName+"-install.log")
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
	m := state.Manifest{Name: c.ProjectName, Company: c.Company, Profile: string(c.Profile), Database: c.InitDB, Port: c.Port, ProjectPath: c.DeploymentPath(), CreatedAt: time.Now().UTC(), Services: []string{"odoo", "db", "waha", "whisper"}}
	if err := state.Write(c.DeploymentPath(), m); err != nil {
		return fmt.Errorf("despliegue completado, pero no se pudo guardar el manifiesto: %w", err)
	}
	if onLog != nil {
		onLog(Event{Line: fmt.Sprintf("Manifiesto guardado en %s", filepath.Join(c.DeploymentPath(), state.ManifestName))})
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
