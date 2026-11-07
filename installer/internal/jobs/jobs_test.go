package jobs

import (
	"testing"
	"time"
)

func TestJobLifecycleAndWeightedProgress(t *testing.T) {
	store := NewStore(t.TempDir())
	stages := []Stage{
		{ID: "validate", Title: "Validación inicial", Weight: 10},
		{ID: "db", Title: "Exportación PostgreSQL", Weight: 30},
		{ID: "filestore", Title: "Copia del filestore", Weight: 40},
		{ID: "verify", Title: "Verificación", Weight: 20},
	}
	job, err := store.Create("backup", "Backup Frigorífico", "inst-101", "lxc-101", false, stages)
	if err != nil {
		t.Fatalf("Create failed: %v", err)
	}
	if job.OverallPercent != 0 {
		t.Fatalf("expected initial 0%%, got %d%%", job.OverallPercent)
	}

	job, err = store.UpdateStage(job.ID, "validate", StatusCompleted, 100, "Validación completada", nil)
	if err != nil {
		t.Fatal(err)
	}
	if job.OverallPercent != 10 {
		t.Fatalf("expected 10%%, got %d%%", job.OverallPercent)
	}

	job, err = store.UpdateStage(job.ID, "db", StatusCompleted, 100, "Dump finalizado", nil)
	if err != nil {
		t.Fatal(err)
	}
	// 10 + 30 = 40%
	if job.OverallPercent != 40 {
		t.Fatalf("expected 40%%, got %d%%", job.OverallPercent)
	}

	tm := ComputeTransferMetrics("Copia del filestore", 3400*1024*1024, 5000*1024*1024, 40*time.Second)
	job, err = store.UpdateStage(job.ID, "filestore", StatusRunning, 70, "Procesando adjuntos", &tm)
	if err != nil {
		t.Fatal(err)
	}
	// 10 + 30 + (40 * 0.70) = 68%
	if job.OverallPercent != 68 {
		t.Fatalf("expected 68%%, got %d%%", job.OverallPercent)
	}
	if !job.Transfer.Active || job.Transfer.ETASeconds <= 0 {
		t.Fatalf("expected active transfer metrics with ETA, got %+v", job.Transfer)
	}

	if err := store.AppendLog(job.ID, "POSTGRES_PASSWORD=supersecret copiado", "supersecret"); err != nil {
		t.Fatal(err)
	}
	logs, err := store.ReadLogs(job.ID, 10)
	if err != nil || len(logs) != 1 {
		t.Fatalf("expected 1 log line, got %v (%v)", logs, err)
	}
	if logs[0] == "POSTGRES_PASSWORD=supersecret copiado" {
		t.Fatalf("secret was not redacted in job log: %s", logs[0])
	}

	active, err := store.ActiveJobs()
	if err != nil || len(active) != 1 {
		t.Fatalf("expected 1 active job for SSH reconnect, got %d", len(active))
	}

	job, err = store.Finish(job.ID, StatusCompleted, "")
	if err != nil {
		t.Fatal(err)
	}
	if job.OverallPercent != 100 || job.Status != StatusCompleted {
		t.Fatalf("expected 100%% completed, got %d%% %s", job.OverallPercent, job.Status)
	}
}
