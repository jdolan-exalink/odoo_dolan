package cli

import (
	"os"
	"path/filepath"
	"strings"
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
	if err := os.WriteFile(filepath.Join(instDir, ".env"), []byte("DOLAN_PROFILE=servicios\n"), 0600); err != nil {
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

	// 4. Standalone packages plan (--current-profile servicios --target-profile comercio)
	if err := Run([]string{"packages", "plan", "--current-profile", "servicios", "--target-profile", "comercio"}); err != nil {
		t.Fatalf("standalone packages plan failed: %v", err)
	}

	// 5. Packages plan and apply on real installation (Servicios -> Comercio + DOLAN_stock_mrp)
	planPath := filepath.Join(root, "plan.json")
	if err := Run([]string{"packages", "plan", "--root", root, "--installation", "cliente1", "--profile", "comercio", "--add", "DOLAN_stock_mrp", "--out", planPath, "--json"}); err != nil {
		t.Fatalf("packages plan failed: %v", err)
	}
	if err := Run([]string{"packages", "apply", "--root", root, "--installation", "cliente1", "--plan", planPath, "--json"}); err != nil {
		t.Fatalf("packages apply failed: %v", err)
	}
	envBytes, err := os.ReadFile(filepath.Join(instDir, ".env"))
	if err != nil {
		t.Fatal(err)
	}
	if !strings.Contains(string(envBytes), "DOLAN_PROFILE=comercio") || !strings.Contains(string(envBytes), "DOLAN_stock_mrp") {
		t.Fatalf("expected .env to be updated with DOLAN_PROFILE=comercio and DOLAN_stock_mrp, got:\n%s", string(envBytes))
	}

	// 6. Create and verify .dolanbak backup via CLI
	bakFile := filepath.Join(root, "backups", "cliente1.dolanbak")
	if err := Run([]string{"backup", "create", "--root", root, "--name", "cliente1", "--out", bakFile, "--json"}); err != nil {
		t.Fatalf("backup create failed: %v", err)
	}
	if err := Run([]string{"backup", "verify", "--file", bakFile, "--json"}); err != nil {
		t.Fatalf("backup verify failed: %v", err)
	}
	if err := Run([]string{"restore", "plan", "--file", bakFile, "--target-provider", "proxmox-lxc", "--json"}); err != nil {
		t.Fatalf("restore plan failed: %v", err)
	}

	// 7. Update check JSON
	if err := Run([]string{"update", "check", "--json"}); err != nil {
		t.Fatalf("update check failed: %v", err)
	}

	// 8. Delete installation (--yes required in non-interactive mode)
	if err := Run([]string{"delete", "--root", root, "--name", "cliente1"}); err == nil {
		t.Fatal("expected delete without --yes to fail in non-interactive mode")
	}
	if err := Run([]string{"delete", "--root", root, "--name", "cliente1", "--yes", "--json"}); err != nil {
		t.Fatalf("delete --yes failed: %v", err)
	}
	if _, err := os.Stat(instDir); !os.IsNotExist(err) {
		t.Fatalf("expected installation directory %s to be deleted", instDir)
	}
}
