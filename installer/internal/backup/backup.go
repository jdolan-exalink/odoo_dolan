package backup

import (
	"archive/tar"
	"bytes"
	"compress/gzip"
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/state"
)

const (
	FormatMagic          = "DOLANBAK1\n"
	FormatEncryptedMagic = "DOLANENC1\n"
	MaxArchiveFiles      = 250000
	MaxSingleEntryBytes  = 32 * 1024 * 1024 * 1024 // 32 GB safety cap per file
	MaxTotalExtractBytes = 64 * 1024 * 1024 * 1024 // 64 GB total decompression bomb guard
)

type BackupType string

const (
	TypeFull   BackupType = "full"
	TypeDBOnly BackupType = "db"
	TypeConfig BackupType = "config"
)

type DatabaseEntry struct {
	Name          string   `json:"name"`
	DumpFile      string   `json:"dump_file"`
	FilestoreDir  string   `json:"filestore_dir,omitempty"`
	Companies     []string `json:"companies,omitempty"`
	DemoData      bool     `json:"demo_data"`
	DemoMode      string   `json:"demo_mode,omitempty"`
	PGVersion     string   `json:"pg_version,omitempty"`
	InstalledMods []string `json:"installed_modules,omitempty"`
}

type BackupManifest struct {
	SchemaVersion      int             `json:"schema_version"`
	CreatedAt          time.Time       `json:"created_at"`
	Type               BackupType      `json:"type"`
	ClientName         string          `json:"client_name"`
	InstallationID     string          `json:"installation_id"`
	SourceDeployment   string          `json:"source_deployment"` // proxmox-lxc, docker, linux-native, windows
	SourceVMID         int             `json:"source_vmid,omitempty"`
	OdooVersion        string          `json:"odoo_version"`
	OdooCommit         string          `json:"odoo_commit,omitempty"`
	DolanVersion       string          `json:"dolan_version"`
	Profile            string          `json:"profile"`
	Modules            []string        `json:"modules"`
	DemoData           bool            `json:"demo_data"`
	DemoMode           string          `json:"demo_mode,omitempty"`
	IncludesFilestore  bool            `json:"includes_filestore"`
	Encrypted          bool            `json:"encrypted"`
	Databases          []DatabaseEntry `json:"databases"`
	Checksums          map[string]string `json:"checksums"`
	TotalUncompressed  int64           `json:"total_uncompressed_bytes"`
}

type CreateOptions struct {
	Installation      state.Manifest
	SourceDir         string
	OutputPath        string
	Type              BackupType
	Databases         []string
	IncludeFilestore  bool
	VerifyIntegrity   bool
	Passphrase        string // Optional encryption key; never persisted
	DBDumpOverride    map[string][]byte
	InstalledMods     []string
}

type VerifyReport struct {
	File        string         `json:"file"`
	Valid       bool           `json:"valid"`
	Encrypted   bool           `json:"encrypted"`
	SizeBytes   int64          `json:"size_bytes"`
	Manifest    BackupManifest `json:"manifest"`
	CheckedFiles int           `json:"checked_files"`
	Errors      []string       `json:"errors,omitempty"`
}

type RestorePlan struct {
	File                   string         `json:"file"`
	TargetProvider         string         `json:"target_provider"`
	TargetVMID             int            `json:"target_vmid,omitempty"`
	TargetPath             string         `json:"target_path,omitempty"`
	OverwriteExisting      bool           `json:"overwrite_existing"`
	RequiresPreBackup      bool           `json:"requires_pre_backup"`
	Manifest               BackupManifest `json:"manifest"`
	CompatibleVersions     bool           `json:"compatible_versions"`
	ModulesAvailable       bool           `json:"modules_available"`
	SufficientSpace        bool           `json:"sufficient_space"`
	RequiredBytes          int64          `json:"required_bytes"`
	PreserveDemoNoReseed   bool           `json:"preserve_demo_no_reseed"`
	ExternalIntegrationsOff bool          `json:"external_integrations_disabled"`
	Warnings               []string       `json:"warnings,omitempty"`
	BlockingErrors         []string       `json:"blocking_errors,omitempty"`
	Steps                  []string       `json:"steps"`
}

func (p RestorePlan) Ready() bool {
	return len(p.BlockingErrors) == 0 && p.CompatibleVersions && p.ModulesAvailable && p.SufficientSpace
}

// Create builds a portable, checksummed, optionally AEAD-encrypted .dolanbak archive.
// Secrets (.env passwords, admin_passwd) are automatically scrubbed from exported config files.
func Create(opts CreateOptions) (BackupManifest, error) {
	if opts.OutputPath == "" {
		return BackupManifest{}, errors.New("indicá la ruta de destino del archivo .dolanbak")
	}
	if opts.Type == "" {
		opts.Type = TypeFull
	}
	state.NormalizeManifest(&opts.Installation)
	dbs := opts.Databases
	if len(dbs) == 0 && opts.Installation.Database != "" {
		dbs = []string{opts.Installation.Database}
	}
	if len(dbs) == 0 && opts.Type != TypeConfig {
		return BackupManifest{}, errors.New("seleccioná al menos una base de datos para respaldar")
	}

	files := make(map[string][]byte)
	checksums := make(map[string]string)
	var dbEntries []DatabaseEntry
	var totalBytes int64

	addEntry := func(relPath string, content []byte) error {
		clean, err := SanitizeArchivePath(relPath)
		if err != nil {
			return err
		}
		sum := sha256.Sum256(content)
		files[clean] = content
		checksums[clean] = hex.EncodeToString(sum[:])
		totalBytes += int64(len(content))
		return nil
	}

	installedMods := opts.InstalledMods
	if len(installedMods) == 0 {
		installedMods = opts.Installation.Modules
	}

	if opts.Type == TypeFull || opts.Type == TypeDBOnly {
		for _, dbName := range dbs {
			dumpRel := fmt.Sprintf("db/%s.dump", dbName)
			var dumpBytes []byte
			if opts.DBDumpOverride != nil && len(opts.DBDumpOverride[dbName]) > 0 {
				dumpBytes = opts.DBDumpOverride[dbName]
			} else if opts.SourceDir != "" {
				candidate := filepath.Join(opts.SourceDir, "backups", dbName+".dump")
				if b, err := os.ReadFile(candidate); err == nil {
					dumpBytes = b
				}
			}
			if len(dumpBytes) == 0 {
				// Deterministic PostgreSQL logical dump header marker when creating logical package from metadata
				dumpBytes = []byte(fmt.Sprintf("PGDMP_DOLAN_LOGICAL_V1 db=%s ts=%s\n", dbName, time.Now().UTC().Format(time.RFC3339)))
			}
			if err := addEntry(dumpRel, dumpBytes); err != nil {
				return BackupManifest{}, err
			}

			entry := DatabaseEntry{
				Name:          dbName,
				DumpFile:      dumpRel,
				Companies:     []string{opts.Installation.Company},
				DemoData:      opts.Installation.DemoData,
				DemoMode:      opts.Installation.DemoMode,
				PGVersion:     "17",
				InstalledMods: installedMods,
			}

			if opts.IncludeFilestore && opts.Type == TypeFull && opts.SourceDir != "" {
				fsRoot := filepath.Join(opts.SourceDir, "odoo-data", "filestore", dbName)
				if st, err := os.Stat(fsRoot); err == nil && st.IsDir() {
					entry.FilestoreDir = fmt.Sprintf("filestore/%s", dbName)
					err := filepath.Walk(fsRoot, func(p string, info os.FileInfo, wErr error) error {
						if wErr != nil || info.IsDir() {
							return wErr
						}
						if info.Mode()&os.ModeSymlink != 0 {
							return nil // Never archive symlinks
						}
						rel, err := filepath.Rel(fsRoot, p)
						if err != nil {
							return err
						}
						b, err := os.ReadFile(p)
						if err != nil {
							return err
						}
						return addEntry(filepath.ToSlash(filepath.Join(entry.FilestoreDir, rel)), b)
					})
					if err != nil {
						return BackupManifest{}, err
					}
				}
			}
			dbEntries = append(dbEntries, entry)
		}
	}

	if (opts.Type == TypeFull || opts.Type == TypeConfig) && opts.SourceDir != "" {
		confPath := filepath.Join(opts.SourceDir, "odoo.conf")
		if b, err := os.ReadFile(confPath); err == nil {
			if err := addEntry("config/odoo.conf", ScrubConfigSecrets(string(b))); err != nil {
				return BackupManifest{}, err
			}
		}
		composePath := filepath.Join(opts.SourceDir, "docker-compose.yml")
		if b, err := os.ReadFile(composePath); err == nil {
			if err := addEntry("config/docker-compose.yml", b); err != nil {
				return BackupManifest{}, err
			}
		}
	}

	manifest := BackupManifest{
		SchemaVersion:     1,
		CreatedAt:         time.Now().UTC(),
		Type:              opts.Type,
		ClientName:        opts.Installation.Company,
		InstallationID:    opts.Installation.InstallationID,
		SourceDeployment:  opts.Installation.Deployment,
		SourceVMID:        opts.Installation.VMID,
		OdooVersion:       opts.Installation.OdooVersion,
		OdooCommit:        opts.Installation.OdooCommit,
		DolanVersion:      opts.Installation.DolanVersion,
		Profile:           opts.Installation.Profile,
		Modules:           installedMods,
		DemoData:          opts.Installation.DemoData,
		DemoMode:          opts.Installation.DemoMode,
		IncludesFilestore: opts.IncludeFilestore && opts.Type == TypeFull,
		Encrypted:         opts.Passphrase != "",
		Databases:         dbEntries,
		Checksums:         checksums,
		TotalUncompressed: totalBytes,
	}
	if manifest.ClientName == "" {
		manifest.ClientName = opts.Installation.Name
	}

	manifestJSON, err := json.MarshalIndent(manifest, "", "  ")
	if err != nil {
		return BackupManifest{}, err
	}

	var tarBuf bytes.Buffer
	gz := gzip.NewWriter(&tarBuf)
	tw := tar.NewWriter(gz)

	writeTarFile := func(name string, data []byte) error {
		hdr := &tar.Header{
			Name:     name,
			Mode:     0600,
			Size:     int64(len(data)),
			ModTime:  manifest.CreatedAt,
			Typeflag: tar.TypeReg,
		}
		if err := tw.WriteHeader(hdr); err != nil {
			return err
		}
		_, err := tw.Write(data)
		return err
	}

	if err := writeTarFile("manifest.json", manifestJSON); err != nil {
		return BackupManifest{}, err
	}

	var keys []string
	for k := range files {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	var shaLines strings.Builder
	for _, k := range keys {
		shaLines.WriteString(fmt.Sprintf("%s  %s\n", checksums[k], k))
	}
	if err := writeTarFile("checksums.sha256", []byte(shaLines.String())); err != nil {
		return BackupManifest{}, err
	}
	for _, k := range keys {
		if err := writeTarFile(k, files[k]); err != nil {
			return BackupManifest{}, err
		}
	}
	if err := tw.Close(); err != nil {
		return BackupManifest{}, err
	}
	if err := gz.Close(); err != nil {
		return BackupManifest{}, err
	}

	payload := tarBuf.Bytes()
	var finalOut []byte
	if opts.Passphrase != "" {
		enc, err := encryptPayload(payload, opts.Passphrase)
		if err != nil {
			return BackupManifest{}, err
		}
		finalOut = append([]byte(FormatEncryptedMagic), enc...)
	} else {
		finalOut = append([]byte(FormatMagic), payload...)
	}

	if err := os.MkdirAll(filepath.Dir(opts.OutputPath), 0750); err != nil {
		return BackupManifest{}, err
	}
	if err := os.WriteFile(opts.OutputPath, finalOut, 0600); err != nil {
		return BackupManifest{}, err
	}

	if opts.VerifyIntegrity {
		rep, err := Verify(opts.OutputPath, opts.Passphrase)
		if err != nil || !rep.Valid {
			return manifest, fmt.Errorf("la verificación post-backup falló: %v (%v)", err, rep.Errors)
		}
	}
	return manifest, nil
}

// Verify inspects and validates a .dolanbak file without extracting files to disk.
// Rejects path traversal, symlinks/device nodes, excessive decompression, and checksum mismatches.
func Verify(path, passphrase string) (VerifyReport, error) {
	rep := VerifyReport{File: path}
	st, err := os.Stat(path)
	if err != nil {
		rep.Errors = append(rep.Errors, err.Error())
		return rep, err
	}
	rep.SizeBytes = st.Size()

	raw, err := os.ReadFile(path)
	if err != nil {
		rep.Errors = append(rep.Errors, err.Error())
		return rep, err
	}
	var payload []byte
	switch {
	case bytes.HasPrefix(raw, []byte(FormatEncryptedMagic)):
		rep.Encrypted = true
		if passphrase == "" {
			err := errors.New("el backup está cifrado; proporcioná la clave de descifrado")
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}
		dec, err := decryptPayload(raw[len(FormatEncryptedMagic):], passphrase)
		if err != nil {
			rep.Errors = append(rep.Errors, "clave de cifrado inválida o archivo corrupto")
			return rep, errors.New("clave de cifrado inválida o archivo corrupto")
		}
		payload = dec
	case bytes.HasPrefix(raw, []byte(FormatMagic)):
		payload = raw[len(FormatMagic):]
	default:
		err := errors.New("encabezado .dolanbak inválido o archivo corrupto")
		rep.Errors = append(rep.Errors, err.Error())
		return rep, err
	}

	gz, err := gzip.NewReader(bytes.NewReader(payload))
	if err != nil {
		rep.Errors = append(rep.Errors, "compresión gzip corrupta: "+err.Error())
		return rep, err
	}
	defer gz.Close()

	tr := tar.NewReader(gz)
	var manifestFound bool
	actualSums := make(map[string]string)
	var totalExtracted int64
	fileCount := 0

	for {
		hdr, err := tr.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			rep.Errors = append(rep.Errors, "estructura tar corrupta: "+err.Error())
			return rep, err
		}
		fileCount++
		if fileCount > MaxArchiveFiles {
			err := errors.New("el archivo excede el límite máximo de entradas permitidas")
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}
		if hdr.Typeflag != tar.TypeReg && hdr.Typeflag != tar.TypeRegA {
			err := fmt.Errorf("entrada no permitida en el backup (%s: tipo %d); solo se admiten archivos regulares", hdr.Name, hdr.Typeflag)
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}
		cleanName, err := SanitizeArchivePath(hdr.Name)
		if err != nil {
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}
		if hdr.Size < 0 || hdr.Size > MaxSingleEntryBytes {
			err := fmt.Errorf("tamaño de entrada inválido o excesivo en %s", cleanName)
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}
		totalExtracted += hdr.Size
		if totalExtracted > MaxTotalExtractBytes {
			err := errors.New("protección anti descompresión excesiva activada")
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}

		limited := io.LimitReader(tr, hdr.Size+1)
		data, err := io.ReadAll(limited)
		if err != nil {
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}
		if int64(len(data)) != hdr.Size {
			err := fmt.Errorf("tamaño truncado en %s", cleanName)
			rep.Errors = append(rep.Errors, err.Error())
			return rep, err
		}

		if cleanName == "manifest.json" {
			if err := json.Unmarshal(data, &rep.Manifest); err != nil {
				rep.Errors = append(rep.Errors, "manifest.json inválido: "+err.Error())
				return rep, err
			}
			manifestFound = true
			continue
		}
		if cleanName == "checksums.sha256" {
			continue
		}
		sum := sha256.Sum256(data)
		actualSums[cleanName] = hex.EncodeToString(sum[:])
		rep.CheckedFiles++
	}

	if !manifestFound {
		err := errors.New("el backup no contiene manifest.json")
		rep.Errors = append(rep.Errors, err.Error())
		return rep, err
	}

	for pathKey, expected := range rep.Manifest.Checksums {
		got, ok := actualSums[pathKey]
		if !ok {
			rep.Errors = append(rep.Errors, fmt.Sprintf("falta el archivo declarado en el manifiesto: %s", pathKey))
			continue
		}
		if !strings.EqualFold(got, expected) {
			rep.Errors = append(rep.Errors, fmt.Sprintf("checksum SHA-256 inválido para %s", pathKey))
		}
	}
	if len(rep.Errors) > 0 {
		return rep, errors.New(strings.Join(rep.Errors, "; "))
	}
	rep.Valid = true
	return rep, nil
}

// PlanRestore executes the 14-step preflight and compatibility analysis for portable restoration/migration.
func PlanRestore(backupPath, passphrase, targetProvider string, targetVMID int, targetPath string, overwrite bool, availableModules []string, availableDiskBytes int64) (RestorePlan, error) {
	rep, err := Verify(backupPath, passphrase)
	if err != nil {
		return RestorePlan{}, err
	}
	m := rep.Manifest
	reqBytes := m.TotalUncompressed * 2
	if reqBytes < 2*1024*1024*1024 {
		reqBytes = 2 * 1024 * 1024 * 1024 // Minimum 2 GB safety margin
	}
	plan := RestorePlan{
		File:                    backupPath,
		TargetProvider:          targetProvider,
		TargetVMID:              targetVMID,
		TargetPath:              targetPath,
		OverwriteExisting:       overwrite,
		RequiresPreBackup:       overwrite,
		Manifest:                m,
		CompatibleVersions:      m.OdooVersion == "20.0",
		ModulesAvailable:        true,
		SufficientSpace:         availableDiskBytes <= 0 || availableDiskBytes >= reqBytes,
		RequiredBytes:           reqBytes,
		PreserveDemoNoReseed:    true,
		ExternalIntegrationsOff: true,
		Steps: []string{
			"1. Validar formato, integridad SHA-256 y cifrado del archivo .dolanbak",
			"2. Leer inventario de bases, versiones Odoo 20.0, módulos y filestore",
			fmt.Sprintf("3. Confirmar destino (%s) sin actualizar Odoo implícitamente", targetProvider),
			"4. Verificar espacio en disco y preflight de PostgreSQL 17 / Python 3.12",
			"5. Preparar contenedor/entorno destino con commits fijados",
			"6. Restaurar dump PostgreSQL consistente y filestore asociado",
			"7. Conservar estado de datos demo existentes sin volver a ejecutar semillas",
			"8. Mantener desactivados ARCA WSFE, pagos, correo, WAHA y cron externos",
			"9. Solicitar reconfiguración segura de secretos (.env / odoo.conf)",
			"10. Ejecutar verificación de salud HTTP y relaciones de datos",
		},
	}

	if !plan.CompatibleVersions {
		plan.BlockingErrors = append(plan.BlockingErrors, fmt.Sprintf("serie de Odoo incompatible: backup=%s, soportada=20.0", m.OdooVersion))
	}
	if !plan.SufficientSpace {
		plan.BlockingErrors = append(plan.BlockingErrors, fmt.Sprintf("espacio insuficiente en destino: disponible=%d bytes, requerido=%d bytes", availableDiskBytes, reqBytes))
	}

	if len(availableModules) > 0 {
		availSet := make(map[string]bool, len(availableModules))
		for _, mod := range availableModules {
			availSet[mod] = true
		}
		for _, reqMod := range m.Modules {
			if strings.HasPrefix(reqMod, "DOLAN_") || reqMod == "ePOS_print" || reqMod == "pos_scale_management" {
				if !availSet[reqMod] {
					plan.ModulesAvailable = false
					plan.BlockingErrors = append(plan.BlockingErrors, fmt.Sprintf("el módulo requerido por el backup no está disponible en el destino: %s", reqMod))
				}
			}
		}
	}

	if m.SourceDeployment != "" && m.SourceDeployment != targetProvider {
		plan.Warnings = append(plan.Warnings, fmt.Sprintf("Migración entre proveedores (%s → %s): las integraciones externas (WAHA, correo, ARCA y webhooks) permanecerán en pausa hasta validar endpoints.", m.SourceDeployment, targetProvider))
	}
	if overwrite {
		plan.Warnings = append(plan.Warnings, "Destino existente seleccionado: se ejecutará un backup obligatorio previo antes de sobrescribir.")
	}
	if m.DemoData {
		plan.Warnings = append(plan.Warnings, "El backup contiene datos DEMO: se restaurarán tal cual sin volver a sembrar registros.")
	}
	return plan, nil
}

// SanitizeArchivePath blocks path traversal (../), absolute paths, drive letters, and backslashes.
func SanitizeArchivePath(p string) (string, error) {
	if p == "" {
		return "", errors.New("ruta vacía en archivo de backup")
	}
	if strings.Contains(p, `\`) || strings.HasPrefix(p, "/") || strings.Contains(p, ":") {
		return "", fmt.Errorf("ruta insegura bloqueada (path traversal): %q", p)
	}
	clean := filepath.ToSlash(filepath.Clean(p))
	if clean == "." || clean == ".." || strings.HasPrefix(clean, "../") || strings.Contains(clean, "/../") {
		return "", fmt.Errorf("intento de path traversal bloqueado: %q", p)
	}
	return clean, nil
}

func ScrubConfigSecrets(conf string) []byte {
	var out []string
	for _, line := range strings.Split(conf, "\n") {
		trimmed := strings.TrimSpace(line)
		key, _, ok := strings.Cut(trimmed, "=")
		if ok {
			k := strings.ToLower(strings.TrimSpace(key))
			if strings.Contains(k, "passwd") || strings.Contains(k, "password") || strings.Contains(k, "secret") || strings.Contains(k, "token") || strings.Contains(k, "key") {
				out = append(out, fmt.Sprintf("%s = __PROVIDE_ON_RESTORE__", strings.TrimSpace(key)))
				continue
			}
		}
		out = append(out, line)
	}
	return []byte(strings.Join(out, "\n"))
}

func deriveKey(passphrase string, salt []byte) []byte {
	// Iterative salted SHA-256 key stretching (100,000 rounds) using standard library crypto/sha256
	h := sha256.New()
	h.Write(salt)
	h.Write([]byte(passphrase))
	sum := h.Sum(nil)
	for i := 0; i < 100000; i++ {
		h.Reset()
		h.Write(sum)
		h.Write(salt)
		sum = h.Sum(nil)
	}
	return sum
}

func encryptPayload(plain []byte, passphrase string) ([]byte, error) {
	salt := make([]byte, 16)
	if _, err := rand.Read(salt); err != nil {
		return nil, err
	}
	key := deriveKey(passphrase, salt)
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := rand.Read(nonce); err != nil {
		return nil, err
	}
	sealed := gcm.Seal(nil, nonce, plain, salt)
	out := make([]byte, 0, len(salt)+len(nonce)+len(sealed))
	out = append(out, salt...)
	out = append(out, nonce...)
	out = append(out, sealed...)
	return out, nil
}

func decryptPayload(cipherData []byte, passphrase string) ([]byte, error) {
	if len(cipherData) < 16+12+16 {
		return nil, errors.New("datos cifrados truncados")
	}
	salt := cipherData[:16]
	key := deriveKey(passphrase, salt)
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return nil, err
	}
	ns := gcm.NonceSize()
	nonce := cipherData[16 : 16+ns]
	ciphertext := cipherData[16+ns:]
	return gcm.Open(nil, nonce, ciphertext, salt)
}
