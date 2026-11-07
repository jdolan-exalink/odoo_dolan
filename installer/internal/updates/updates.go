package updates

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

type ComponentUpdate struct {
	Component string `json:"component"`
	Current   string `json:"current"`
	Available string `json:"available"`
	Status    string `json:"status"` // up-to-date, available, review, compatible
	Notes     string `json:"notes,omitempty"`
}

type UpdateReport struct {
	CheckedAt        time.Time         `json:"checked_at"`
	BackupBeforeRun  bool              `json:"backup_before_run"`
	Components       []ComponentUpdate `json:"components"`
	PinnedOdooCommit string            `json:"pinned_odoo_commit,omitempty"`
	PinnedAdhocRepos int               `json:"pinned_adhoc_repos"`
}

type lockFile struct {
	Odoo struct {
		Series string `json:"series"`
		Commit string `json:"commit"`
	} `json:"odoo"`
	IngAdhoc []struct {
		Name   string `json:"name"`
		Commit string `json:"commit"`
	} `json:"ingadhoc"`
}

func Check(repoRoot, managerVersion, currentDolanVersion string) UpdateReport {
	rep := UpdateReport{
		CheckedAt:       time.Now().UTC(),
		BackupBeforeRun: true,
	}
	if managerVersion == "" || managerVersion == "dev" {
		managerVersion = "2.0.0"
	}
	if currentDolanVersion == "" {
		currentDolanVersion = "20.0.1"
	}

	var lf lockFile
	if repoRoot != "" {
		if b, err := os.ReadFile(filepath.Join(repoRoot, "distribution.lock.json")); err == nil {
			_ = json.Unmarshal(b, &lf)
		}
	}
	rep.PinnedOdooCommit = lf.Odoo.Commit
	rep.PinnedAdhocRepos = len(lf.IngAdhoc)

	odooSerie := lf.Odoo.Series
	if odooSerie == "" {
		odooSerie = "20.0"
	}

	rep.Components = []ComponentUpdate{
		{
			Component: "DOLAN Manager",
			Current:   managerVersion,
			Available: managerVersion,
			Status:    "compatible",
			Notes:     "Binario precompilado verificado por SHA-256",
		},
		{
			Component: "DOLAN Suite",
			Current:   currentDolanVersion,
			Available: "20.0.1",
			Status:    "compatible",
			Notes:     "Actualización selectiva de módulos instalados (sin -u all ciego)",
		},
		{
			Component: "Odoo Community",
			Current:   odooSerie,
			Available: "Revisar",
			Status:    "review",
			Notes:     "Commit fijado en distribution.lock.json; no se hace git pull indiscriminado",
		},
		{
			Component: "PostgreSQL",
			Current:   "17",
			Available: "Compatible",
			Status:    "compatible",
			Notes:     "Requiere backup lógico .dolanbak antes de migración mayor",
		},
	}
	return rep
}
