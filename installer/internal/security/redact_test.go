package security

import "testing"

func TestRedact(t *testing.T) {
	got := Redact("DOLAN_API_KEY=abc123 Authorization: Bearer token", "abc123")
	if got == "DOLAN_API_KEY=abc123 Authorization: Bearer token" || got == "" {
		t.Fatalf("sensitive values were not redacted: %q", got)
	}
	if got := Redact("a line contains custom-secret", "custom-secret"); got != "a line contains [REDACTED]" {
		t.Fatalf("explicit secret not redacted: %q", got)
	}
}
