package cli

import (
	"os"
	"path/filepath"
	"testing"
)

func TestCLISubcommandsAndAdoption(t *testing.T) {
	root := t.TempDir()
	instDir := filepath.Join(root, "cliente1")
	if err := os.MkdirAll(instDir, 0750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(instDir, "docker-compose.yml"), []byte("services:\n  odoo:\n    image: odoo:20.0\n"), 0600); err != nil {
		t.Fatal(err)
	}

	// 1. List unmanaged deployment in JSON
	if err := Run([]string{"list", "--root", root, "--json"}); err != nil {
		t.Fatalf("list --json failed: %v", err)
	}

	// 2. Adopt without --yes must fail (explicit consent guard)
	if err := Run([]string{"adopt", "--root", root, "--installation", "cliente1"}); err == nil {
		t.Fatal("expected adopt without --yes to fail")
	}

	// 3. Adopt with --yes must succeed and create manifest
	if err := Run([]string{"adopt", "--root", root, "--installation", "cliente1", "--company", "Cliente Uno SA", "--profile", "servicios", "--yes", "--json"}); err != nil {
		t.Fatalf("adopt --yes failed: %v", err)
	}

	// 4. Packages list and plan (Servicios -> Comercio)
	planPath := filepath.Join(root, "plan.json")
	if err := Run([]string{"packages", "plan", "--root", root, "--installation", "cliente1", "--profile", "comercio", "--out", planPath, "--json"}); err != nil {
		t.Fatalf("packages plan failed: %v", err)
	}
	if err := Run([]string{"packages", "apply", "--root", root, "--installation", "cliente1", "--plan", planPath, "--json"}); err != nil {
		t.Fatalf("packages apply failed: %v", err)
	}

	// 5. Create and verify .dolanbak backup via CLI
	bakFile := filepath.Join(root, "backups", "cliente1.dolanbak")
	if err := Run([]string{"backup", "create", "--root", root, "--installation", "cliente1", "--file", bakFile, "--json"}); err != nil {
		t.Fatalf("backup create failed: %v", err)
	}
	if err := Run([]string{"backup", "verify", "--file", bakFile, "--json"}); err != nil {
		t.Fatalf("backup verify failed: %v", err)
	}
	if err := Run([]string{"restore", "plan", "--file", bakFile, "--target", "lxc", "--json"}); err != nil {
		t.Fatalf("restore plan failed: %v", err)
	}

	// 6. Update check JSON
	if err := Run([]string{"update", "check", "--json"}); err != nil {
		t.Fatalf("update check failed: %v", err)
	}
}
