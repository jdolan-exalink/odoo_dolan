# -*- coding: utf-8 -*-
"""dolan_credit_blocked deja de ser company_dependent.

En las bases donde la versión 20.0.1.0.0 se instaló sin DOLAN_accounting la
columna quedó como jsonb (un valor por compañía). Se pasa a booleano: el
cliente queda bloqueado si estaba bloqueado en alguna compañía.
"""


def migrate(cr, version):
    cr.execute("""
        SELECT data_type FROM information_schema.columns
         WHERE table_name = 'res_partner' AND column_name = 'dolan_credit_blocked'
    """)
    row = cr.fetchone()
    if not row or row[0] != 'jsonb':
        return
    cr.execute("ALTER TABLE res_partner ADD COLUMN dolan_credit_blocked_bool boolean")
    cr.execute("""
        UPDATE res_partner p
           SET dolan_credit_blocked_bool = EXISTS (
                SELECT 1 FROM jsonb_each(p.dolan_credit_blocked) AS v(key, value)
                 WHERE v.value = 'true'::jsonb)
         WHERE jsonb_typeof(p.dolan_credit_blocked) = 'object'
    """)
    cr.execute("ALTER TABLE res_partner DROP COLUMN dolan_credit_blocked")
    cr.execute("ALTER TABLE res_partner RENAME COLUMN dolan_credit_blocked_bool TO dolan_credit_blocked")
