package engine

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"strings"
	"time"

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
		return Deployment{}, fmt.Errorf("no existe un despliegue Compose llamado %q en %s", name, root)
	}
	m, err := state.Read(path)
	return Deployment{Name: name, Path: path, Manifest: m, Managed: err == nil}, nil
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
