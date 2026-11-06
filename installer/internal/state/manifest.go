package state

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

const ManifestName = "dolan-installation.json"

type Manifest struct {
	SchemaVersion int       `json:"schema_version"`
	Name          string    `json:"name"`
	Company       string    `json:"company"`
	Profile       string    `json:"profile"`
	Database      string    `json:"database"`
	Port          int       `json:"port"`
	ProjectPath   string    `json:"project_path"`
	CreatedAt     time.Time `json:"created_at"`
	Services      []string  `json:"services"`
}

func Write(path string, m Manifest) error {
	m.SchemaVersion = 1
	if m.CreatedAt.IsZero() {
		m.CreatedAt = time.Now().UTC()
	}
	data, err := json.MarshalIndent(m, "", "  ")
	if err != nil {
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
	err = json.Unmarshal(b, &m)
	return m, err
}
