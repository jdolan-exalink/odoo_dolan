package engine

import (
	"context"
	"os"
	"path/filepath"
	"testing"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
)

func TestResetExistingDeploymentGuards(t *testing.T) {
	root := t.TempDir()
	cfg := core.NewConfig()
	cfg.ProjectRoot = root
	cfg.ProjectName = "sodecar"

	if err := resetExistingDeployment(context.Background(), cfg, nil, nil, nil); err != nil {
		t.Fatalf("absent destination without reset should be okay: %v", err)
	}
	cfg.ResetExistingName = "sodecar"
	if err := resetExistingDeployment(context.Background(), cfg, nil, nil, nil); err == nil {
		t.Fatal("reset must reject a missing deployment")
	}

	target := cfg.DeploymentPath()
	if err := os.MkdirAll(target, 0700); err != nil {
		t.Fatal(err)
	}
	cfg.ResetExistingName = ""
	if err := resetExistingDeployment(context.Background(), cfg, nil, nil, nil); err == nil {
		t.Fatal("existing destination must be preserved without explicit reset")
	}
	cfg.ResetExistingName = "other"
	if err := resetExistingDeployment(context.Background(), cfg, nil, nil, nil); err == nil {
		t.Fatal("reset target must match project name")
	}
	cfg.ResetExistingName = "sodecar"
	if err := resetExistingDeployment(context.Background(), cfg, nil, nil, nil); err == nil {
		t.Fatal("reset must require a Compose project")
	}
	if _, err := os.Stat(filepath.Join(target, "docker-compose.yml")); !os.IsNotExist(err) {
		t.Fatal("guard tests should leave files untouched")
	}
}
