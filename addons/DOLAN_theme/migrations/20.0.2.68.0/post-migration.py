def migrate(cr, version):
    # Mi Espacio retired the per-user Prioridades/Personalizado selector:
    # every user now sees the complete indicator set filtered by work area.
    cr.execute(
        "UPDATE dolan_workspace_preference SET indicator_mode = 'complete' "
        "WHERE indicator_mode IS DISTINCT FROM 'complete'"
    )
