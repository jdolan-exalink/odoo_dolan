package security

import (
	"regexp"
	"strings"
)

var sensitiveLine = regexp.MustCompile(`(?i)(password|passwd|secret|token|api[_-]?key|authorization)(\s*[=:]\s*)([^\s,;]+)`)

func Redact(line string, secrets ...string) string {
	line = sensitiveLine.ReplaceAllString(line, "$1$2[REDACTED]")
	for _, secret := range secrets {
		if secret != "" {
			line = strings.ReplaceAll(line, secret, "[REDACTED]")
		}
	}
	return line
}
