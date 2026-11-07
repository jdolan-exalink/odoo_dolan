package state

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

const ManifestName = "dolan-installation.json"

type DatabaseRecord struct {
	Name      string   `json:"name"`
	Companies []string `json:"companies,omitempty"`
	DemoData  bool     `json:"demo_data"`
	DemoMode  string   `json:"demo_mode,omitempty"`
}

type Manifest struct {
	SchemaVersion  int              `json:"schema_version"`
	InstallationID string           `json:"installation_id"`
	Name           string           `json:"name"`
	Deployment     string           `json:"deployment"`
	VMID           int              `json:"vmid,omitempty"`
	OdooVersion    string           `json:"odoo_version"`
	OdooCommit     string           `json:"odoo_commit,omitempty"`
	DolanVersion   string           `json:"dolan_version"`
	Company        string           `json:"company"`
	Profile        string           `json:"profile"`
	Modules        []string         `json:"modules,omitempty"`
	DemoData       bool             `json:"demo_data"`
	DemoMode       string           `json:"demo_mode,omitempty"`
	Database       string           `json:"database"`
	Databases      []DatabaseRecord `json:"databases,omitempty"`
	Port           int              `json:"port"`
	CallbackPort   int              `json:"callback_port,omitempty"`
	ProjectPath    string           `json:"project_path"`
	CreatedAt      time.Time        `json:"created_at"`
	UpdatedAt      time.Time        `json:"updated_at,omitempty"`
	AdoptedAt      *time.Time       `json:"adopted_at,omitempty"`
	Services       []string         `json:"services"`
}

func NewUUID() string {
	b := make([]byte, 16)
	if _, err := rand.Read(b); err != nil {
		return fmt.Sprintf("dolan-%d", time.Now().UnixNano())
	}
	b[6] = (b[6] & 0x0f) | 0x40
	b[8] = (b[8] & 0x3f) | 0x80
	return fmt.Sprintf("%s-%s-%s-%s-%s",
		hex.EncodeToString(b[0:4]),
		hex.EncodeToString(b[4:6]),
		hex.EncodeToString(b[6:8]),
		hex.EncodeToString(b[8:10]),
		hex.EncodeToString(b[10:16]),
	)
}

func NormalizeManifest(m *Manifest) {
	if m.SchemaVersion == 0 {
		m.SchemaVersion = 1
	}
	if m.InstallationID == "" {
		m.InstallationID = NewUUID()
	}
	if m.Deployment == "" {
		m.Deployment = "docker"
	}
	if m.OdooVersion == "" {
		m.OdooVersion = "20.0"
	}
	if m.DolanVersion == "" {
		m.DolanVersion = "20.0.1"
	}
	if m.CreatedAt.IsZero() {
		m.CreatedAt = time.Now().UTC()
	}
	if m.UpdatedAt.IsZero() {
		m.UpdatedAt = m.CreatedAt
	}
	if m.DemoMode == "" {
		if m.DemoData {
			m.DemoMode = "odoo"
		} else {
			m.DemoMode = "none"
		}
	}
	if m.DemoMode != "none" {
		m.DemoData = true
	}
	if m.Database != "" && len(m.Databases) == 0 {
		var companies []string
		if m.Company != "" {
			companies = []string{m.Company}
		}
		m.Databases = []DatabaseRecord{
			{
				Name:      m.Database,
				Companies: companies,
				DemoData:  m.DemoData,
				DemoMode:  m.DemoMode,
			},
		}
	} else if m.Database == "" && len(m.Databases) > 0 {
		m.Database = m.Databases[0].Name
	}
}

func Write(path string, m Manifest) error {
	NormalizeManifest(&m)
	m.UpdatedAt = time.Now().UTC()
	data, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
		return err
	}
	if err := os.MkdirAll(path, 0750); err != nil {
		return err
	}
	tmp := filepath.Join(path, ManifestName+".tmp")
	if err := os.WriteFile(tmp, append(data, '\n'), 0600); err != nil {
		return err
	}
	return os.Rename(tmp, filepath.Join(path, ManifestName))
}

func Read(path string) (Manifest, error) {
	var m Manifest
	b, err := os.ReadFile(filepath.Join(path, ManifestName))
	if err != nil {
		return m, err
	}
	if err := json.Unmarshal(b, &m); err != nil {
		return m, err
	}
	NormalizeManifest(&m)
	return m, nil
}
