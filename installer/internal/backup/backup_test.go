package backup

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/state"
)

func TestBackupCreateVerifyAndEncryption(t *testing.T) {
	tmp := t.TempDir()
	srcDir := filepath.Join(tmp, "src")
	if err := os.MkdirAll(filepath.Join(srcDir, "odoo-data", "filestore", "odoo_frigorifico", "ab"), 0750); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "odoo-data", "filestore", "odoo_frigorifico", "ab", "ab123"), []byte("attachment-data"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(srcDir, "odoo.conf"), []byte("[options]\nadmin_passwd = secret123\ndb_password = pgsecret\nworkers = 2\n"), 0600); err != nil {
		t.Fatal(err)
	}

	inst := state.Manifest{
		Name:             "frigorifico",
		Company:          "Frigorífico Demo SRL",
		Deployment:       "docker",
		OdooVersion:      "20.0",
		DolanVersion:     "20.0.1",
		Profile:          "comercio",
		Modules:          []string{"DOLAN_base", "DOLAN_pos"},
		Database:         "odoo_frigorifico",
		DemoData:         true,
		DemoMode:         "dolan",
	}

	outFile := filepath.Join(tmp, "frigorifico.dolanbak")
	m, err := Create(CreateOptions{
		Installation:     inst,
		SourceDir:        srcDir,
		OutputPath:       outFile,
		Type:             TypeFull,
		IncludeFilestore: true,
		VerifyIntegrity:  true,
		Passphrase:       "clave-fuerte-2026",
		DBDumpOverride: map[string][]byte{
			"odoo_frigorifico": []byte("PGDMP_CONSISTENT_DUMP_BYTES"),
		},
	})
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}
	if !m.Encrypted || !m.IncludesFilestore {
		t.Fatalf("expected encrypted full backup with filestore, got %+v", m)
	}

	// Wrong passphrase must fail
	if _, err := Verify(outFile, "clave-incorrecta"); err == nil {
		t.Fatal("expected invalid passphrase to fail verification")
	}

	// Correct passphrase must pass
	rep, err := Verify(outFile, "clave-fuerte-2026")
	if err != nil || !rep.Valid {
		t.Fatalf("Verify with correct passphrase failed: %v (%v)", err, rep.Errors)
	}

	// PlanRestore Docker -> Proxmox LXC migration preflight
	plan, err := PlanRestore(outFile, "clave-fuerte-2026", "proxmox-lxc", 110, "", false, []string{"DOLAN_base", "DOLAN_pos"}, 80*1024*1024*1024)
	if err != nil {
		t.Fatalf("PlanRestore failed: %v", err)
	}
	if !plan.Ready() || !plan.PreserveDemoNoReseed || !plan.ExternalIntegrationsOff {
		t.Fatalf("expected valid migration plan, got %+v", plan)
	}

	// Missing addon in target must block restore safely (Test 14)
	badPlan, err := PlanRestore(outFile, "clave-fuerte-2026", "proxmox-lxc", 110, "", false, []string{"DOLAN_base"}, 80*1024*1024*1024)
	if err != nil {
		t.Fatal(err)
	}
	if badPlan.Ready() || badPlan.ModulesAvailable {
		t.Fatal("expected missing DOLAN_pos addon to block restore")
	}
}

func TestMaliciousArchiveAndCorruptionBlocked(t *testing.T) {
	tmp := t.TempDir()

	// 1. Corrupt header
	corruptPath := filepath.Join(tmp, "corrupt.dolanbak")
	if err := os.WriteFile(corruptPath, []byte("NOT_A_VALID_BACKUP"), 0600); err != nil {
		t.Fatal(err)
	}
	if _, err := Verify(corruptPath, ""); err == nil {
		t.Fatal("expected corrupt backup to be rejected")
	}

	// 2. Malicious tar with path traversal "../../etc/passwd"
	var buf bytes.Buffer
	gz := gzip.NewWriter(&buf)
	tw := tar.NewWriter(gz)
	evilData := []byte("root:x:0:0")
	_ = tw.WriteHeader(&tar.Header{
		Name:     "../../etc/passwd",
		Mode:     0600,
		Size:     int64(len(evilData)),
		Typeflag: tar.TypeReg,
	})
	_, _ = tw.Write(evilData)
	_ = tw.Close()
	_ = gz.Close()

	evilPath := filepath.Join(tmp, "evil.dolanbak")
	raw := append([]byte(FormatMagic), buf.Bytes()...)
	if err := os.WriteFile(evilPath, raw, 0600); err != nil {
		t.Fatal(err)
	}
	rep, err := Verify(evilPath, "")
	if err == nil || rep.Valid {
		t.Fatal("expected path traversal archive to be rejected")
	}
	if !strings.Contains(err.Error(), "traversal") {
		t.Fatalf("expected traversal error, got: %v", err)
	}
}
