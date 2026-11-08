"""Consolidate the two Liquid Glass variants into the single Glass profile."""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE ir_config_parameter
           SET value = 'glass'
         WHERE key = 'dolan_ui.appearance_profile'
           AND value IN ('liquid_glass_dark', 'liquid_glass_light')
        """
    )
    cr.execute(
        """
        UPDATE dolan_screen_preference
           SET appearance_profile = 'glass'
         WHERE appearance_profile IN ('liquid_glass_dark', 'liquid_glass_light')
        """
    )
