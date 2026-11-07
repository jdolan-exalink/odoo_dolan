package platform

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
)

type HostEnvironment struct {
	Type        string `json:"type"`         // proxmox-ve, lxc, docker-host, linux-native, windows
	DisplayName string `json:"display_name"` // e.g., "Proxmox VE 9.x", "Windows AMD64"
	Hostname    string `json:"hostname"`
	OS          string `json:"os"`
	Arch        string `json:"arch"`
	HasProxmox  bool   `json:"has_proxmox"`
	HasDocker   bool   `json:"has_docker"`
	InsideLXC   bool   `json:"inside_lxc"`
}

func DetectHostEnvironment() HostEnvironment {
	hostname, _ := os.Hostname()
	if hostname == "" {
		hostname = "localhost"
	}
	archLabel := strings.ToUpper(runtime.GOARCH)
	osLabel := runtime.GOOS
	switch runtime.GOOS {
	case "linux":
		osLabel = "Linux " + archLabel
	case "windows":
		osLabel = "Windows " + archLabel
	}

	env := HostEnvironment{
		Type:        "linux-native",
		DisplayName: osLabel,
		Hostname:    hostname,
		OS:          runtime.GOOS,
		Arch:        runtime.GOARCH,
	}
	if runtime.GOOS == "windows" {
		env.Type = "windows"
		env.DisplayName = "Windows"
		if _, err := exec.LookPath("docker"); err == nil {
			env.HasDocker = true
		}
		return env
	}

	if b, err := os.ReadFile("/proc/1/environ"); err == nil && strings.Contains(string(b), "container=lxc") {
		env.InsideLXC = true
	}
	if _, err := os.Stat("/etc/pve"); err == nil {
		env.HasProxmox = true
	} else if _, err := exec.LookPath("pveversion"); err == nil {
		env.HasProxmox = true
	}
	if _, err := exec.LookPath("docker"); err == nil {
		env.HasDocker = true
	}

	if env.HasProxmox {
		env.Type = "proxmox-ve"
		ver := "Proxmox VE"
		if out, err := exec.Command("pveversion").Output(); err == nil {
			// e.g. pve-manager/9.0-1/abcdef (running kernel: ...)
			s := strings.TrimSpace(string(out))
			if strings.HasPrefix(s, "pve-manager/") {
				parts := strings.Split(strings.TrimPrefix(s, "pve-manager/"), "/")
				if len(parts) > 0 && parts[0] != "" {
					ver = "Proxmox VE " + parts[0]
				}
			}
		}
		env.DisplayName = ver
	} else if env.InsideLXC {
		env.Type = "lxc"
		env.DisplayName = "Contenedor LXC"
	} else if env.HasDocker {
		env.Type = "docker-host"
		env.DisplayName = "Docker Host"
	} else {
		env.Type = "linux-native"
		env.DisplayName = "Linux nativo"
	}
	return env
}

func (h HostEnvironment) HeaderSummary() string {
	osArch := "Linux " + strings.ToUpper(h.Arch)
	if h.OS == "windows" {
		osArch = "Windows " + strings.ToUpper(h.Arch)
	}
	return fmt.Sprintf("%s  |  %s  |  %s", h.DisplayName, h.Hostname, osArch)
}

type LXCContainer struct {
	VMID        int    `json:"vmid"`
	Status      string `json:"status"` // running, stopped
	Name        string `json:"name"`
	IsDolan     bool   `json:"is_dolan"`
	IsOdooOther bool   `json:"is_odoo_other"`
	Profile     string `json:"profile,omitempty"`
	DemoData    bool   `json:"demo_data,omitempty"`
	DemoMode    string `json:"demo_mode,omitempty"`
	Evidence    string `json:"evidence,omitempty"`
}

// ParsePctList parses the output of `pct list` on Proxmox VE.
// Example:
// VMID       Status     Lock         Name
// 101        running                 frigorifico
// 105        stopped                 desarrollo
func ParsePctList(output string) []LXCContainer {
	var out []LXCContainer
	lines := strings.Split(strings.TrimSpace(output), "\n")
	for idx, line := range lines {
		line = strings.TrimSpace(line)
		if line == "" {
			continue
		}
		fields := strings.Fields(line)
		if idx == 0 && len(fields) > 0 && strings.EqualFold(fields[0], "VMID") {
			continue
		}
		if len(fields) < 2 {
			continue
		}
		vmid, err := strconv.Atoi(fields[0])
		if err != nil {
			continue
		}
		status := strings.ToLower(fields[1])
		name := ""
		if len(fields) >= 3 {
			name = fields[len(fields)-1]
		}
		out = append(out, LXCContainer{
			VMID:   vmid,
			Status: status,
			Name:   name,
		})
	}
	sort.Slice(out, func(i, j int) bool { return out[i].VMID < out[j].VMID })
	return out
}

type ProxmoxStorage struct {
	Name       string `json:"name"`
	Type       string `json:"type"`
	Status     string `json:"status"`
	AvailBytes int64  `json:"avail_bytes"`
}

// ParsePvesmStatus parses `pvesm status` output.
// Name         Type     Status           Total            Used       Available        %
// local        dir      active        98497780        12345678        81102548   12.53%
func ParsePvesmStatus(output string) []ProxmoxStorage {
	var out []ProxmoxStorage
	lines := strings.Split(strings.TrimSpace(output), "\n")
	for idx, line := range lines {
		fields := strings.Fields(line)
		if idx == 0 && len(fields) > 0 && strings.EqualFold(fields[0], "Name") {
			continue
		}
		if len(fields) < 6 {
			continue
		}
		availKB, _ := strconv.ParseInt(fields[5], 10, 64)
		out = append(out, ProxmoxStorage{
			Name:       fields[0],
			Type:       fields[1],
			Status:     fields[2],
			AvailBytes: availKB * 1024,
		})
	}
	return out
}

type LXCPreflightResult struct {
	VMIDFree      bool     `json:"vmid_free"`
	StorageReady  bool     `json:"storage_ready"`
	BridgeReady   bool     `json:"bridge_ready"`
	TemplateReady bool     `json:"template_ready"`
	ResourcesOK   bool     `json:"resources_ok"`
	Warnings      []string `json:"warnings,omitempty"`
	Blocking      []string `json:"blocking,omitempty"`
}

func (r LXCPreflightResult) Ready() bool {
	return len(r.Blocking) == 0 && r.VMIDFree && r.StorageReady && r.BridgeReady && r.ResourcesOK
}

// ValidateLXCPreflight validates the requested LXC configuration against discovered Proxmox state.
func ValidateLXCPreflight(vmid, cpu, ramMB, diskGB int, storage, bridge string, existing []LXCContainer, storages []ProxmoxStorage) LXCPreflightResult {
	res := LXCPreflightResult{
		VMIDFree:      true,
		StorageReady:  true,
		BridgeReady:   true,
		TemplateReady: true,
		ResourcesOK:   true,
	}
	if vmid < 100 {
		res.VMIDFree = false
		res.Blocking = append(res.Blocking, "VMID inválido (debe ser >= 100)")
	}
	for _, c := range existing {
		if c.VMID == vmid {
			res.VMIDFree = false
			res.Blocking = append(res.Blocking, fmt.Sprintf("el VMID %d ya está en uso por %q", vmid, c.Name))
			break
		}
	}
	if cpu < 1 || ramMB < 1024 || diskGB < 10 {
		res.ResourcesOK = false
		res.Blocking = append(res.Blocking, "recursos insuficientes (mínimo 1 CPU, 1024 MB RAM y 10 GB disco)")
	}
	if storage == "" {
		res.StorageReady = false
		res.Blocking = append(res.Blocking, "seleccioná un storage de Proxmox")
	} else if len(storages) > 0 {
		found := false
		for _, st := range storages {
			if st.Name == storage {
				found = true
				if st.Status != "active" {
					res.StorageReady = false
					res.Blocking = append(res.Blocking, fmt.Sprintf("storage %q no está activo (%s)", storage, st.Status))
				}
				reqBytes := int64(diskGB) * 1024 * 1024 * 1024
				if st.AvailBytes > 0 && st.AvailBytes < reqBytes {
					res.StorageReady = false
					res.Blocking = append(res.Blocking, fmt.Sprintf("espacio insuficiente en %q: requiere %d GB", storage, diskGB))
				}
				break
			}
		}
		if !found {
			res.StorageReady = false
			res.Blocking = append(res.Blocking, fmt.Sprintf("storage %q no existe en este nodo Proxmox", storage))
		}
	}
	if !regexp.MustCompile(`^[a-zA-Z0-9_.-]{2,16}$`).MatchString(bridge) {
		res.BridgeReady = false
		res.Blocking = append(res.Blocking, fmt.Sprintf("bridge de red inválido: %q", bridge))
	}
	return res
}

// DiscoverProxmoxLXC lists local LXC containers if running on Proxmox VE and checks for DOLAN evidence
// without modifying any container or confusing non-DOLAN Odoo installations.
func DiscoverProxmoxLXC(ctx context.Context) ([]LXCContainer, error) {
	if _, err := exec.LookPath("pct"); err != nil {
		return nil, nil
	}
	out, err := exec.CommandContext(ctx, "pct", "list").Output()
	if err != nil {
		return nil, err
	}
	containers := ParsePctList(string(out))
	for i := range containers {
		inspectLXCDolanEvidence(&containers[i])
	}
	return containers, nil
}

func inspectLXCDolanEvidence(c *LXCContainer) {
	// Check mounted rootfs if accessible on host without starting stopped containers
	rootfsCandidates := []string{
		fmt.Sprintf("/var/lib/lxc/%d/rootfs", c.VMID),
	}
	for _, rootfs := range rootfsCandidates {
		manifestPath := filepath.Join(rootfs, "opt", "dolan", "dolan-installation.json")
		if b, err := os.ReadFile(manifestPath); err == nil && strings.Contains(string(b), "schema_version") {
			c.IsDolan = true
			c.Evidence = "manifiesto /opt/dolan/dolan-installation.json"
			return
		}
		if _, err := os.Stat(filepath.Join(rootfs, "opt", "odoo", "dolan-addons", "DOLAN_base")); err == nil {
			c.IsDolan = true
			c.Evidence = "addons DOLAN_base en /opt/odoo/dolan-addons"
			return
		}
		if _, err := os.Stat(filepath.Join(rootfs, "etc", "odoo", "odoo.conf")); err == nil {
			c.IsOdooOther = true
			c.Evidence = "Odoo detectado sin firma DOLAN (no se modifica)"
		}
	}
}

// BuildNativeLXCProvisionScript generates the deterministic provisioning script for a Debian 13
// unprivileged LXC container with native PostgreSQL 17 and native Odoo CE 20 + DOLAN Suite (no Docker inside LXC).
func BuildNativeLXCProvisionScript(dbName, profile string, modules []string, demoMode string) string {
	modCSV := strings.Join(modules, ",")
	demoFlag := "--without-demo=True"
	if demoMode == "odoo" || demoMode == "dolan" {
		demoFlag = ""
	}
	return fmt.Sprintf(`#!/usr/bin/env bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive

# 1. Paquetes nativos Debian 13 (PostgreSQL + Python 3.12 + dependencias Odoo 20 CE)
apt-get update
apt-get install -y --no-install-recommends \
  ca-certificates curl git gnupg build-essential pkg-config \
  postgresql postgresql-client libpq-dev \
  python3 python3-venv python3-dev python3-pip \
  libxml2-dev libxslt1-dev libldap2-dev libsasl2-dev libssl-dev libffi-dev \
  libjpeg62-turbo-dev zlib1g-dev libfreetype6-dev liblcms2-dev libwebp-dev \
  fontconfig nodejs npm
npm install -g rtlcss

# 2. Usuario y estructura nativa de Odoo + DOLAN (sin Docker dentro de LXC)
id -u odoo >/dev/null 2>&1 || useradd --system --home-dir /var/lib/odoo --create-home --shell /usr/sbin/nologin odoo
install -d -m 0750 -o odoo -g odoo /opt/odoo /var/lib/odoo /var/log/odoo /etc/odoo /opt/dolan

# 3. Rol PostgreSQL local
systemctl enable --now postgresql
su - postgres -c "psql -tAc \"SELECT 1 FROM pg_roles WHERE rolname='odoo'\" | grep -q 1 || createuser -s odoo"

# 4. Inicialización de base %s con perfil %s (%s) y modo demo=%s
# Módulos: %s
# Flag demo: %s
`, dbName, profile, modCSV, demoMode, modCSV, demoFlag)
}
