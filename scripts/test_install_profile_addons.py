#!/usr/bin/env python3
"""Guard profile bundles against addons listed by the Go installer."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "crear_odoo20.sh").read_text(encoding="utf-8")


def profile_assignment(profile: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(profile)}\)\s*(.*?)(?=^  [a-z]+\)|^  \*\))",
        SCRIPT,
    )
    if not match:
        raise AssertionError(f"No encuentro el bloque de perfil {profile!r}")
    return match.group(1)


class InstallProfileAddonTests(unittest.TestCase):
    def test_commerce_and_full_profiles_include_pos_addons(self):
        commerce = profile_assignment("comercio")
        full = profile_assignment("full")
        for addon in ("ePOS_print", "pos_scale_management", "DOLAN_discount_engine", "DOLAN_payment_terminal"):
            with self.subTest(profile="comercio", addon=addon):
                self.assertIn(addon, commerce)
        for addon in ("ePOS_print", "pos_scale_management"):
            with self.subTest(profile="full", addon=addon):
                self.assertIn(addon, full)

    def test_non_dolan_requested_addons_are_copied_with_manifests(self):
        self.assertIn('IFS=\',\' read -ra REQUESTED_ADDONS <<< "$DOLAN_ADDONS"', SCRIPT)
        self.assertIn('[[ "$addon" == DOLAN_* ]] && continue', SCRIPT)
        self.assertIn('! -f "$mod_dir/__manifest__.py"', SCRIPT)
        self.assertIn('cp -r "$mod_dir" .', SCRIPT)


if __name__ == "__main__":
    unittest.main()
