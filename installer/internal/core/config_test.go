package core

import "testing"

func TestSlugify(t *testing.T) {
	if got := Slugify("Cintía Verónica Gorosito"); got != "cintiaveronicagorosito" {
		t.Fatalf("Slugify() = %q", got)
	}
}

func TestValidCUIT(t *testing.T) {
	if !ValidCUIT("30-52722598-8") {
		t.Fatal("expected valid CUIT")
	}
	if ValidCUIT("30-52722598-7") {
		t.Fatal("expected checksum mismatch")
	}
	if ValidCUIT("123") {
		t.Fatal("expected invalid length")
	}
}

func TestConfigValidation(t *testing.T) {
	c := NewConfig()
	c.ProjectName = "empresa1"
	c.Company = "Empresa Uno SA"
	c.CUIT = "30-52722598-8"
	c.Address = "Calle 123"
	c.City = "Santa Fe"
	c.AdminEmail = "admin@example.com"
	c.AdminPassword = "una-clave-segura"
	c.Normalize()
	if err := c.Validate(true); err != nil {
		t.Fatalf("valid config rejected: %v", err)
	}
	c.Port = c.CallbackPort
	if err := c.Validate(true); err == nil {
		t.Fatal("expected duplicate port error")
	}
}
