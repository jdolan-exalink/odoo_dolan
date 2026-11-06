package main

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

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/core"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/engine"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/platform"
	"github.com/jdolan-exalink/odoo_dolan/installer/internal/tui"
)

var version = "dev"

func main() {
	if err := run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}

func run(args []string) error {
	if len(args) == 0 {
		return usageError()
	}
	if args[0] == "--version" || args[0] == "version" {
		fmt.Printf("dolan-installer %s (%s/%s)\n", version, runtime.GOOS, runtime.GOARCH)
		return nil
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	switch args[0] {
	case "install":
		return runInstall(ctx, args[1:])
	case "doctor":
		return runDoctor(ctx, args[1:])
	case "list":
		return runList(args[1:])
	case "status":
		return runStatus(ctx, args[1:])
	case "logs":
		return runLogs(ctx, args[1:])
	case "help", "--help", "-h":
		printUsage()
		return nil
	default:
		return fmt.Errorf("subcomando desconocido %q; ejecutá dolan-installer --help", args[0])
	}
}

func runInstall(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("install", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	configFile := fs.String("config", "", "Archivo JSON para automatización")
	nonInteractive := fs.Bool("non-interactive", false, "No abrir la TUI")
	dryRun := fs.Bool("dry-run", false, "Mostrar el plan sin modificar el host")
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de despliegues")
	name := fs.String("name", "", "Nombre corto del proyecto")
	profile := fs.String("profile", "", "core, comercio, servicios, full o custom")
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
	if visited(fs, "name") {
		cfg.ProjectName = *name
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
		// Secrets are collected as masked fields by the wizard; they are never passed in CLI arguments.
	}
	if *dryRun {
		args, err := runner.Plan(cfg)
		if err != nil {
			return err
		}
		fmt.Println("Plan de instalación (sin cambios al host):")
		fmt.Printf("Sistema: %s/%s\nPerfil: %s\nProyecto: %s\nBase: %s\nPuerto: %d\n", runtime.GOOS, runtime.GOARCH, cfg.Profile, cfg.DeploymentPath(), cfg.InitDB, cfg.Port)
		fmt.Printf("Motor Bash: %s\nArgumentos sin secretos: %s\n", filepath.Join(repo, "crear_odoo20.sh"), strings.Join(args, " "))
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

func runDoctor(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("doctor", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	port := fs.Int("port", 8070, "Puerto a revisar")
	asJSON := fs.Bool("json", false, "Salida JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	r := platform.Doctor(ctx, *port)
	if *asJSON {
		e := json.NewEncoder(os.Stdout)
		e.SetIndent("", "  ")
		_ = e.Encode(r)
	} else {
		fmt.Printf("DOLAN Installer · diagnóstico\n%s · %s · %d CPU\n\n", r.OS, r.Architecture, r.CPU)
		for _, c := range r.Checks {
			fmt.Printf("%-18s %-8s %s\n", c.Name, strings.ToUpper(c.Status), c.Detail)
		}
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
	if err := fs.Parse(args); err != nil {
		return err
	}
	items, err := engine.Discover(*root)
	if err != nil {
		return err
	}
	if len(items) == 0 {
		fmt.Printf("No encontré despliegues Compose en %s\n", *root)
		return nil
	}
	for _, d := range items {
		managed := "manual/no gestionado"
		if d.Managed {
			managed = d.Manifest.Profile + " · DB " + d.Manifest.Database
		}
		fmt.Printf("%-24s %-32s %s\n%s\n", d.Name, managed, d.Path, stateHint(d))
	}
	return nil
}

func runStatus(ctx context.Context, args []string) error {
	fs := flag.NewFlagSet("status", flag.ContinueOnError)
	fs.SetOutput(io.Discard)
	root := fs.String("root", core.DefaultProjectRoot(), "Directorio base de despliegues")
	name := fs.String("name", "", "Nombre de la instalación")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *name == "" {
		return errors.New("status requiere --name")
	}
	d, err := engine.Resolve(*root, *name)
	if err != nil {
		return err
	}
	s := engine.GetStatus(ctx, d)
	fmt.Printf("Instalación: %s\nRuta: %s\n", d.Name, d.Path)
	if d.Managed {
		fmt.Printf("Empresa: %s · Perfil: %s · Base: %s\n", d.Manifest.Company, d.Manifest.Profile, d.Manifest.Database)
		if s.HTTP != "" {
			fmt.Printf("HTTP: %s · %s\n", s.HTTP, s.HTTPStatus)
		}
	} else {
		fmt.Println("Manifiesto: no gestionada por DOLAN Installer")
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
	tail := fs.Int("tail", 100, "Cantidad de líneas por servicio")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *name == "" {
		return errors.New("logs requiere --name")
	}
	d, err := engine.Resolve(*root, *name)
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

func usageError() error { printUsage(); return errors.New("indicá un subcomando") }
func printUsage() {
	fmt.Printf(`DOLAN Installer 2.0 · CLI/TUI

Uso: dolan-installer <comando> [opciones]

Comandos:
  install       Asistente TUI o instalación declarativa
  doctor        Diagnóstico sin cambios (admite --json)
  list          Descubre proyectos Docker Compose en la ruta base
  status        Estado de servicios y endpoint HTTP
  logs          Logs Compose con redacción de secretos
  --version     Versión y plataforma

Instalación interactiva:
  dolan-installer install

Automatización (el JSON no admite contraseñas; se reciben por entorno):
  DOLAN_ADMIN_LOGIN_PASSWORD='...' dolan-installer install --config install.json --non-interactive

La instalación requiere Linux con Bash, Docker Engine y Compose. Use ` + "`doctor`" + ` antes de instalar.
Windows local/SSH, backup/restore/update de Odoo y diagnósticos remotos no están habilitados en este MVP.
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
		if entry.IsDir() && strings.HasPrefix(entry.Name(), "DOLAN_") {
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
