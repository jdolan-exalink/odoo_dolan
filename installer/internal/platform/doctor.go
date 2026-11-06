package platform

import (
	"context"
	"fmt"
	"net"
	"net/http"
	"os"
	"os/exec"
	"runtime"
	"strings"
	"time"
)

type Check struct {
	Name   string `json:"name"`
	Status string `json:"status"`
	Detail string `json:"detail"`
}
type Report struct {
	OS           string  `json:"os"`
	Architecture string  `json:"architecture"`
	CPU          int     `json:"cpu"`
	Checks       []Check `json:"checks"`
}

func Doctor(ctx context.Context, port int) Report {
	r := Report{OS: runtime.GOOS, Architecture: runtime.GOARCH, CPU: runtime.NumCPU()}
	if runtime.GOOS == "linux" {
		cmd := exec.Command("id", "-u")
		b, err := cmd.Output()
		if err == nil && strings.TrimSpace(string(b)) == "0" {
			r.Checks = append(r.Checks, Check{"privilegios", "ok", "ejecución como root"})
		} else {
			r.Checks = append(r.Checks, Check{"privilegios", "warning", "para instalar paquetes y escribir en /opt, iniciá el CLI con sudo"})
		}
	}
	if runtime.GOOS == "linux" {
		if b, err := os.ReadFile("/etc/os-release"); err == nil {
			for _, line := range strings.Split(string(b), "\n") {
				if strings.HasPrefix(line, "PRETTY_NAME=") {
					r.OS = strings.Trim(strings.TrimPrefix(line, "PRETTY_NAME="), `"`)
					break
				}
			}
		}
	}
	checkCommand(&r, "git", "git", "--version")
	checkCommand(&r, "docker", "docker", "--version")
	if _, err := exec.LookPath("docker"); err == nil {
		checkCommand(&r, "docker compose", "docker", "compose", "version")
	} else {
		r.Checks = append(r.Checks, Check{"docker compose", "blocked", "Docker CLI no disponible"})
	}
	if _, err := exec.LookPath("bash"); err == nil {
		checkCommand(&r, "bash", "bash", "--version")
	} else {
		r.Checks = append(r.Checks, Check{"bash", "blocked", "Bash no está disponible en PATH"})
	}
	if port > 0 {
		listener, err := net.Listen("tcp", fmt.Sprintf("127.0.0.1:%d", port))
		if err != nil {
			r.Checks = append(r.Checks, Check{"puerto HTTP", "warning", fmt.Sprintf("127.0.0.1:%d ya está ocupado: %v", port, err)})
		} else {
			_ = listener.Close()
			r.Checks = append(r.Checks, Check{"puerto HTTP", "ok", fmt.Sprintf("127.0.0.1:%d disponible", port)})
		}
	}
	client := http.Client{Timeout: 4 * time.Second}
	req, _ := http.NewRequestWithContext(ctx, http.MethodHead, "https://github.com", nil)
	if req != nil {
		resp, err := client.Do(req)
		if err != nil {
			r.Checks = append(r.Checks, Check{"GitHub", "warning", "sin conexión HTTPS: " + err.Error()})
		} else {
			_ = resp.Body.Close()
			r.Checks = append(r.Checks, Check{"GitHub", "ok", "HTTPS responde"})
		}
	}
	return r
}

func checkCommand(r *Report, label, name string, args ...string) {
	path, err := exec.LookPath(name)
	if err != nil {
		r.Checks = append(r.Checks, Check{label, "blocked", "no está instalado"})
		return
	}
	cmd := exec.Command(name, args...)
	b, err := cmd.CombinedOutput()
	detail := strings.TrimSpace(string(b))
	if len(detail) > 180 {
		detail = detail[:180]
	}
	if err != nil {
		r.Checks = append(r.Checks, Check{label, "blocked", fmt.Sprintf("%s: %s", path, detail)})
		return
	}
	if label == "docker compose" {
		cmd = exec.Command("docker", "info", "--format", "{{.ServerVersion}}")
		b, err = cmd.CombinedOutput()
		if err != nil {
			r.Checks = append(r.Checks, Check{label, "warning", "CLI disponible, daemon sin responder"})
			return
		}
		detail = "Docker Engine " + strings.TrimSpace(string(b))
	}
	r.Checks = append(r.Checks, Check{label, "ok", detail})
}

func Ready(r Report) bool {
	for _, c := range r.Checks {
		if c.Status == "blocked" {
			return false
		}
	}
	return true
}
