package main

import (
	"fmt"
	"os"

	"github.com/jdolan-exalink/odoo_dolan/installer/internal/cli"
)

func main() {
	if err := cli.Run(os.Args[1:]); err != nil {
		fmt.Fprintln(os.Stderr, "Error:", err)
		os.Exit(1)
	}
}
