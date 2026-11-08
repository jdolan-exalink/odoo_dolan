"""Normalize legacy appearance profile identifiers without resetting user choices."""


PROFILE_MAP = {
    "enterprise_classic": "odoo_classic",
    "graphite": "dolan_fluent",
    "glass": "dolan_liquid",
    "liquid_glass_dark": "dolan_liquid",
    "liquid_glass_light": "dolan_liquid",
    "minimal": "dolan_minimal",
    "legacy": "odoo_classic",
}


def migrate(cr, version):
    cr.execute("SELECT value FROM ir_config_parameter WHERE key = 'dolan_ui.appearance_profile'")
    row = cr.fetchone()
    if row and row[0] in PROFILE_MAP:
        cr.execute(
            "UPDATE ir_config_parameter SET value = %s WHERE key = 'dolan_ui.appearance_profile'",
            (PROFILE_MAP[row[0]],),
        )
    cr.execute("SELECT to_regclass('dolan_screen_preference')")
    if cr.fetchone()[0]:
        for old_value, new_value in PROFILE_MAP.items():
            cr.execute(
                "UPDATE dolan_screen_preference SET appearance_profile = %s WHERE appearance_profile = %s",
                (new_value, old_value),
            )
