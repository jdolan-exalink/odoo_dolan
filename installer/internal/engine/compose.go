package engine

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/packages"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/security"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/state"
)

type Deployment struct {
	Name, Path string
	Manifest   state.Manifest
	Managed    bool
}
type Container struct {
	Name    string `json:"Name"`
	Service string `json:"Service"`
	State   string `json:"State"`
	Status  string `json:"Status"`
}
type Status struct {
	Deployment Deployment
	Containers []Container
	HTTP       string
	HTTPStatus string
	Error      string
}

func Discover(root string) ([]Deployment, error) {
	entries, err := os.ReadDir(root)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var out []Deployment
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		path := filepath.Join(root, entry.Name())
		if _, err := os.Stat(filepath.Join(path, "docker-compose.yml")); err != nil {
			continue
		}
		m, mErr := state.Read(path)
		out = append(out, Deployment{Name: entry.Name(), Path: path, Manifest: m, Managed: mErr == nil})
	}
	return out, nil
}

func Resolve(root, name string) (Deployment, error) {
	if filepath.IsAbs(name) {
		cleanRoot, _ := filepath.Abs(root)
		cleanName, _ := filepath.Abs(name)
		rel, err := filepath.Rel(cleanRoot, cleanName)
		if err != nil || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
			return Deployment{}, errors.New("la ruta de instalación debe quedar dentro de la ruta base configurada")
		}
		name = rel
	}
	if name == "" || name == "." || strings.ContainsAny(name, `/\`) {
		return Deployment{}, errors.New("indicá un nombre de despliegue simple, sin rutas")
	}
	path := filepath.Join(root, name)
	if _, err := os.Stat(filepath.Join(path, "docker-compose.yml")); err != nil {
		// Also try matching by VMID or InstallationID in discovered deployments
		if items, dErr := Discover(root); dErr == nil {
			for _, item := range items {
				if fmt.Sprint(item.Manifest.VMID) == name || item.Manifest.InstallationID == name {
					return item, nil
				}
			}
		}
		return Deployment{}, fmt.Errorf("no existe un despliegue llamado %q en %s", name, root)
	}
	m, err := state.Read(path)
	return Deployment{Name: name, Path: path, Manifest: m, Managed: err == nil}, nil
}

// Adopt validates an unmanaged installation directory and writes a dolan-installation.json manifest
// without reinstalling or altering data, only after explicit user consent.
func Adopt(root, name, company, profile, database string, port int) (Deployment, error) {
	d, err := Resolve(root, name)
	if err != nil {
		return Deployment{}, err
	}
	if d.Managed {
		return d, nil
	}
	now := time.Now().UTC()
	if company == "" {
		company = d.Name
	}
	if profile == "" {
		profile = "comercio"
	}
	if database == "" {
		database = "odoo_" + d.Name
	}
	if port == 0 {
		port = 8070
	}
	m := state.Manifest{
		Name:         d.Name,
		Company:      company,
		Deployment:   "docker",
		OdooVersion:  "20.0",
		DolanVersion: "20.0.1",
		Profile:      profile,
		Database:     database,
		Port:         port,
		ProjectPath:  d.Path,
		CreatedAt:    now,
		AdoptedAt:    &now,
		Services:     []string{"odoo", "db", "waha", "whisper"},
	}
	if err := state.Write(d.Path, m); err != nil {
		return Deployment{}, err
	}
	d.Manifest = m
	d.Managed = true
	return d, nil
}

func GetStatus(ctx context.Context, d Deployment) Status {
	s := Status{Deployment: d}
	cmd := exec.CommandContext(ctx, "docker", "compose", "ps", "--all", "--format", "json")
	cmd.Dir = d.Path
	b, err := cmd.Output()
	if err != nil {
		s.Error = err.Error()
		return s
	}
	for _, line := range strings.Split(strings.TrimSpace(string(b)), "\n") {
		if strings.TrimSpace(line) == "" {
			continue
		}
		var c Container
		if json.Unmarshal([]byte(line), &c) == nil {
			s.Containers = append(s.Containers, c)
		}
	}
	if d.Manifest.Port > 0 {
		s.HTTP = fmt.Sprintf("http://127.0.0.1:%d/web/login", d.Manifest.Port)
		client := http.Client{Timeout: 3 * time.Second, CheckRedirect: func(_ *http.Request, _ []*http.Request) error { return http.ErrUseLastResponse }}
		resp, err := client.Get(s.HTTP)
		if err != nil {
			s.HTTPStatus = "no responde"
		} else {
			s.HTTPStatus = resp.Status
			resp.Body.Close()
		}
	}
	return s
}

func ReadLogs(ctx context.Context, d Deployment, tail int) ([]string, error) {
	if tail < 1 || tail > 5000 {
		return nil, errors.New("--tail debe estar entre 1 y 5000")
	}
	cmd := exec.CommandContext(ctx, "docker", "compose", "logs", "--no-color", "--tail", fmt.Sprint(tail))
	cmd.Dir = d.Path
	b, err := cmd.CombinedOutput()
	if err != nil {
		return nil, fmt.Errorf("docker compose logs: %w: %s", err, strings.TrimSpace(string(b)))
	}
	secrets := envSecrets(filepath.Join(d.Path, ".env"))
	var out []string
	for _, line := range strings.Split(strings.TrimRight(string(b), "\r\n"), "\n") {
		out = append(out, security.Redact(line, secrets...))
	}
	return out, nil
}

var sensitiveEnv = regexp.MustCompile(`(?i)(password|passwd|secret|token|api[_-]?key)`)

func envSecrets(path string) []string {
	b, err := os.ReadFile(path)
	if err != nil {
		return nil
	}
	var secrets []string
	for _, line := range strings.Split(string(b), "\n") {
		key, value, ok := strings.Cut(strings.TrimSpace(line), "=")
		if ok && sensitiveEnv.MatchString(key) {
			value = strings.Trim(value, `"'`)
			if value != "" {
				secrets = append(secrets, value)
			}
		}
	}
	return secrets
}

// DeleteDeployment stops and removes containers, volumes, local images, and the deployment directory
// after validating that the target is a valid deployment inside root.
func DeleteDeployment(ctx context.Context, root, name string) (Deployment, error) {
	d, err := Resolve(root, name)
	if err != nil {
		return Deployment{}, err
	}
	info, err := os.Lstat(d.Path)
	if err != nil {
		return Deployment{}, err
	}
	if !info.IsDir() || info.Mode()&os.ModeSymlink != 0 {
		return Deployment{}, errors.New("el destino a borrar debe ser un directorio real, no un archivo ni un enlace simbólico")
	}
	realRoot, err := filepath.EvalSymlinks(root)
	if err != nil {
		return Deployment{}, fmt.Errorf("resolver la ruta base: %w", err)
	}
	if filepath.Clean(realRoot) == string(os.PathSeparator) {
		return Deployment{}, errors.New("por seguridad no se puede borrar un deployment desde la raíz del sistema")
	}
	realTarget, err := filepath.EvalSymlinks(d.Path)
	if err != nil {
		return Deployment{}, fmt.Errorf("resolver el deployment: %w", err)
	}
	rel, err := filepath.Rel(realRoot, realTarget)
	if err != nil || rel == "." || rel == ".." || strings.HasPrefix(rel, ".."+string(os.PathSeparator)) {
		return Deployment{}, errors.New("el deployment a borrar debe quedar dentro de la ruta base")
	}
	composeFile := filepath.Join(realTarget, "docker-compose.yml")
	if st, err := os.Stat(composeFile); err != nil || !st.Mode().IsRegular() {
		return Deployment{}, errors.New("no encontré un docker-compose.yml regular en el deployment")
	}
	if _, lookErr := exec.LookPath("docker"); lookErr == nil {
		stop := exec.CommandContext(ctx, "docker", "compose", "down", "--volumes", "--rmi", "local", "--remove-orphans")
		stop.Dir = realTarget
		_ = stop.Run()
	}
	if err := os.RemoveAll(realTarget); err != nil {
		return Deployment{}, fmt.Errorf("borrar carpeta del deployment: %w", err)
	}
	return d, nil
}

type ApplyPackageResult struct {
	Installation     string              `json:"installation"`
	ManifestUpdated  bool                `json:"manifest_updated"`
	EnvUpdated       bool                `json:"env_updated"`
	AddonsSynced     int                 `json:"addons_synced"`
	ContainerUpdated bool                `json:"container_updated"`
	Plan             packages.ChangePlan `json:"plan"`
	Message          string              `json:"message"`
}

// ApplyPackagePlan persists the updated profile and modules in the deployment manifest,
// syncs any newly required addons from repoRoot/addons into the deployment's addons directory,
// updates .env if present, and installs new modules in the running Odoo container if active.
func ApplyPackagePlan(ctx context.Context, repoRoot string, d Deployment, plan packages.ChangePlan) (ApplyPackageResult, error) {
	res := ApplyPackageResult{
		Installation: d.Name,
		Plan:         plan,
	}
	d.Manifest.Profile = string(plan.TargetProfile)
	d.Manifest.Modules = plan.TargetModules
	d.Manifest.UpdatedAt = time.Now().UTC()
	if d.Manifest.Name == "" {
		d.Manifest.Name = d.Name
	}
	if d.Manifest.OdooVersion == "" {
		d.Manifest.OdooVersion = "20.0"
	}
	if d.Manifest.DolanVersion == "" {
		d.Manifest.DolanVersion = "20.0.1"
	}
	if d.Manifest.Deployment == "" {
		d.Manifest.Deployment = "docker"
	}
	if err := state.Write(d.Path, d.Manifest); err != nil {
		return res, err
	}
	res.ManifestUpdated = true

	envPath := filepath.Join(d.Path, ".env")
	if _, err := os.Stat(envPath); err == nil {
		if updateEnvFile(envPath, map[string]string{
			"DOLAN_PROFILE": string(plan.TargetProfile),
			"DOLAN_MODULES": strings.Join(plan.TargetModules, ","),
		}) == nil {
			res.EnvUpdated = true
		}
	}

	destAddonsRoot := filepath.Join(d.Path, "addons")
	if repoRoot != "" {
		if st, err := os.Stat(destAddonsRoot); err == nil && st.IsDir() {
			for _, mod := range plan.TargetModules {
				srcMod := filepath.Join(repoRoot, "addons", mod)
				dstMod := filepath.Join(destAddonsRoot, mod)
				if _, sErr := os.Stat(srcMod); sErr == nil {
					if copyAddonDir(srcMod, dstMod) == nil {
						res.AddonsSynced++
					}
				}
			}
		}
	}

	if len(plan.ToInstall) > 0 {
		st := GetStatus(ctx, d)
		odooRunning := false
		for _, c := range st.Containers {
			if (c.Service == "odoo" || strings.Contains(c.Name, "odoo")) && c.State == "running" {
				odooRunning = true
				break
			}
		}
		if odooRunning {
			dbName := d.Manifest.Database
			if dbName == "" {
				dbName = "odoo_" + d.Name
			}
			modsCSV := strings.Join(append([]string{}, plan.ToInstall...), ",")
			if len(plan.OdooSystemAppsToAdd) > 0 {
				modsCSV = strings.Join(append(append([]string{}, plan.OdooSystemAppsToAdd...), plan.ToInstall...), ",")
			}
			cmd := exec.CommandContext(ctx, "docker", "compose", "exec", "-T", "odoo",
				"/opt/odoo/odoo-server/odoo-bin", "-c", "/etc/odoo/odoo.conf",
				"-d", dbName, "-i", modsCSV, "--stop-after-init", "--no-http")
			cmd.Dir = d.Path
			if out, err := cmd.CombinedOutput(); err != nil {
				res.Message = fmt.Sprintf("Manifiesto actualizado, pero odoo-bin devolvió error al inicializar módulos: %v (%s)", err, strings.TrimSpace(string(out)))
				return res, nil
			}
			restart := exec.CommandContext(ctx, "docker", "compose", "restart", "odoo")
			restart.Dir = d.Path
			_ = restart.Run()
			res.ContainerUpdated = true
			res.Message = fmt.Sprintf("Perfil %s y +%d módulos instalados y activos en %s", plan.TargetProfile, len(plan.ToInstall), d.Name)
			return res, nil
		}
	}

	res.Message = fmt.Sprintf("Perfil %s y módulos (%d en total, +%d nuevos) guardados en %s", plan.TargetProfile, len(plan.TargetModules), len(plan.ToInstall), d.Name)
	return res, nil
}

func updateEnvFile(path string, updates map[string]string) error {
	b, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	lines := strings.Split(string(b), "\n")
	seen := make(map[string]bool)
	for i, line := range lines {
		key, _, ok := strings.Cut(strings.TrimSpace(line), "=")
		if ok {
			if newVal, exists := updates[key]; exists {
				lines[i] = key + "=" + newVal
				seen[key] = true
			}
		}
	}
	for k, v := range updates {
		if !seen[k] {
			lines = append(lines, k+"="+v)
		}
	}
	return os.WriteFile(path, []byte(strings.Join(lines, "\n")), 0600)
}

func copyAddonDir(src, dst string) error {
	return filepath.Walk(src, func(path string, info os.FileInfo, err error) error {
		if err != nil {
			return err
		}
		rel, err := filepath.Rel(src, path)
		if err != nil {
			return err
		}
		target := filepath.Join(dst, rel)
		if info.IsDir() {
			return os.MkdirAll(target, 0755)
		}
		in, err := os.Open(path)
		if err != nil {
			return err
		}
		defer in.Close()
		out, err := os.OpenFile(target, os.O_CREATE|os.O_TRUNC|os.O_WRONLY, info.Mode()&0777)
		if err != nil {
			return err
		}
		defer out.Close()
		_, err = io.Copy(out, in)
		return err
	})
}
