"""Cambia nombres, CUIT, correos, teléfonos y cuentas bancarias por datos ficticios en una COPIA
de la base, para sacar las capturas de la Ayuda sin mostrar clientes, proveedores ni empleados reales.

Se corre con odoo shell sobre una base cuyo nombre contenga «help_shots» (se niega con cualquier otra):

    docker exec -i <contenedor> python3 /opt/odoo/odoo-server/odoo-bin shell -c /etc/odoo/odoo.conf \
        -d dolan_help_shots --no-http < scripts/help_shots_anonymize.py

Es repetible: cada registro recibe siempre el mismo nombre ficticio (según su id).
"""
import random

if 'help_shots' not in env.cr.dbname:  # noqa: F821 - env lo da odoo shell
    raise SystemExit(f'Me niego: la base {env.cr.dbname} no es una copia para capturas (tiene que llamarse *help_shots*).')  # noqa: F821

E = env(context=dict(env.context, tracking_disable=True, mail_notrack=True, no_reset_password=True), su=True)  # noqa: F821

FIRST = ['Lucía', 'Martín', 'Sofía', 'Juan Pablo', 'Valentina', 'Diego', 'Camila', 'Federico', 'Agustina', 'Nicolás',
         'Florencia', 'Matías', 'Carolina', 'Santiago', 'Micaela', 'Gonzalo', 'Julieta', 'Pablo', 'Rocío', 'Tomás',
         'Paula', 'Ezequiel', 'Natalia', 'Facundo', 'Brenda', 'Lautaro', 'Daniela', 'Hernán', 'Milagros', 'Leandro']
LAST = ['Gómez', 'Fernández', 'Rodríguez', 'López', 'Martínez', 'Pérez', 'García', 'Sánchez', 'Romero', 'Sosa',
        'Álvarez', 'Torres', 'Ruiz', 'Ramírez', 'Flores', 'Benítez', 'Acosta', 'Medina', 'Herrera', 'Aguirre',
        'Pereyra', 'Gutiérrez', 'Giménez', 'Molina', 'Silva', 'Castro', 'Rojas', 'Ortiz', 'Núñez', 'Luna']
COMPANY_A = ['Almacén', 'Distribuidora', 'Ferretería', 'Corralón', 'Supermercado', 'Autoservicio', 'Mayorista',
             'Agropecuaria', 'Librería', 'Farmacia', 'Panadería', 'Transportes', 'Servicios', 'Comercial', 'Industrias',
             'Maderera', 'Electricidad', 'Lácteos', 'Frigorífico', 'Estación de Servicio']
COMPANY_B = ['del Sur', 'La Esquina', 'San Martín', 'El Progreso', 'Los Álamos', 'Río Paraná', 'Don Ernesto',
             'La Pampa', 'Norte Grande', 'Del Centro', 'Las Heras', 'Belgrano', 'Santa Rita', 'El Ceibo', 'Litoral',
             'Los Robles', 'Patagonia', 'Mitre', 'La Colonia', 'Sarmiento']
FORMS = ['S.A.', 'S.R.L.', 'S.A.S.', 'S.R.L.', 'S.A.']
STREETS = ['Av. San Martín', 'Belgrano', 'Av. Rivadavia', 'Mitre', 'Sarmiento', '25 de Mayo', 'Moreno', 'Av. Libertad']


def cuit(prefix, rnd):
    body = f'{prefix}{rnd.randrange(10_000_000, 99_999_999)}'
    weights = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    check = 11 - sum(int(d) * w for d, w in zip(body, weights)) % 11
    if check == 11:
        check = 0
    if check == 10:
        return cuit(prefix, rnd)
    return f'{body}{check}'


def cbu(rnd):
    def block(digits, weights):
        return digits + str((10 - sum(int(d) * w for d, w in zip(digits, weights)) % 10) % 10)
    first = block(''.join(str(rnd.randrange(10)) for _ in range(7)), [7, 1, 3, 9, 7, 1, 3])
    second = block(''.join(str(rnd.randrange(10)) for _ in range(13)), [3, 9, 7, 1, 3, 9, 7, 1, 3, 9, 7, 1, 3])
    return first + second


def slug(text):
    import unicodedata
    text = unicodedata.normalize('NFD', text).encode('ascii', 'ignore').decode().lower()
    return ''.join(c if c.isalnum() else '.' for c in text).strip('.').replace('..', '.')


Partner = E['res.partner'].with_context(active_test=False)
company_partners = E['res.company'].search([]).mapped('partner_id')


def fake_vat(vat, rnd, is_company):
    digits = ''.join(c for c in (vat or '') if c.isdigit())
    if len(digits) == 11:
        return cuit(digits[:2] if digits[:2] in ('20', '23', '24', '27', '30', '33', '34') else ('30' if is_company else '20'), rnd)
    if 7 <= len(digits) <= 8:
        return str(rnd.randrange(20_000_000, 45_000_000))
    return False


# Empresas propias: nombre de ejemplo
for index, company in enumerate(E['res.company'].search([], order='id')):
    rnd = random.Random(f'company-{company.id}')
    name = 'Distribuidora Ejemplo S.A.' if index == 0 else f'Ejemplo Sucursal {index} S.A.'
    vals = {'name': name, 'email': f'administracion{index or ""}@ejemplo.com.ar', 'phone': '+54 11 4000-1000'}
    company.write(vals)
    pvals = {'street': f'{STREETS[index % len(STREETS)]} {100 + index * 10}'}
    if company.partner_id.vat:
        pvals['vat'] = cuit('30', rnd)
    try:
        company.partner_id.write(pvals)
    except Exception as error:  # noqa: BLE001
        print('empresa', company.id, error)

changed = 0
for partner in Partner.search([('id', 'not in', company_partners.ids)], order='id'):
    if partner.id in (E.ref('base.public_partner', raise_if_not_found=False) or Partner).ids:
        continue
    rnd = random.Random(f'partner-{partner.id}')
    is_company = partner.is_company or bool(partner.vat and not partner.parent_id and str(partner.vat).startswith('3'))
    if partner.parent_id and partner.type != 'contact':
        name = partner.name and f'{partner.type == "delivery" and "Depósito" or "Sucursal"} {rnd.choice(STREETS)}'
    elif is_company:
        crnd = random.Random(f'company-name-{partner.vat or partner.id}')
        name = f'{crnd.choice(COMPANY_A)} {crnd.choice(COMPANY_B)} {crnd.choice(FORMS)}'
    else:
        name = f'{rnd.choice(FIRST)} {rnd.choice(LAST)}'
    vals = {'name': name or partner.name}
    if partner.email:
        vals['email'] = f'{slug(name)[:30]}@ejemplo.com.ar'
    if partner.phone:
        vals['phone'] = f'+54 11 4{rnd.randrange(100, 999)}-{rnd.randrange(1000, 9999)}'
    if 'mobile' in partner._fields and partner.mobile:
        vals['mobile'] = f'+54 9 11 5{rnd.randrange(100, 999)}-{rnd.randrange(1000, 9999)}'
    if partner.street:
        vals['street'] = f'{rnd.choice(STREETS)} {rnd.randrange(100, 4999)}'
    if partner.vat:
        vals['vat'] = fake_vat(partner.vat, random.Random(f'vat-{partner.vat}'), is_company)
    try:
        with E.cr.savepoint():
            partner.write(vals)
        changed += 1
    except Exception as error:  # noqa: BLE001
        print('contacto', partner.id, error)
print('contactos cambiados:', changed)

if 'hr.employee' in E:
    for employee in E['hr.employee'].with_context(active_test=False).search([]):
        rnd = random.Random(f'employee-{employee.id}')
        vals = {'name': f'{rnd.choice(FIRST)} {rnd.choice(LAST)}'}
        for field in ('work_email', 'private_email'):
            if field in employee._fields and employee[field]:
                vals[field] = f'{slug(vals["name"])}@ejemplo.com.ar'
        for field in ('identification_id', 'ssnid'):
            if field in employee._fields and employee[field]:
                vals[field] = str(rnd.randrange(20_000_000, 45_000_000))
        try:
            with E.cr.savepoint():
                employee.write(vals)
        except Exception as error:  # noqa: BLE001
            print('empleado', employee.id, error)

for bank in E['res.partner.bank'].with_context(active_test=False).search([]):
    rnd = random.Random(f'bank-{bank.id}')
    try:
        with E.cr.savepoint():
            field = 'account_number' if 'account_number' in bank._fields else 'acc_number'
            vals = {field: cbu(rnd)}
            if 'cbu_alias' in bank._fields and bank.cbu_alias:
                vals['cbu_alias'] = f'ejemplo.cuenta.{bank.id}'
            bank.write(vals)
    except Exception as error:  # noqa: BLE001
        print('cuenta', bank.id, error)

# Los nombres guardados en comprobantes ya emitidos
E.cr.execute("""
    UPDATE account_move m SET invoice_partner_display_name = p.complete_name
      FROM res_partner p WHERE p.id = m.partner_id AND m.invoice_partner_display_name IS NOT NULL
""")
E.cr.commit()
print('listo')
