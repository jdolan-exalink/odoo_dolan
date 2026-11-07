package cli

import (
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"os"
	"os/signal"
	"path/filepath"
	"runtime"
	"strings"
	"syscall"
	"time"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/backup"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/engine"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/jobs"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/packages"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/platform"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/state"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/tui"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/updates"
)

var Version = "2.0.0"

func Run(args []string) error {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	if len(args) == 0 {
		// If interactive TTY, launch Manager 2.0 TUI Home screen (7.1); otherwise show usage
		repo, _ := findRepoRoot()
		if isInteractiveTTY() {
			return tui.RunManagerTUI(ctx, core.DefaultProjectRoot(), repo)
		}
		return usageError()
	}

	if args[0] == "--version" || args[0] == "version" {
		fmt.Printf("dolan %s (%s/%s)\n", Version, runtime.GOOS, runtime.GOARCH)
		return nil
	}

	switch args[0] {
	case "tui":
		repo, _ := findRepoRoot()
		return tui.RunManagerTUI(ctx, core.DefaultProjectRoot(), repo)
	case "install":
		return runInstall(ctx, args[1:])
	case "doctor", "diagnostics":
		return runDiagnostics(ctx, args[1:])
	case "list":
		return runList(args[1:])
	case "adopt":
		return runAdopt(args[1:])
	case "status":
		return runStatus(ctx, args[1:])
	case "logs":
		return runLogs(ctx, args[1:])
	case "backup":
		return runBackup(ctx, args[1:])
	case "restore":
		return runRestore(ctx, args[1:])
	case "packages":
		return runPackages(ctx, args[1:])
	case "update":
		return runUpdate(ctx, args[1:])
	case "jobs":
		return runJobs(args[1:])
	case "help", "--help", "-h":
		printUsage()
		return nil
	default:
		return fmt.Errorf("subcomando desconocido %q; ejecutá dolan --help", args[0])
	}
}

func runInstall(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("install", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	configFile := fs.String("config", "", "Archivo JSON para automatización")
	nonInteractive := fs.Bool("non-interactive", false, "No abrir la TUI")
	dryRun := fs.Bool("dry-run", false, "Mostrar el plan sin modificar el host")
	asJSON := fs.Bool("json", false, "Salida JSON del plan")
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de despliegues")
	target := fs.String("target", "docker", "proxmox-lxc, docker, linux-native o windows")
	vmid := fs.Int("vmid", 105, "VMID para Proxmox LXC")
	name := fs.String("name", "", "Nombre corto del proyecto")
	resetExisting := fs.String("reset-existing", "", "Borrar un deployment existente con este mismo nombre después de confirmar el plan")
	profile := fs.String("profile", "", "basico/core, comercio, servicios, completo/full o custom")
	modules := fs.String("modules", "", "IDs DOLAN separados por coma para custom")
	company := fs.String("company", "", "Razón social inicial")
	short := fs.String("company-short", "", "Nombre corto de carpeta y base")
	cuit := fs.String("cuit", "", "CUIT con o sin guiones")
	address := fs.String("address", "", "Domicilio fiscal")
	city := fs.String("city", "", "Localidad")
	responsibility := fs.String("responsibility", "", "Responsable Inscripto, Monotributista o Exento")
	billingPOS := fs.Int("billing-pos", 0, "Punto de venta de facturación")
	posPOS := fs.Int("pos-pos", 0, "Punto de venta de POS")
	adminEmail := fs.String("admin-email", "", "Correo/login del administrador")
	adminName := fs.String("admin-name", "", "Nombre visible del administrador")
	port := fs.Int("port", 0, "Puerto HTTP publicado")
	callbackPort := fs.Int("callback-port", 0, "Puerto de callback OAuth loopback")
	demoData := fs.Bool("demo-data", false, "Instalar datos de demostración de Odoo en los módulos")
	demoMode := fs.String("demo-mode", "", "none, odoo o dolan")
	if err := fs.Parse(args); err != nil {
		return err
	}

	cfg := core.NewConfig()
	if *configFile != "" {
		f, err := os.Open(*configFile)
		if err != nil {
			return fmt.Errorf("abrir configuración: %w", err)
		}
		decoder := json.NewDecoder(f)
		decoder.DisallowUnknownFields()
		err = decoder.Decode(&cfg)
		_ = f.Close()
		if err != nil {
			return fmt.Errorf("leer configuración JSON: %w", err)
		}
	}
	if visited(fs, "root") {
		cfg.ProjectRoot = *root
	}
	if visited(fs, "target") {
		cfg.Target = core.DeploymentTarget(*target)
	}
	if visited(fs, "vmid") {
		cfg.LXC.VMID = *vmid
	}
	if visited(fs, "name") {
		cfg.ProjectName = *name
	}
	if visited(fs, "reset-existing") {
		cfg.ResetExistingName = *resetExisting
		if cfg.ProjectName == "" {
			cfg.ProjectName = *resetExisting
		}
		if cfg.CompanyShort == "" {
			cfg.CompanyShort = *resetExisting
		}
	}
	if visited(fs, "profile") {
		cfg.Profile = core.Profile(*profile)
	}
	if visited(fs, "modules") {
		cfg.Modules = split(*modules)
	}
	if visited(fs, "company") {
		cfg.Company = *company
	}
	if visited(fs, "company-short") {
		cfg.CompanyShort = *short
	}
	if visited(fs, "cuit") {
		cfg.CUIT = *cuit
	}
	if visited(fs, "address") {
		cfg.Address = *address
	}
	if visited(fs, "city") {
		cfg.City = *city
	}
	if visited(fs, "responsibility") {
		cfg.Responsibility = *responsibility
	}
	if visited(fs, "billing-pos") {
		cfg.BillingPOS = *billingPOS
	}
	if visited(fs, "pos-pos") {
		cfg.POSPOS = *posPOS
	}
	if visited(fs, "admin-email") {
		cfg.AdminEmail = *adminEmail
	}
	if visited(fs, "admin-name") {
		cfg.AdminName = *adminName
	}
	if visited(fs, "port") {
		cfg.Port = *port
	}
	if visited(fs, "callback-port") {
		cfg.CallbackPort = *callbackPort
	}
	if visited(fs, "demo-data") {
		cfg.DemoData = *demoData
		if *demoData && cfg.DemoMode == core.DemoNone {
			cfg.DemoMode = core.DemoOdoo
		}
	}
	if visited(fs, "demo-mode") {
		cfg.DemoMode = core.DemoMode(*demoMode)
		cfg.DemoData = cfg.DemoMode != core.DemoNone
	}
	cfg.AdminPassword = os.Getenv("DOLAN_ADMIN_LOGIN_PASSWORD")
	cfg.MasterPassword = os.Getenv("DOLAN_DB_MASTER_PASSWORD")
	cfg.Normalize()

	repo, err := findRepoRoot()
	if err != nil {
		return err
	}
	modulesAvailable, err := discoverModules(filepath.Join(repo, "addons"))
	if err != nil {
		return err
	}
	runner := engine.Runner{RepoRoot: repo}
	if !*nonInteractive && !*dryRun {
		cfg, err = tui.RunWizard(cfg, modulesAvailable)
		if err != nil {
			return err
		}
	}
	if *dryRun {
		argsPlan, err := runner.Plan(cfg)
		if err != nil {
			return err
		}
		if *asJSON {
			return writeJSON(map[string]any{
				"system":          runtime.GOOS + "/" + runtime.GOARCH,
				"target":          cfg.Target,
				"vmid":            cfg.LXC.VMID,
				"profile":         core.CanonicalProfile(cfg.Profile),
				"deployment_path": cfg.DeploymentPath(),
				"database":        cfg.InitDB,
				"demo_mode":       cfg.DemoMode,
				"port":            cfg.Port,
				"engine_args":     argsPlan,
			})
		}
		fmt.Println("Plan de instalación (sin cambios al host):")
		fmt.Printf("Sistema: %s/%s\nDestino: %s\nPerfil: %s\nProyecto: %s\nBase: %s\nModo Demo: %s\nPuerto: %d\n",
			runtime.GOOS, runtime.GOARCH, cfg.Target, cfg.Profile, cfg.DeploymentPath(), cfg.InitDB, cfg.DemoMode, cfg.Port)
		if cfg.ResetExistingName != "" {
			fmt.Printf("ATENCIÓN: al confirmar se eliminará el deployment existente %q, sus datos, volúmenes e imágenes locales.\n", cfg.ResetExistingName)
		}
		fmt.Printf("Motor Bash: %s\nArgumentos sin secretos: %s\n", filepath.Join(repo, "crear_odoo20.sh"), strings.Join(argsPlan, " "))
		return nil
	}
	if *nonInteractive {
		if err := cfg.Validate(true); err != nil {
			return err
		}
		if cfg.AdminPassword == "" {
			return errors.New("en modo no interactivo definí DOLAN_ADMIN_LOGIN_PASSWORD en el entorno; no se aceptan contraseñas en flags")
		}
	}
	if !*nonInteractive && cfg.AdminPassword == "" {
		return errors.New("la TUI no conservó la contraseña inicial; volvé a completar el asistente")
	}
	return tui.RunInstall(ctx, cfg, runner)
}

func runDiagnostics(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("diagnostics", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	port := fs.Int("port", 8070, "Puerto a revisar")
	installation := fs.String("installation", "", "ID, nombre o VMID de la instalación")
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de despliegues")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	r := platform.Doctor(ctx, *port)
	if *installation != "" {
		if d, err := engine.Resolve(*root, *installation); err == nil {
			st := engine.GetStatus(ctx, d)
			statusVal := "ok"
			detail := fmt.Sprintf("perfil=%s db=%s demo=%v", d.Manifest.Profile, d.Manifest.Database, d.Manifest.DemoData)
			if st.Error != "" {
				statusVal = "warning"
				detail += " (" + st.Error + ")"
			}
			r.Checks = append(r.Checks, platform.Check{
				Name:   "instalación " + d.Name,
				Status: statusVal,
				Detail: detail,
			})
		}
	}
	if *asJSON {
		return writeJSON(r)
	}
	fmt.Printf("DOLAN Manager 2.0 · Diagnóstico\n%s · %s · %d CPU\n\n", r.OS, r.Architecture, r.CPU)
	for _, c := range r.Checks {
		fmt.Printf("%-20s %-8s %s\n", c.Name, strings.ToUpper(c.Status), c.Detail)
	}
	if !platform.Ready(r) {
		return errors.New("hay bloqueos; el diagnóstico no modificó el sistema")
	}
	return nil
}

func runList(args []string) error {
	fs := flag.NewFlagSet("list", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de despliegues")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	items, err := engine.Discover(*root)
	if err != nil {
		return err
	}
	if *asJSON {
		if items == nil {
			items = []engine.Deployment{}
		}
		return writeJSON(items)
	}
	if len(items) == 0 {
		fmt.Printf("No encontré despliegues en %s\n", *root)
		return nil
	}
	for _, d := range items {
		managed := "manual/no gestionado (adoptable con `dolan adopt`)"
		if d.Managed {
			demoSuffix := ""
			if d.Manifest.DemoData {
				demoSuffix = " [DEMO]"
			}
			managed = d.Manifest.Profile + demoSuffix + " · DB " + d.Manifest.Database
		}
		fmt.Printf("%-24s %-36s %s\n%s\n", d.Name, managed, d.Path, stateHint(d))
	}
	return nil
}

func runAdopt(args []string) error {
	fs := flag.NewFlagSet("adopt", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base")
	name := fs.String("installation", "", "Nombre de la instalación a adoptar")
	company := fs.String("company", "", "Razón social")
	profile := fs.String("profile", "comercio", "Perfil de la instalación")
	db := fs.String("db", "", "Base de datos principal")
	port := fs.Int("port", 8070, "Puerto HTTP")
	confirm := fs.Bool("yes", false, "Confirmar adopción explícita sin reinstalar")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *name == "" {
		return errors.New("adopt requiere --installation <nombre>")
	}
	if !*confirm {
		return errors.New("adopt requiere confirmación explícita (--yes) para registrar el manifiesto sin modificar datos")
	}
	d, err := engine.Adopt(*root, *name, *company, *profile, *db, *port)
	if err != nil {
		return err
	}
	if *asJSON {
		return writeJSON(d)
	}
	fmt.Printf("Instalación %q adoptada con éxito (ID: %s).\n", d.Name, d.Manifest.InstallationID)
	return nil
}

func runStatus(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("status", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de despliegues")
	name := fs.String("name", "", "Nombre de la instalación")
	installation := fs.String("installation", "", "Alias de --name o VMID")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	target := *name
	if target == "" {
		target = *installation
	}
	if target == "" {
		// Global host + installations status summary when no specific installation is passed
		host := platform.DetectHostEnvironment()
		items, _ := engine.Discover(*root)
		if *asJSON {
			return writeJSON(map[string]any{
				"host":          host,
				"installations": items,
			})
		}
		fmt.Printf("Entorno: %s\nInstalaciones detectadas en %s: %d\n", host.HeaderSummary(), *root, len(items))
		return nil
	}
	d, err := engine.Resolve(*root, target)
	if err != nil {
		return err
	}
	s := engine.GetStatus(ctx, d)
	if *asJSON {
		return writeJSON(s)
	}
	fmt.Printf("Instalación: %s\nRuta: %s\n", d.Name, d.Path)
	if d.Managed {
		demoTag := "No"
		if d.Manifest.DemoData {
			demoTag = fmt.Sprintf("Sí (%s - DEMO)", d.Manifest.DemoMode)
		}
		fmt.Printf("Empresa: %s · Perfil: %s · Base: %s · Datos demo: %s\n", d.Manifest.Company, d.Manifest.Profile, d.Manifest.Database, demoTag)
		if s.HTTP != "" {
			fmt.Printf("HTTP: %s · %s\n", s.HTTP, s.HTTPStatus)
		}
	} else {
		fmt.Println("Manifiesto: no gestionada por DOLAN Manager")
	}
	if s.Error != "" {
		return fmt.Errorf("no se obtuvo estado de Compose: %s", s.Error)
	}
	if len(s.Containers) == 0 {
		fmt.Println("Contenedores: ninguno iniciado")
	}
	for _, c := range s.Containers {
		fmt.Printf("%-20s %-14s %s\n", c.Service, c.State, c.Status)
	}
	return nil
}

func runLogs(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("logs", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de despliegues")
	name := fs.String("name", "", "Nombre de la instalación")
	installation := fs.String("installation", "", "Alias de --name")
	tail := fs.Int("tail", 100, "Cantidad de líneas por servicio")
	if err := fs.Parse(args); err != nil {
		return err
	}
	target := *name
	if target == "" {
		target = *installation
	}
	if target == "" {
		return errors.New("logs requiere --name o --installation")
	}
	d, err := engine.Resolve(*root, target)
	if err != nil {
		return err
	}
	lines, err := engine.ReadLogs(ctx, d, *tail)
	if err != nil {
		return err
	}
	for _, line := range lines {
		fmt.Println(line)
	}
	return nil
}

func runBackup(_ context.Context, args []string) error {
	if len(args) == 0 {
		return errors.New("indicá una acción de backup: list, create o verify")
	}
	sub := args[0]
	fs := flag.NewFlagSet("backup "+sub, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de instalaciones")
	installation := fs.String("installation", "", "Nombre, ID o VMID de la instalación")
	destDir := fs.String("dest", "", "Directorio o archivo destino para el backup")
	file := fs.String("file", "", "Archivo .dolanbak")
	bType := fs.String("type", "full", "Tipo de backup: full, db o config")
	includeFS := fs.Bool("filestore", true, "Incluir filestore")
	verifyAfter := fs.Bool("verify", true, "Verificar integridad al finalizar")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	passphrase := os.Getenv("DOLAN_BACKUP_PASSPHRASE")

	switch sub {
	case "list":
		searchDir := *destDir
		if searchDir == "" {
			searchDir = filepath.Join(*root, "backups")
		}
		entries, err := os.ReadDir(searchDir)
		if os.IsNotExist(err) {
			if *asJSON {
				return writeJSON([]string{})
			}
			fmt.Printf("No hay backups en %s\n", searchDir)
			return nil
		}
		if err != nil {
			return err
		}
		var found []string
		for _, e := range entries {
			if !e.IsDir() && strings.HasSuffix(e.Name(), ".dolanbak") {
				found = append(found, filepath.Join(searchDir, e.Name()))
			}
		}
		if *asJSON {
			return writeJSON(found)
		}
		for _, f := range found {
			fmt.Println(f)
		}
		return nil

	case "create":
		if *installation == "" {
			return errors.New("backup create requiere --installation <id|nombre|vmid>")
		}
		var instManifest state.Manifest
		var srcDir string
		if d, err := engine.Resolve(*root, *installation); err == nil {
			instManifest = d.Manifest
			srcDir = d.Path
			if instManifest.Name == "" {
				instManifest.Name = d.Name
			}
		} else {
			// Support creating a logical portable backup for an LXC VMID or named target
			instManifest = state.Manifest{
				Name:        *installation,
				Company:     *installation,
				Deployment:  "proxmox-lxc",
				OdooVersion: "20.0",
				Profile:     "comercio",
				Database:    "odoo_" + core.Slugify(*installation),
			}
		}
		outPath := *file
		if outPath == "" {
			baseDir := *destDir
			if baseDir == "" {
				baseDir = filepath.Join(*root, "backups")
			}
			outPath = filepath.Join(baseDir, fmt.Sprintf("%s-%s.dolanbak", instManifest.Name, time.Now().UTC().Format("20060102-150405")))
		}
		m, err := backup.Create(backup.CreateOptions{
			Installation:     instManifest,
			SourceDir:        srcDir,
			OutputPath:       outPath,
			Type:             backup.BackupType(*bType),
			IncludeFilestore: *includeFS,
			VerifyIntegrity:  *verifyAfter,
			Passphrase:       passphrase,
		})
		if err != nil {
			return err
		}
		if *asJSON {
			return writeJSON(map[string]any{
				"file":     outPath,
				"manifest": m,
			})
		}
		fmt.Printf("Backup creado y verificado: %s\n", outPath)
		return nil

	case "verify":
		if *file == "" {
			return errors.New("backup verify requiere --file <archivo.dolanbak>")
		}
		rep, err := backup.Verify(*file, passphrase)
		if *asJSON {
			_ = writeJSON(rep)
		}
		if err != nil {
			return err
		}
		if !*asJSON {
			fmt.Printf("Backup válido: %s (%d archivos verificados, Odoo %s, perfil %s)\n",
				rep.File, rep.CheckedFiles, rep.Manifest.OdooVersion, rep.Manifest.Profile)
		}
		return nil
	default:
		return fmt.Errorf("subcomando de backup desconocido: %q", sub)
	}
}

func runRestore(_ context.Context, args []string) error {
	if len(args) == 0 {
		return errors.New("indicá plan o --file para restaurar")
	}
	sub := "run"
	subArgs := args
	if args[0] == "plan" || args[0] == "run" {
		sub = args[0]
		subArgs = args[1:]
	}
	fs := flag.NewFlagSet("restore "+sub, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	file := fs.String("file", "", "Archivo .dolanbak")
	target := fs.String("target", "proxmox-lxc", "Destino: lxc, proxmox-lxc, docker, linux-native")
	vmid := fs.Int("vmid", 110, "VMID destino en Proxmox")
	overwrite := fs.Bool("overwrite", false, "Sobrescribir instalación existente (requiere --yes y backup previo)")
	confirm := fs.Bool("yes", false, "Confirmar restauración")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(subArgs); err != nil {
		return err
	}
	if *file == "" {
		return errors.New("restore requiere --file <archivo.dolanbak>")
	}
	targetNorm := *target
	if targetNorm == "lxc" {
		targetNorm = "proxmox-lxc"
	}
	passphrase := os.Getenv("DOLAN_BACKUP_PASSPHRASE")
	plan, err := backup.PlanRestore(*file, passphrase, targetNorm, *vmid, "", *overwrite, packages.AllCatalogIDs(), 80*1024*1024*1024)
	if err != nil {
		return err
	}
	if sub == "plan" {
		if *asJSON {
			return writeJSON(plan)
		}
		fmt.Printf("Plan de restauración para %s -> %s:\n", plan.File, plan.TargetProvider)
		for _, step := range plan.Steps {
			fmt.Println("  " + step)
		}
		for _, w := range plan.Warnings {
			fmt.Println("  ! " + w)
		}
		if !plan.Ready() {
			return fmt.Errorf("preflight bloqueado: %s", strings.Join(plan.BlockingErrors, "; "))
		}
		return nil
	}
	if !plan.Ready() {
		return fmt.Errorf("restauración bloqueada por preflight: %s", strings.Join(plan.BlockingErrors, "; "))
	}
	if *overwrite && !*confirm {
		return errors.New("sobrescribir un destino existente requiere --yes y genera backup previo obligatorio")
	}
	if *asJSON {
		return writeJSON(map[string]any{
			"status": "ready_to_restore",
			"plan":   plan,
		})
	}
	fmt.Printf("Preflight aprobado para restaurar %s en %s.\n", plan.File, plan.TargetProvider)
	return nil
}

func runPackages(_ context.Context, args []string) error {
	if len(args) == 0 {
		return errors.New("indicá una acción para packages: list, plan o apply")
	}
	sub := args[0]
	fs := flag.NewFlagSet("packages "+sub, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base")
	installation := fs.String("installation", "", "ID, nombre o VMID de la instalación")
	profile := fs.String("profile", "", "Perfil objetivo (basico, servicios, comercio, completo)")
	addMods := fs.String("add", "", "Módulos a agregar separados por coma")
	removeMods := fs.String("remove", "", "Módulos a desinstalar separados por coma")
	planFile := fs.String("plan", "", "Archivo JSON de plan para apply")
	outPlan := fs.String("out", "", "Guardar plan en archivo JSON")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}

	var currentProfile = core.ProfileServices
	var currentMods = core.FindProfileInfo(core.ProfileServices).DolanModules
	if *installation != "" {
		if d, err := engine.Resolve(*root, *installation); err == nil && d.Managed {
			currentProfile = core.Profile(d.Manifest.Profile)
			if len(d.Manifest.Modules) > 0 {
				currentMods = d.Manifest.Modules
			} else {
				currentMods = core.FindProfileInfo(currentProfile).DolanModules
			}
		}
	}

	switch sub {
	case "list":
		instSet := make(map[string]bool)
		for _, m := range currentMods {
			instSet[m] = true
		}
		var list []packages.ModuleSpec
		for _, spec := range packages.Catalog {
			item := spec
			if instSet[item.ID] {
				item.State = packages.StateInstalled
			} else {
				item.State = packages.StateAvailable
			}
			list = append(list, item)
		}
		if *asJSON {
			return writeJSON(list)
		}
		fmt.Printf("Catálogo de paquetes (perfil actual: %s):\n", core.ProfileDisplayName(currentProfile))
		for _, m := range list {
			fmt.Printf("%-26s %-14s %s\n", m.ID, m.State, m.Title)
		}
		return nil

	case "plan":
		if *installation == "" {
			return errors.New("packages plan requiere --installation <id|nombre>")
		}
		plan, err := packages.PlanChange(*installation, currentProfile, core.Profile(*profile), currentMods, split(*addMods), split(*removeMods))
		if err != nil {
			if *asJSON {
				_ = writeJSON(plan)
			}
			return err
		}
		if *outPlan != "" {
			b, _ := json.MarshalIndent(plan, "", "  ")
			if err := os.WriteFile(*outPlan, append(b, '\n'), 0600); err != nil {
				return err
			}
		}
		if *asJSON {
			return writeJSON(plan)
		}
		fmt.Printf("Plan de paquetes para %s (%s -> %s):\n", plan.Installation, plan.CurrentProfile, plan.TargetProfile)
		fmt.Printf("Módulos a instalar (+%d): %s\n", len(plan.ToInstall), strings.Join(plan.ToInstall, ", "))
		for _, w := range plan.Warnings {
			fmt.Println("Aviso: " + w)
		}
		return nil

	case "apply":
		if *installation == "" {
			return errors.New("packages apply requiere --installation <id|nombre>")
		}
		var plan packages.ChangePlan
		if *planFile != "" {
			b, err := os.ReadFile(*planFile)
			if err != nil {
				return err
			}
			if err := json.Unmarshal(b, &plan); err != nil {
				return err
			}
		} else {
			var err error
			plan, err = packages.PlanChange(*installation, currentProfile, core.Profile(*profile), currentMods, split(*addMods), split(*removeMods))
			if err != nil {
				return err
			}
		}
		if d, err := engine.Resolve(*root, *installation); err == nil {
			d.Manifest.Profile = string(plan.TargetProfile)
			d.Manifest.Modules = plan.TargetModules
			if err := state.Write(d.Path, d.Manifest); err != nil {
				return err
			}
		}
		if *asJSON {
			return writeJSON(map[string]any{
				"applied": true,
				"plan":    plan,
			})
		}
		fmt.Printf("Cambios aplicados a %s: perfil=%s (+%d módulos).\n", *installation, plan.TargetProfile, len(plan.ToInstall))
		return nil
	default:
		return fmt.Errorf("subcomando de packages desconocido: %q", sub)
	}
}

func runUpdate(_ context.Context, args []string) error {
	sub := "check"
	subArgs := args
	if len(args) > 0 && !strings.HasPrefix(args[0], "-") {
		sub = args[0]
		subArgs = args[1:]
	}
	fs := flag.NewFlagSet("update "+sub, flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(subArgs); err != nil {
		return err
	}
	repo, _ := findRepoRoot()
	rep := updates.Check(repo, Version, "20.0.1")
	if *asJSON {
		return writeJSON(rep)
	}
	fmt.Printf("%-22s %-14s %-14s %s\n", "COMPONENTE", "ACTUAL", "DISPONIBLE", "NOTAS")
	for _, c := range rep.Components {
		fmt.Printf("%-22s %-14s %-14s %s\n", c.Component, c.Current, c.Available, c.Notes)
	}
	return nil
}

func runJobs(args []string) error {
	fs := flag.NewFlagSet("jobs", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	store := jobs.NewStore("")
	list, err := store.List()
	if err != nil {
		return err
	}
	if *asJSON {
		if list == nil {
			list = []jobs.Job{}
		}
		return writeJSON(list)
	}
	if len(list) == 0 {
		fmt.Println("No hay tareas registradas.")
		return nil
	}
	for _, j := range list {
		fmt.Printf("%-32s %-12s %3d%%  %s\n", j.ID, j.Status, j.OverallPercent, j.Title)
	}
	return nil
}

func writeJSON(v any) error {
	e := json.NewEncoder(os.Stdout)
	e.SetIndent("", "  ")
	return e.Encode(v)
}

func usageError() error { printUsage(); return errors.New("indicá un subcomando") }

func printUsage() {
	fmt.Printf(`DOLAN Manager 2.0 · CLI/TUI de Ciclo de Vida (Odoo CE 20)

Uso: dolan <comando> [opciones]

Comandos principales:
  tui                      Abrir el administrador interactivo TUI (pantallas 7.1–7.16)
  status                   Estado del host o de una instalación (--installation, --json)
  list                     Listar instalaciones detectadas (--root, --json)
  adopt                    Adoptar una instalación existente con consentimiento (--installation, --yes)
  install                  Asistente de nueva instalación o modo declarativo (--config, --non-interactive, --dry-run)
  backup list|create|verify Motor de backups lógicos portables .dolanbak (--installation, --file, --json)
  restore [plan|run]       Preflight de compatibilidad, restauración y migración (--file, --target, --json)
  packages list|plan|apply Gestión incremental de perfiles y módulos sin reinstalar (--installation, --profile, --json)
  update check             Verificar actualizaciones fijadas de Manager, Suite DOLAN y Odoo (--json)
  diagnostics | doctor     Diagnóstico de salud, recursos e integridad (--installation, --json)
  logs                     Logs con redacción automática de secretos (--name, --tail)
  jobs                     Tareas persistentes y reconexión SSH (--json)
  --version                Versión y plataforma
`)
}

func findRepoRoot() (string, error) {
	if override := os.Getenv("DOLAN_REPO_ROOT"); override != "" {
		return filepath.Abs(override)
	}
	wd, err := os.Getwd()
	if err != nil {
		return "", err
	}
	for dir := wd; ; dir = filepath.Dir(dir) {
		if _, err := os.Stat(filepath.Join(dir, "crear_odoo20.sh")); err == nil {
			return dir, nil
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
	}
	return "", errors.New("no encuentro crear_odoo20.sh y addons/DOLAN_*; ejecutá desde el repositorio o definí DOLAN_REPO_ROOT")
}

func discoverModules(addonsRoot string) ([]string, error) {
	entries, err := os.ReadDir(addonsRoot)
	if err != nil {
		return nil, err
	}
	var modules []string
	for _, entry := range entries {
		if entry.IsDir() {
			if _, err := os.Stat(filepath.Join(addonsRoot, entry.Name(), "__manifest__.py")); err == nil {
				modules = append(modules, entry.Name())
			}
		}
	}
	return modules, nil
}

func visited(fs *flag.FlagSet, name string) bool {
	found := false
	fs.Visit(func(f *flag.Flag) {
		if f.Name == name {
			found = true
		}
	})
	return found
}

func split(s string) []string {
	var out []string
	for _, item := range strings.Split(s, ",") {
		if item = strings.TrimSpace(item); item != "" {
			out = append(out, item)
		}
	}
	return out
}

func stateHint(d engine.Deployment) string {
	if d.Managed {
		return "Creado " + d.Manifest.CreatedAt.Format(time.DateTime)
	}
	return "Compose detectado; sin manifiesto de administrador"
}

func isInteractiveTTY() bool {
	fi, err := os.Stdin.Stat()
	if err != nil {
		return false
	}
	return (fi.Mode() & os.ModeCharDevice) != 0
}
