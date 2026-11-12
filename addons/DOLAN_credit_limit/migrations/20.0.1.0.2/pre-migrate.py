# -*- coding: utf-8 -*-
"""El bloqueo manual pasa de dolan_credit_blocked a dolan_credit_hold.

En 20.0.1.0.0 DOLAN_credit_limit redefinía dolan_credit_blocked, el campo de
bloqueo por mora de DOLAN_accounting, como company_dependent (jsonb). Desde
20.0.1.0.2 el bloqueo manual vive en dolan_credit_hold y el de mora solo
frena ventas si el cliente tiene el tilde dolan_overdue_blocks_sales.

- Sin DOLAN_accounting, dolan_credit_blocked era solo el bloqueo manual: se
  copia a dolan_credit_hold y se elimina la columna vieja.
- Con DOLAN_accounting, la columna es la de mora: si quedó como jsonb se
  vuelve a booleano (bloqueado si lo estaba en alguna compañía).
"""


def _column_type(cr, column):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'res_partner' AND column_name = %s
    """, (column,))
    row = cr.fetchone()
    return row and row[0]


def _as_boolean_sql(column_type):
    if column_type == 'jsonb':
        return """EXISTS (SELECT 1 FROM jsonb_each(
                      CASE WHEN jsonb_typeof(dolan_credit_blocked) = 'object'
                           THEN dolan_credit_blocked ELSE '{}'::jsonb END) AS v(key, value)
                   WHERE v.value = 'true'::jsonb)"""
    return "COALESCE(dolan_credit_blocked, false)"


def migrate(cr, version):
    column_type = _column_type(cr, 'dolan_credit_blocked')
    if not column_type:
        return
    cr.execute("SELECT 1 FROM ir_module_module WHERE name = 'DOLAN_accounting' AND state IN ('installed', 'to upgrade')")
    accounting = bool(cr.fetchone())
    if not accounting:
        if not _column_type(cr, 'dolan_credit_hold'):
            cr.execute("ALTER TABLE res_partner ADD COLUMN dolan_credit_hold boolean")
        cr.execute("UPDATE res_partner SET dolan_credit_hold = " + _as_boolean_sql(column_type))
        cr.execute("ALTER TABLE res_partner DROP COLUMN dolan_credit_blocked")
        return
    if column_type == 'jsonb':
        cr.execute("ALTER TABLE res_partner ADD COLUMN dolan_credit_blocked_bool boolean")
        cr.execute("UPDATE res_partner SET dolan_credit_blocked_bool = " + _as_boolean_sql(column_type))
        cr.execute("ALTER TABLE res_partner DROP COLUMN dolan_credit_blocked")
        cr.execute("ALTER TABLE res_partner RENAME COLUMN dolan_credit_blocked_bool TO dolan_credit_blocked")
