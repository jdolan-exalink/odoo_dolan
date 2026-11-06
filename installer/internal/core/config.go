package core

import (
	"errors"
	"fmt"
	"net/mail"
	"os"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
)

type Profile string

const (
	ProfileCore     Profile = "core"
	ProfileCommerce Profile = "comercio"
	ProfileServices Profile = "servicios"
	ProfileFull     Profile = "full"
	ProfileCustom   Profile = "custom"
)

var Profiles = []Profile{ProfileCore, ProfileCommerce, ProfileServices, ProfileFull, ProfileCustom}

type Config struct {
	ProjectName       string   `json:"project_name"`
	ProjectRoot       string   `json:"project_root"`
	Profile           Profile  `json:"profile"`
	Modules           []string `json:"modules,omitempty"`
	ResetExistingName string   `json:"-"`
	Company           string   `json:"company"`
	CompanyShort      string   `json:"company_short"`
	CUIT              string   `json:"cuit"`
	Address           string   `json:"address"`
	City              string   `json:"city"`
	Responsibility    string   `json:"responsibility"`
	BillingPOS        int      `json:"billing_pos"`
	POSPOS            int      `json:"pos_pos"`
	AdminEmail        string   `json:"admin_email"`
	AdminName         string   `json:"admin_name"`
	AdminPassword     string   `json:"-"`
	MasterPassword    string   `json:"-"`
	Port              int      `json:"port"`
	CallbackPort      int      `json:"callback_port"`
	InitDB            string   `json:"init_db"`
}

var slugInvalid = regexp.MustCompile(`[^a-z0-9]+`)

func Slugify(value string) string {
	value = strings.NewReplacer("á", "a", "é", "e", "í", "i", "ó", "o", "ú", "u", "ü", "u", "ñ", "n",
		"Á", "a", "É", "e", "Í", "i", "Ó", "o", "Ú", "u", "Ü", "u", "Ñ", "n").Replace(strings.ToLower(strings.TrimSpace(value)))
	value = slugInvalid.ReplaceAllString(value, "")
	if len(value) > 48 {
		value = value[:48]
	}
	return value
}

func DefaultProjectRoot() string {
	if runtime.GOOS == "windows" {
		base := os.Getenv("PROGRAMDATA")
		if base == "" {
			base = `C:\ProgramData`
		}
		return filepath.Join(base, "DOLAN", "deployments")
	}
	return "/opt/dolan/deployments"
}

func NewConfig() Config {
	return Config{Profile: ProfileCore, Responsibility: "Responsable Inscripto", BillingPOS: 1, POSPOS: 1, Port: 8070, CallbackPort: 1455, AdminName: "Administrador", ProjectRoot: DefaultProjectRoot()}
}

func (c *Config) Normalize() {
	if c.CompanyShort == "" {
		c.CompanyShort = Slugify(c.Company)
	}
	if c.ProjectName == "" {
		c.ProjectName = c.CompanyShort
	}
	if c.InitDB == "" && c.CompanyShort != "" {
		c.InitDB = "odoo_" + c.CompanyShort
	}
	if c.ProjectRoot == "" {
		c.ProjectRoot = DefaultProjectRoot()
	}
	if c.Port == 0 {
		c.Port = 8070
	}
	if c.CallbackPort == 0 {
		c.CallbackPort = 1455
	}
	if c.BillingPOS == 0 {
		c.BillingPOS = 1
	}
	if c.POSPOS == 0 {
		c.POSPOS = 1
	}
	if c.AdminName == "" {
		c.AdminName = "Administrador"
	}
}

func (c Config) DeploymentPath() string {
	return filepath.Join(c.ProjectRoot, c.ProjectName)
}

func (c Config) Validate(requireCompany bool) error {
	if !containsProfile(c.Profile) {
		return fmt.Errorf("perfil inválido %q: elegí core, comercio, servicios, full o custom", c.Profile)
	}
	if !regexp.MustCompile(`^[a-z0-9][a-z0-9_-]{0,47}$`).MatchString(c.ProjectName) {
		return errors.New("el nombre corto debe contener hasta 48 letras minúsculas, números, guion o guion bajo")
	}
	if !filepath.IsAbs(c.ProjectRoot) {
		return errors.New("la ruta base de instalaciones debe ser absoluta")
	}
	if c.Port < 1 || c.Port > 65535 {
		return errors.New("el puerto HTTP debe estar entre 1 y 65535")
	}
	if c.CallbackPort < 1 || c.CallbackPort > 65535 {
		return errors.New("el puerto de callback debe estar entre 1 y 65535")
	}
	if c.Port == c.CallbackPort {
		return errors.New("el puerto HTTP y el puerto OAuth no pueden coincidir")
	}
	if c.Profile == ProfileCustom && len(c.Modules) == 0 {
		return errors.New("el perfil custom requiere al menos un módulo")
	}
	if !requireCompany {
		return nil
	}
	if strings.TrimSpace(c.Company) == "" {
		return errors.New("indicá la razón social")
	}
	if !ValidCUIT(c.CUIT) {
		return errors.New("el CUIT debe tener 11 dígitos y dígito verificador válido")
	}
	if strings.TrimSpace(c.Address) == "" {
		return errors.New("indicá el domicilio fiscal")
	}
	if strings.TrimSpace(c.City) == "" {
		return errors.New("indicá la localidad")
	}
	if c.Responsibility != "Responsable Inscripto" && c.Responsibility != "Monotributista" && c.Responsibility != "Exento" {
		return errors.New("seleccioná una responsabilidad ARCA reconocida")
	}
	if c.BillingPOS < 1 || c.BillingPOS > 99998 || c.POSPOS < 1 || c.POSPOS > 99998 {
		return errors.New("los puntos de venta deben estar entre 1 y 99998")
	}
	if _, err := mail.ParseAddress(c.AdminEmail); err != nil || !strings.Contains(c.AdminEmail, ".") {
		return errors.New("indicá un correo de administrador válido")
	}
	if len(c.AdminPassword) < 8 {
		return errors.New("la contraseña del administrador debe tener al menos 8 caracteres")
	}
	if c.InitDB == "" {
		return errors.New("no se pudo generar el nombre de la base")
	}
	if !regexp.MustCompile(`^[a-z][a-z0-9_]{0,62}$`).MatchString(c.InitDB) {
		return errors.New("el nombre de base debe comenzar con una letra y usar minúsculas, números o guion bajo")
	}
	return nil
}

func ValidCUIT(input string) bool {
	digits := make([]int, 0, 11)
	for _, r := range input {
		if r >= '0' && r <= '9' {
			digits = append(digits, int(r-'0'))
		}
	}
	if len(digits) != 11 {
		return false
	}
	weights := []int{5, 4, 3, 2, 7, 6, 5, 4, 3, 2}
	sum := 0
	for i, weight := range weights {
		sum += digits[i] * weight
	}
	check := 11 - (sum % 11)
	if check == 11 {
		check = 0
	}
	if check == 10 {
		return digits[0] == 2 && digits[1] == 3 && digits[10] == 9
	}
	return digits[10] == check
}

func containsProfile(p Profile) bool {
	for _, valid := range Profiles {
		if p == valid {
			return true
		}
	}
	return false
}
