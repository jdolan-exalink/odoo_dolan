package jobs

import (
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"math"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/security"
)

type Status string

const (
	StatusPending   Status = "pending"
	StatusRunning   Status = "running"
	StatusCompleted Status = "completed"
	StatusFailed    Status = "failed"
	StatusCanceled  Status = "canceled"
)

type Stage struct {
	ID          string    `json:"id"`
	Title       string    `json:"title"`
	Weight      float64   `json:"weight"`
	Status      Status    `json:"status"`
	ProgressPct float64   `json:"progress_pct"`
	StartedAt   time.Time `json:"started_at,omitempty"`
	CompletedAt time.Time `json:"completed_at,omitempty"`
	Detail      string    `json:"detail,omitempty"`
}

type TransferMetrics struct {
	Active         bool    `json:"active"`
	Label          string  `json:"label,omitempty"`
	BytesProcessed int64   `json:"bytes_processed"`
	BytesTotal     int64   `json:"bytes_total"`
	SpeedBPS       float64 `json:"speed_bps"`
	ETASeconds     int     `json:"eta_seconds"`
}

type Job struct {
	ID             string          `json:"id"`
	Type           string          `json:"type"`
	Title          string          `json:"title"`
	InstallationID string          `json:"installation_id,omitempty"`
	Target         string          `json:"target,omitempty"`
	Status         Status          `json:"status"`
	Destructive    bool            `json:"destructive"`
	Stages         []Stage         `json:"stages"`
	CurrentStage   string          `json:"current_stage,omitempty"`
	OverallPercent int             `json:"overall_percent"`
	Transfer       TransferMetrics `json:"transfer"`
	LastEvent      string          `json:"last_event,omitempty"`
	Error          string          `json:"error,omitempty"`
	CreatedAt      time.Time       `json:"created_at"`
	UpdatedAt      time.Time       `json:"updated_at"`
	CompletedAt    time.Time       `json:"completed_at,omitempty"`
	PID            int             `json:"pid,omitempty"`
	LogPath        string          `json:"log_path"`
}

type Store struct {
	Root string
	mu   sync.Mutex
}

func DefaultJobsRoot() string {
	if override := os.Getenv("DOLAN_JOBS_ROOT"); override != "" {
		return override
	}
	if runtime.GOOS == "windows" {
		base := os.Getenv("PROGRAMDATA")
		if base == "" {
			base = `C:\ProgramData`
		}
		return filepath.Join(base, "DOLAN", "jobs")
	}
	return "/opt/dolan/jobs"
}

func NewStore(root string) *Store {
	if root == "" {
		root = DefaultJobsRoot()
	}
	return &Store{Root: root}
}

func newJobID(jobType string) string {
	b := make([]byte, 4)
	_, _ = rand.Read(b)
	prefix := strings.ToLower(strings.TrimSpace(jobType))
	if prefix == "" {
		prefix = "job"
	}
	return fmt.Sprintf("%s-%s-%s", prefix, time.Now().UTC().Format("20060102-150405"), hex.EncodeToString(b))
}

func (s *Store) Create(jobType, title, installationID, target string, destructive bool, stages []Stage) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if err := os.MkdirAll(s.Root, 0700); err != nil {
		return Job{}, err
	}
	id := newJobID(jobType)
	dir := filepath.Join(s.Root, id)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return Job{}, err
	}
	now := time.Now().UTC()
	for i := range stages {
		if stages[i].Weight <= 0 {
			stages[i].Weight = 1
		}
		if stages[i].Status == "" {
			stages[i].Status = StatusPending
		}
	}
	j := Job{
		ID:             id,
		Type:           jobType,
		Title:          title,
		InstallationID: installationID,
		Target:         target,
		Status:         StatusPending,
		Destructive:    destructive,
		Stages:         stages,
		CreatedAt:      now,
		UpdatedAt:      now,
		PID:            os.Getpid(),
		LogPath:        filepath.Join(dir, "job.log"),
	}
	j.OverallPercent = CalculateOverallPercent(j.Stages)
	if err := s.saveLocked(j); err != nil {
		return Job{}, err
	}
	return j, nil
}

func CalculateOverallPercent(stages []Stage) int {
	if len(stages) == 0 {
		return 0
	}
	totalWeight := 0.0
	weightedSum := 0.0
	for _, st := range stages {
		w := st.Weight
		if w <= 0 {
			w = 1
		}
		totalWeight += w
		pct := st.ProgressPct
		switch st.Status {
		case StatusCompleted:
			pct = 100
		case StatusPending:
			pct = 0
		default:
			if pct < 0 {
				pct = 0
			}
			if pct > 100 {
				pct = 100
			}
		}
		weightedSum += w * (pct / 100.0)
	}
	if totalWeight <= 0 {
		return 0
	}
	res := int(math.Round((weightedSum / totalWeight) * 100.0))
	if res < 0 {
		return 0
	}
	if res > 100 {
		return 100
	}
	return res
}

func ComputeTransferMetrics(label string, processed, total int64, elapsed time.Duration) TransferMetrics {
	m := TransferMetrics{
		Active:         true,
		Label:          label,
		BytesProcessed: processed,
		BytesTotal:     total,
	}
	secs := elapsed.Seconds()
	if secs > 0.05 && processed > 0 {
		m.SpeedBPS = float64(processed) / secs
		if total > processed && m.SpeedBPS > 1 {
			remaining := float64(total - processed)
			m.ETASeconds = int(math.Ceil(remaining / m.SpeedBPS))
		}
	}
	return m
}

func FormatBytes(b int64) string {
	const unit = 1024
	if b < unit {
		return fmt.Sprintf("%d B", b)
	}
	div, exp := int64(unit), 0
	for n := b / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	return fmt.Sprintf("%.1f %cB", float64(b)/float64(div), "KMGTPE"[exp])
}

func FormatDuration(seconds int) string {
	if seconds <= 0 {
		return "00:00"
	}
	mins := seconds / 60
	secs := seconds % 60
	if mins >= 60 {
		hours := mins / 60
		mins = mins % 60
		return fmt.Sprintf("%02d:%02d:%02d", hours, mins, secs)
	}
	return fmt.Sprintf("%02d:%02d", mins, secs)
}

func (s *Store) UpdateStage(jobID, stageID string, status Status, pct float64, event string, transfer *TransferMetrics) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	j, err := s.loadLocked(jobID)
	if err != nil {
		return Job{}, err
	}
	now := time.Now().UTC()
	if j.Status == StatusPending && status == StatusRunning {
		j.Status = StatusRunning
	}
	for i := range j.Stages {
		if j.Stages[i].ID == stageID {
			j.Stages[i].Status = status
			if status == StatusCompleted {
				j.Stages[i].ProgressPct = 100
				j.Stages[i].CompletedAt = now
			} else {
				j.Stages[i].ProgressPct = pct
			}
			if j.Stages[i].StartedAt.IsZero() && (status == StatusRunning || status == StatusCompleted) {
				j.Stages[i].StartedAt = now
			}
			if event != "" {
				j.Stages[i].Detail = event
			}
			j.CurrentStage = j.Stages[i].Title
			break
		}
	}
	if event != "" {
		j.LastEvent = event
	}
	if transfer != nil {
		j.Transfer = *transfer
	} else if status == StatusCompleted {
		j.Transfer = TransferMetrics{}
	}
	j.OverallPercent = CalculateOverallPercent(j.Stages)
	j.UpdatedAt = now
	if err := s.saveLocked(j); err != nil {
		return Job{}, err
	}
	return j, nil
}

func (s *Store) AppendLog(jobID, line string, secrets ...string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	j, err := s.loadLocked(jobID)
	if err != nil {
		return err
	}
	clean := security.Redact(line, secrets...)
	j.LastEvent = clean
	j.UpdatedAt = time.Now().UTC()
	_ = s.saveLocked(j)

	f, err := os.OpenFile(j.LogPath, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0600)
	if err != nil {
		return err
	}
	defer f.Close()
	_, err = fmt.Fprintf(f, "%s %s\n", time.Now().UTC().Format(time.RFC3339), clean)
	return err
}

func (s *Store) Finish(jobID string, finalStatus Status, errMsg string) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	j, err := s.loadLocked(jobID)
	if err != nil {
		return Job{}, err
	}
	now := time.Now().UTC()
	j.Status = finalStatus
	j.Error = security.Redact(errMsg)
	j.UpdatedAt = now
	j.CompletedAt = now
	j.Transfer = TransferMetrics{}
	if finalStatus == StatusCompleted {
		for i := range j.Stages {
			j.Stages[i].Status = StatusCompleted
			j.Stages[i].ProgressPct = 100
		}
		j.OverallPercent = 100
	}
	if err := s.saveLocked(j); err != nil {
		return Job{}, err
	}
	return j, nil
}

func (s *Store) Get(jobID string) (Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.loadLocked(jobID)
}

func (s *Store) List() ([]Job, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	entries, err := os.ReadDir(s.Root)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	var out []Job
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		if j, err := s.loadLocked(entry.Name()); err == nil {
			out = append(out, j)
		}
	}
	sort.Slice(out, func(i, k int) bool {
		return out[i].CreatedAt.After(out[k].CreatedAt)
	})
	return out, nil
}

func (s *Store) ActiveJobs() ([]Job, error) {
	all, err := s.List()
	if err != nil {
		return nil, err
	}
	var active []Job
	for _, j := range all {
		if j.Status == StatusRunning || j.Status == StatusPending {
			active = append(active, j)
		}
	}
	return active, nil
}

func (s *Store) ReadLogs(jobID string, tail int) ([]string, error) {
	j, err := s.Get(jobID)
	if err != nil {
		return nil, err
	}
	b, err := os.ReadFile(j.LogPath)
	if os.IsNotExist(err) {
		return nil, nil
	}
	if err != nil {
		return nil, err
	}
	lines := strings.Split(strings.TrimRight(string(b), "\r\n"), "\n")
	if tail > 0 && len(lines) > tail {
		lines = lines[len(lines)-tail:]
	}
	return lines, nil
}

func (s *Store) loadLocked(jobID string) (Job, error) {
	var j Job
	if jobID == "" || strings.ContainsAny(jobID, `/\`) || jobID == "." || jobID == ".." {
		return j, fmt.Errorf("job id inválido: %q", jobID)
	}
	path := filepath.Join(s.Root, jobID, "job.json")
	b, err := os.ReadFile(path)
	if err != nil {
		return j, err
	}
	if err := json.Unmarshal(b, &j); err != nil {
		return j, err
	}
	return j, nil
}

func (s *Store) saveLocked(j Job) error {
	dir := filepath.Join(s.Root, j.ID)
	if err := os.MkdirAll(dir, 0700); err != nil {
		return err
	}
	data, err := json.MarshalIndent(j, "", "  ")
	if err != nil {
		return err
	}
	tmp := filepath.Join(dir, "job.json.tmp")
	if err := os.WriteFile(tmp, append(data, '\n'), 0600); err != nil {
		return err
	}
	return os.Rename(tmp, filepath.Join(dir, "job.json"))
}
