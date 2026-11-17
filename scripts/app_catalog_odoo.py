"""Íconos estilo Odoo para las apps propias de DOLAN.

El estilo «Originales de Odoo» del Escritorio muestra el ícono nativo del menú
(web_icon). Las apps de Odoo usan dibujos planos de 50x50, sin mosaico ni
trazos finos: dos a cuatro formas geométricas grandes de la paleta de Odoo, y
donde dos formas se pisan, la zona común va en un tono más oscuro.

Este archivo dibuja con esas reglas un ícono por app propia (todas distintas).
Dibujados para este repositorio (licencia LGPL-3 del proyecto); no copian
ningún ícono de Odoo. build_app_catalog.py los escribe en lib/odoo/ y los usa
como web_icon de los menús, así que también son los íconos por defecto de cada
app en la lista de Odoo.
"""
import math

# Paleta de los íconos de Odoo.
P, PD = "#985184", "#712258"        # violeta
T, TD, TG = "#1AD3BB", "#005E7A", "#1A6F66"  # turquesa
Y, A, O = "#FBB945", "#F78613", "#F86126"    # amarillo, ámbar, naranja
K, W, RD = "#FC868B", "#962B48", "#F9464C"   # rosa, bordó, rojo
B, BL, N = "#088BF5", "#2EBCFA", "#144496"   # azules


def rect(x, y, w, h, r=0, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}"{extra}/>'


def circle(cx, cy, r):
    return f'<circle cx="{cx}" cy="{cy}" r="{r}"/>'


def path(d, extra=""):
    return f'<path d="{d}"{extra}/>'


def gear(cx, cy, r_out, r_in, teeth=8):
    """Engranaje macizo (sin agujero) como polígono."""
    pts = []
    step = 2 * math.pi / teeth
    for i in range(teeth):
        a = i * step
        for da, rr in ((-0.22, r_in), (-0.13, r_out), (0.13, r_out), (0.22, r_in)):
            pts.append((cx + rr * math.cos(a + da * step * 2), cy + rr * math.sin(a + da * step * 2)))
    return path("M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + "Z")


def fill(color, *shapes):
    return [("fill", color, s) for s in shapes]


def over(color, base, shape, mono_edge=False):
    """Zona donde `shape` pisa a `base`, en el color más oscuro. Con `mono_edge` su
    borde queda marcado también en la versión de un color."""
    return [("over", color, base, shape, mono_edge)]


def stroke(color, shape, width=5):
    return [("stroke", color, shape, width)]


def render(layers):
    defs, body = [], []
    for layer in layers:
        kind = layer[0]
        if kind == "fill":
            _k, color, shape = layer
            body.append(shape.replace("/>", f' fill="{color}"/>', 1))
        elif kind == "over":
            _k, color, base, shape, _edge = layer
            cid = f"c{len(defs)}"
            defs.append(f'<clipPath id="{cid}">{base}</clipPath>')
            body.append(shape.replace("/>", f' fill="{color}" clip-path="url(#{cid})"/>', 1))
        else:
            _k, color, shape, width = layer
            body.append(shape.replace(
                "/>", f' fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round"/>', 1))
    head = '<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg">'
    inner = (f"<defs>{''.join(defs)}</defs>" if defs else "") + "".join(body)
    return f"{head}{inner}</svg>\n"


def _icons():
    i = {}
    # ---- Comercial ------------------------------------------------------
    back, front = rect(16, 4, 28, 34, 4), rect(6, 12, 28, 34, 4)
    i["quotations"] = (fill(Y, back) + fill(K, front) + over(O, back, front)
                       + fill(P, rect(11, 30, 17, 4.5, 2.25), rect(11, 37.5, 10, 4.5, 2.25)))

    b2 = path("M22 46v-5a12 12 0 0 1 12-12h0a12 12 0 0 1 12 12v5Z")
    b1 = path("M4 46v-6a12 12 0 0 1 12-12h4a12 12 0 0 1 12 12v6Z")
    i["customers"] = (fill(T, circle(34, 15, 7), b2) + fill(P, circle(18, 15, 8.5), b1)
                      + over(TD, b2, b1) + over(TD, circle(34, 15, 7), circle(18, 15, 8.5)))

    tag_b = path("M14 4h16l16 16-14 14-18-18Z")
    tag_f = path("M4 10a4 4 0 0 1 4-4h14l20 20a3 3 0 0 1 0 4.2L28.2 44a3 3 0 0 1-4.2 0L4 24Z")
    i["pricelists"] = fill(K, tag_b) + fill(Y, tag_f) + over(O, tag_b, tag_f) + fill(P, circle(14, 16, 4))

    bag_b = path("M24 12h20l2 30a4 4 0 0 1-4 4H26Z")
    bag_f = path("M8 18h26l2 24a4 4 0 0 1-4 4H10a4 4 0 0 1-4-4Z")
    i["marketplace"] = (fill(T, bag_b) + stroke(T, path("M29 13v-3a5 5 0 0 1 10 0v3"), 3.5)
                        + fill(P, bag_f) + over(TD, bag_b, bag_f)
                        + stroke(Y, path("M15 22v-5a6 6 0 0 1 12 0v5"), 4))

    screen = rect(4, 6, 42, 28, 4)
    bag = path("M27 22h16l1 18a3 3 0 0 1-3 3H29a3 3 0 0 1-3-3Z")
    i["ecommerce"] = (fill(BL, screen) + fill(N, rect(21, 34, 8, 7), rect(14, 40, 22, 5, 2.5))
                      + fill(Y, bag) + over(A, screen, bag) + stroke(P, path("M31 23v-3a4 4 0 0 1 8 0v3"), 3))

    star = path("M24 4l5.9 12 13.1 1.9-9.5 9.3 2.3 13.1L24 34.1l-11.8 6.2 2.3-13.1L5 17.9l13.1-1.9Z")
    i["loyalty"] = fill(K, circle(36, 36, 11)) + fill(Y, star) + over(O, circle(36, 36, 11), star)

    # ---- Finanzas -------------------------------------------------------
    c_b, c_f = rect(12, 16, 34, 26, 4), rect(4, 8, 34, 26, 4)
    i["current_accounts"] = (fill(T, c_b) + fill(P, c_f) + over(TD, c_b, c_f)
                             + fill(Y, circle(14, 18, 4.5), path("M7 30a7 7 0 0 1 14 0Z"))
                             + fill(Y, rect(25, 16, 8, 4, 2), rect(25, 23, 8, 4, 2)))

    clock = circle(35, 34, 11)
    body = path("M4 44v-4a12 12 0 0 1 12-12h6a12 12 0 0 1 12 12v4Z")
    i["debtors"] = (fill(P, circle(19, 14, 9), body) + fill(Y, clock) + over(O, body, clock)
                    + stroke(PD, path("M35 28v6l4 3"), 3.5))

    hand = path("M4 30h11l8 4h11a4 4 0 0 1 0 8H4Z")
    coin = circle(30, 15, 10)
    i["collections"] = (fill(Y, coin) + fill(A, circle(30, 15, 5)) + fill(P, hand)
                        + fill(T, rect(2, 27, 9, 19, 2.5)) + over(TD, hand, rect(2, 27, 9, 19, 2.5)))

    note = rect(4, 16, 32, 24, 4)
    arrow = path("M28 6h8V2l11 9-11 9v-4h-8Z")
    i["vendor_payments"] = (fill(K, note) + fill(W, circle(20, 28, 6)) + fill(O, arrow)
                            + over(RD, note, arrow) + fill(P, rect(4, 42, 32, 4, 2)))

    safe = rect(5, 5, 40, 36, 5)
    i["treasury"] = (fill(P, safe) + fill(PD, rect(10, 41, 7, 5, 2), rect(33, 41, 7, 5, 2))
                     + fill(Y, circle(22, 23, 11)) + fill(O, circle(22, 23, 5))
                     + fill(T, rect(36, 15, 4.5, 16, 2.25)))

    i["banks"] = (fill(N, path("M25 3l21 12a2 2 0 0 1-1 3.7H5A2 2 0 0 1 4 15Z"))
                  + fill(B, rect(8, 21, 6, 17, 2), rect(18, 21, 6, 17, 2), rect(27, 21, 6, 17, 2), rect(37, 21, 6, 17, 2))
                  + fill(BL, rect(4, 40, 42, 6, 3)))

    chk_b, chk_f = rect(9, 6, 38, 24, 4), rect(3, 16, 40, 26, 4)
    i["checks"] = (fill(T, chk_b) + fill(Y, chk_f) + over(TG, chk_b, chk_f)
                   + stroke(P, path("M9 34c3-4 5-4 7 0s4 4 7 0"), 3.5) + fill(O, rect(29, 31, 9, 5, 2.5)))

    ar_t = path("M4 10a3 3 0 0 1 3-3h23V2l16 12-16 12v-5H7a3 3 0 0 1-3-3Z")
    ar_b = path("M46 32a3 3 0 0 0-3-3H20v-5L4 36l16 12v-5h23a3 3 0 0 0 3-3Z")
    i["reconciliation"] = fill(T, ar_t) + fill(P, ar_b) + over(TD, ar_t, ar_b)

    disc = circle(25, 25, 21)
    band = rect(21, -4, 8, 58, 0, ' transform="rotate(45 25 25)"')
    i["taxes"] = fill(Y, disc) + over(P, disc, band, mono_edge=True) + fill(W, circle(16, 16, 5), circle(34, 34, 5))

    doc = rect(4, 4, 30, 42, 4)
    bars = [rect(14, 30, 7, 12, 2), rect(24, 22, 7, 20, 2), rect(34, 12, 7, 30, 2)]
    i["fiscal_reports"] = (fill(K, doc) + fill(P, *bars)
                           + sum((over(W, doc, b) for b in bars), []))

    i["financial_reports"] = (fill(BL, rect(4, 26, 13, 20, 3)) + fill(B, rect(18.5, 14, 13, 32, 3))
                              + fill(N, rect(33, 4, 13, 42, 3)))

    # ---- Punto de venta -------------------------------------------------
    receipt = path("M9 4h28v42l-4.7-3.5L27.7 46 23 42.5 18.3 46l-4.6-3.5L9 46Z")
    check = circle(36, 33, 10)
    i["pos_closing"] = (fill(K, receipt) + fill(W, rect(14, 11, 18, 4, 2), rect(14, 19, 12, 4, 2))
                        + fill(T, check) + over(TG, receipt, check)
                        + stroke("#ffffff", path("M31.5 33l3 3 6-6"), 3))

    drawer = rect(4, 26, 42, 20, 4)
    clk = circle(32, 17, 13)
    i["cash_shifts"] = (fill(Y, drawer) + fill(A, rect(12, 36, 18, 5, 2.5)) + fill(P, clk)
                        + over(W, drawer, clk) + stroke(Y, path("M32 10v7h6"), 3.5))

    # ---- Inventario y compras -------------------------------------------
    box = rect(7, 18, 36, 28, 4)
    lid = rect(4, 9, 42, 13, 4)
    i["products"] = (fill(O, box) + fill(P, lid) + over(W, box, lid)
                     + fill(Y, rect(21, 9, 8, 22, 2)) + over(A, lid, rect(21, 9, 8, 22, 2)))

    fac = path("M4 46V24l12-8v8l12-8v8l12-8v30Z")
    chim = rect(36, 4, 7, 22, 2)
    i["suppliers"] = (fill(T, chim) + fill(P, fac) + over(TD, chim, fac)
                      + fill(Y, rect(10, 34, 6, 6, 1.5), rect(21, 34, 6, 6, 1.5), rect(32, 34, 6, 6, 1.5)))

    i["replenishment"] = (stroke(T, path("M41 27A16 16 0 1 1 36.3 13.7"), 8)
                          + fill(T, path("M44 4v15H29Z")) + fill(P, rect(18, 20, 14, 14, 3)))

    left, right = rect(3, 26, 18, 18, 4), rect(29, 26, 18, 18, 4)
    i["transfers"] = (fill(P, left) + fill(T, right)
                      + stroke(Y, path("M12 21a13 11 0 0 1 24 -2"), 5) + fill(Y, path("M30 14l11 3-6 9Z")))

    i["lots"] = (fill(P, rect(5, 4, 5, 32, 1.5), rect(23, 4, 4, 32, 1.5), rect(39, 4, 6, 32, 1.5))
                 + fill(T, rect(13, 4, 7, 32, 1.5), rect(30, 4, 6, 32, 1.5)) + fill(Y, rect(5, 40, 40, 6, 3)))

    board = rect(7, 7, 36, 39, 5)
    clip = rect(16, 3, 18, 9, 3)
    i["stock_count"] = (fill(O, board) + fill(P, clip) + over(W, board, clip)
                        + fill(T, circle(16, 24, 4), circle(16, 36, 4))
                        + fill(Y, rect(23, 22, 14, 4, 2), rect(23, 34, 14, 4, 2)))

    tag = path("M26 4h12a4 4 0 0 1 4 4v12L28 34 14 20Z")
    coins = [rect(4, 22, 28, 9, 4.5), rect(4, 30, 28, 9, 4.5), rect(4, 38, 28, 8, 4)]
    i["costs"] = (fill(P, tag) + fill(Y, coins[0]) + fill(A, coins[1]) + fill(Y, coins[2])
                  + over(PD, tag, coins[0]) + fill(Y, circle(34, 12, 3)))

    # ---- Logística ------------------------------------------------------
    doc = rect(4, 4, 28, 36, 4)
    truck = rect(18, 22, 20, 16, 3)
    i["delivery_notes"] = (fill(Y, doc) + fill(P, truck) + over(O, doc, truck)
                           + fill(K, path("M38 26h3.5a2 2 0 0 1 1.7 1l3 5V38h-8.2Z"))
                           + fill(PD, circle(25, 40, 4.5), circle(40, 40, 4.5)))

    basket = path("M12 18h34l-4.5 17a3 3 0 0 1-2.9 2.2H18.4a3 3 0 0 1-2.9-2.2Z")
    pbox = rect(20, 6, 15, 15, 3)
    i["picking"] = (stroke(T, path("M3 8h6l4 12"), 4.5) + fill(T, basket) + fill(Y, pbox)
                    + over(TG, basket, pbox) + fill(P, circle(21, 43, 4), circle(38, 43, 4)))

    i["routes"] = (stroke(P, path("M10 40h18a7 7 0 0 0 0-14H22a7 7 0 0 1 0-14h12"), 6)
                   + fill(T, circle(10, 40, 6.5)) + fill(Y, rect(34, 4, 4, 18, 2), path("M38 4h9l-3 5 3 5h-9Z")))

    phone = rect(6, 3, 26, 44, 5)
    ok = circle(36, 31, 11)
    i["proof_delivery"] = (fill(P, phone) + stroke(Y, path("M11 20c3-5 5-5 7 0s4 5 8 0"), 3.5)
                           + fill(T, ok) + over(TD, phone, ok)
                           + stroke("#ffffff", path("M31 31l3.5 3.5 6.5-6.5"), 3.2))

    # ---- Personal -------------------------------------------------------
    cal = rect(4, 8, 42, 38, 5)
    i["hr_novelties"] = (fill(T, cal) + over(TD, cal, rect(4, 8, 42, 10))
                         + fill(P, rect(13, 3, 5, 11, 2.5), rect(32, 3, 5, 11, 2.5))
                         + fill(Y, rect(22, 23, 6, 18, 3), rect(16, 29, 18, 6, 3)))

    i["hr_documents"] = (fill(Y, path("M4 10a4 4 0 0 1 4-4h10l4 4h20a4 4 0 0 1 4 4v28H4Z"))
                         + fill(A, rect(4, 16, 42, 30, 4))
                         + fill(P, circle(25, 26, 5.5), path("M14 43a11 9 0 0 1 22 0Z")))

    note = rect(3, 9, 40, 25, 4)
    coin = circle(35, 35, 11)
    i["payroll"] = (fill(T, note) + fill(TD, circle(16, 21.5, 6)) + fill(Y, coin)
                    + over(TG, note, coin) + fill(O, circle(35, 35, 5)))

    cal = rect(4, 6, 32, 34, 5)
    clk = circle(34, 33, 13)
    i["scheduling"] = (fill(P, cal) + over(PD, cal, rect(4, 6, 32, 9))
                       + fill(Y, clk) + over(O, cal, clk) + stroke(P, path("M34 26v7h6"), 3.5))

    body = path("M4 46v-5a12 12 0 0 1 12-12h6a12 12 0 0 1 12 12v5Z")
    star = path("M38 24l3.2 6.4 7 1-5.1 5 1.2 7L38 40.1 31.7 43.4l1.2-7-5.1-5 7-1Z")
    i["hr_management"] = (fill(T, circle(19, 15, 9), body) + fill(Y, star) + over(TG, body, star))

    pie = circle(22, 26, 18)
    wedge = path("M22 26V8a18 18 0 0 1 17.1 12.4Z")
    i["hr_reports"] = (fill(T, pie) + fill(Y, wedge) + fill(P, rect(38, 30, 8, 16, 2.5))
                       + over(TD, pie, rect(38, 30, 8, 16, 2.5)) + fill(K, circle(42, 24, 3.5)))

    # ---- Industria ------------------------------------------------------
    shield = path("M25 3l18 7v12c0 11-8 19-18 25C15 41 7 33 7 22V10Z")
    i["quality"] = (fill(P, shield) + over(PD, shield, rect(25, 0, 25, 50))
                    + stroke(Y, path("M16 24l6 6 12-12"), 5.5))

    house = rect(8, 22, 34, 24, 3)
    roof = path("M25 4l21 17a2 2 0 0 1-1.3 3.6H5.3A2 2 0 0 1 4 21Z")
    i["assets"] = fill(O, house) + fill(P, roof) + over(W, house, roof) + fill(Y, rect(20, 32, 10, 14, 2))

    # ---- Servicios ------------------------------------------------------
    doc = rect(4, 4, 30, 40, 4)
    seal = circle(34, 31, 10)
    i["contracts"] = (fill(K, doc) + fill(W, rect(10, 12, 16, 4, 2), rect(10, 20, 10, 4, 2))
                      + fill(P, path("M28 36l-3 11 6-3 3 4 1-11Z"), path("M40 36l3 11-6-3-3 4-1-11Z"))
                      + fill(Y, seal) + over(O, doc, seal))

    book = rect(8, 4, 34, 42, 4)
    ok = circle(34, 34, 10)
    i["appointments"] = (fill(P, book) + fill(Y, rect(4, 10, 9, 5, 2.5), rect(4, 22.5, 9, 5, 2.5), rect(4, 35, 9, 5, 2.5))
                         + fill(T, ok) + over(TD, book, ok)
                         + stroke("#ffffff", path("M29.5 34l3 3 5.5-5.5"), 3))

    ring = circle(25, 25, 15)
    dashed = ring.replace("/>", ' stroke-dasharray="11.78 11.78" stroke-dashoffset="5.89"/>')
    i["helpdesk"] = stroke(Y, ring, 11) + stroke(K, dashed, 11) + fill(P, circle(25, 25, 4))

    pin = path("M25 46S8 31 8 20a17 17 0 0 1 34 0c0 11-17 26-17 26Z")
    i["service_orders"] = (fill(O, pin) + fill(Y, circle(25, 20, 9))
                           + fill(P, rect(22.5, 10, 5, 20, 2.5, ' transform="rotate(45 25 20)"')))

    # ---- Comunicación ---------------------------------------------------
    i["ocr"] = (stroke(T, path("M5 15V9a4 4 0 0 1 4-4h6M35 5h6a4 4 0 0 1 4 4v6M45 35v6a4 4 0 0 1-4 4h-6M15 45H9a4 4 0 0 1-4-4v-6"), 5)
                + fill(P, rect(14, 13, 22, 5, 2.5), rect(14, 32, 16, 5, 2.5)) + fill(O, rect(4, 22.5, 42, 5, 2.5)))

    card = rect(11, 4, 28, 22, 3)
    env = rect(4, 16, 42, 30, 4)
    i["templates"] = (fill(P, card) + fill(Y, env) + over(O, env, card)
                      + fill(K, path("M4 20l21 15 21-15v-0.5a3.5 3.5 0 0 0-3.5-3.5h-35A3.5 3.5 0 0 0 4 19.5Z")))

    bolt = path("M29 2L9 28h14l-4 20 22-28H27Z")
    i["automations"] = fill(P, circle(25, 25, 17)) + fill(Y, bolt) + over(O, circle(25, 25, 17), bolt)

    # ---- Gestión --------------------------------------------------------
    i["executive_dashboard"] = (fill(P, rect(4, 4, 26, 22, 4)) + fill(Y, rect(33, 4, 13, 22, 4))
                                + fill(T, rect(4, 29, 42, 17, 4))
                                + stroke(TD, path("M10 40l8-5 7 3 10-6 5 2"), 3.5))

    neck = path("M18 4h14l-4 8h-6Z")
    bag = path("M25 12c12 0 19 12 19 21 0 7-5 13-12 13H18C11 46 6 40 6 33c0-9 7-21 19-21Z")
    arr = path("M36 4l10 10h-6v14h-8V14h-6Z")
    i["profitability"] = fill(Y, neck) + fill(P, bag) + fill(T, arr) + over(TD, bag, arr)

    back = path("M4 46V30c6 0 8-12 15-12s9 10 15 6l12-8v30Z")
    front = path("M4 46V36c8-2 10-20 20-20s10 18 22 12v18Z")
    coin = circle(13, 12, 8)
    i["cash_flow"] = fill(Y, back) + fill(P, coin) + fill(T, front) + over(TG, back, front) + over(PD, back, coin)

    doc = rect(4, 4, 28, 34, 4)
    lens = circle(28, 26, 12)
    i["audit"] = (fill(Y, doc) + stroke(P, lens, 7) + fill(P, rect(34, 33, 7, 16, 3.5, ' transform="rotate(-45 37.5 41)"'))
                  + over(O, doc, path("M28 14a12 12 0 1 0 0.01 0Z")))

    bell = path("M25 4a4 4 0 0 1 4 4v1a13 13 0 0 1 9 12v9l5 7H7l5-7v-9a13 13 0 0 1 9-12V8a4 4 0 0 1 4-4Z")
    i["alerts"] = (fill(Y, bell) + fill(P, circle(25, 43, 5)) + fill(K, circle(39, 11, 8))
                   + over(O, bell, circle(39, 11, 8)))

    bubble = path("M25 4a20 20 0 1 1-9.3 37.7L6 45l3.3-9.3A20 20 0 0 1 25 4Z")
    i["help"] = (fill(T, bubble) + stroke(P, path("M18.5 19a6.5 6.5 0 1 1 9.5 5.8c-2 1-3 2.6-3 4.6"), 5.5)
                 + fill(P, circle(25, 36, 3.5)))

    i["owner_dashboard"] = (stroke(K, path("M8 36A17 17 0 0 1 13 24"), 9) + stroke(Y, path("M15 21.5A17 17 0 0 1 35 21.5"), 9)
                            + stroke(T, path("M37 24A17 17 0 0 1 42 36"), 9)
                            + stroke(P, path("M25 36L34 25"), 5) + fill(P, circle(25, 36, 5)) + fill(PD, rect(6, 43, 38, 4, 2)))

    i["budget"] = (fill(K, circle(21, 29, 17)) + fill(W, circle(21, 29, 10)) + fill(K, circle(21, 29, 4))
                   + stroke(T, path("M21 29L42 8"), 4.5) + fill(T, path("M34 4h12v12l-4-4-4-4Z")))

    # ---- Configuración --------------------------------------------------
    tall, low = rect(5, 4, 22, 42, 3), rect(23, 18, 22, 28, 3)
    i["companies"] = (fill(P, tall) + fill(T, low) + over(TD, tall, low)
                      + fill(Y, rect(10, 10, 5, 5, 1.5), rect(17, 10, 5, 5, 1.5), rect(10, 20, 5, 5, 1.5)))

    i["branches"] = (stroke(N, path("M25 10v13M25 23L10 40M25 23l15 17"), 5)
                     + fill(P, circle(25, 10, 7)) + fill(T, circle(10, 40, 7)) + fill(Y, circle(40, 40, 7)))

    body = path("M4 46v-6a12 12 0 0 1 12-12h6a12 12 0 0 1 12 12v6Z")
    lock = rect(28, 30, 18, 15, 3)
    i["users"] = (fill(K, circle(19, 15, 9.5), body) + stroke(P, path("M32 31v-4a5 5 0 0 1 10 0v4"), 3.5)
                  + fill(P, lock) + over(W, body, lock))

    doc = rect(4, 4, 28, 38, 4)
    g = gear(34, 33, 13, 9.5)
    i["fiscal_settings"] = fill(BL, doc) + fill(N, rect(9, 11, 14, 4, 2)) + fill(Y, g) + over(TG, doc, g) + fill(B, circle(34, 33, 4))

    plug = path("M8 16h26v6a13 13 0 0 1-26 0Z")
    socket = rect(30, 28, 16, 18, 4)
    i["integrations"] = (fill(Y, rect(13, 4, 5, 14, 2.5), rect(24, 4, 5, 14, 2.5)) + fill(T, socket) + fill(P, plug)
                         + over(TD, socket, plug) + fill(P, rect(18, 33, 6, 10, 3)))

    tray = path("M4 30h12l3 6h12l3-6h12v12a4 4 0 0 1-4 4H8a4 4 0 0 1-4-4Z")
    arrow = path("M19 4h12v15h8L25 34 11 19h8Z")
    i["imports"] = fill(T, tray) + fill(P, arrow) + over(TD, tray, arrow)

    i["app_catalog"] = (fill(P, rect(4, 4, 19, 19, 5)) + fill(Y, rect(27, 4, 19, 19, 5)) + fill(T, rect(4, 27, 19, 19, 5))
                        + fill(K, rect(33, 27, 7, 19, 3.5), rect(27, 33, 19, 7, 3.5)))

    cyl = path("M6 12c0-5 30-5 30 0v28c0 5-30 5-30 0Z")
    badge = circle(36, 36, 11)
    i["backups"] = (fill(B, cyl) + fill(BL, path("M6 12c0-5 30-5 30 0s-30 5-30 0Z"))
                    + stroke(N, path("M7 26c4 4 24 4 28 0"), 3) + fill(Y, badge) + over(A, cyl, badge)
                    + stroke(N, path("M36 30v11M31.5 37l4.5 4.5 4.5-4.5"), 3))

    tile = rect(4, 4, 42, 42, 9)
    i["diagnostics"] = fill(K, tile) + stroke(W, path("M7 27h8l4-10 7 18 4-10h13"), 5)
    return i


GAP = 2.2  # separación transparente entre formas en la versión de un color


def _attrs(shape, attrs):
    return shape.replace("/>", f" {attrs}/>", 1)


def render_mono(layers):
    """Versión de un solo color para el estilo Mosaico (se usa como máscara).

    Mismo dibujo que el ícono de Odoo, con el estilo de los íconos rellenos de
    Fluent: formas macizas separadas por una línea transparente donde una pisa a
    otra. Las zonas «over» desaparecen (en un color no se distinguen) y los
    trazos blancos de detalle se recortan.
    """
    overs = [layer for layer in layers if layer[0] == "over"]
    layers = [layer for layer in layers if layer[0] != "over"]
    defs, body = [], []
    # El borde de una zona «over» sigue marcado con una línea transparente dentro de
    # la forma que pisa (así el impuesto conserva la barra del porcentaje).
    over_cutters = []
    for n, (_kind, _color, base, shape, _edge) in enumerate(o for o in overs if o[4]):
        defs.append(f'<clipPath id="o{n}">{base}</clipPath>')
        over_cutters.append((shape, f'<g clip-path="url(#o{n})">' + _attrs(
            shape, f'fill="none" stroke="#000" stroke-width="{GAP * 2}" stroke-linejoin="round"') + "</g>"))
    for index, layer in enumerate(layers):
        kind, color = layer[0], layer[1]
        if kind == "stroke" and color.lower() == "#ffffff":
            continue  # detalle blanco: solo recorta
        cutters = []
        for later in layers[index + 1:]:
            if later[0] == "fill":
                cutters.append(_attrs(later[2], f'fill="#000" stroke="#000" stroke-width="{GAP * 2}" stroke-linejoin="round"'))
            else:
                gap = 0 if later[1].lower() == "#ffffff" else GAP * 2
                cutters.append(_attrs(later[2], f'fill="none" stroke="#000" stroke-width="{later[3] + gap}" '
                                                'stroke-linecap="round" stroke-linejoin="round"'))
        cutters += [cut for shape, cut in over_cutters if shape != layer[2]]
        if kind == "fill":
            shape = _attrs(layer[2], 'fill="#212121"')
        else:
            shape = _attrs(layer[2], f'fill="none" stroke="#212121" stroke-width="{layer[3]}" '
                                     'stroke-linecap="round" stroke-linejoin="round"')
        if cutters:
            mid = f"m{index}"
            defs.append(f'<mask id="{mid}" maskUnits="userSpaceOnUse" x="-5" y="-5" width="60" height="60">'
                        f'<rect x="-5" y="-5" width="60" height="60" fill="#fff"/>{"".join(cutters)}</mask>')
            body.append(f'<g mask="url(#{mid})">{shape}</g>')
        else:
            body.append(shape)
    head = '<svg width="50" height="50" viewBox="0 0 50 50" xmlns="http://www.w3.org/2000/svg">'
    return f"{head}<defs>{''.join(defs)}</defs>{''.join(body)}</svg>\n"


def _mix(color, other, amount):
    a = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(other[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b))


def render_3d(layers):
    """Versión con volumen para el estilo Expresivo 3D: el mismo dibujo, cada forma
    con degradé de claro a oscuro y una sombra suave, sin mosaico de fondo, como
    los objetos de Fluent 3D del resto del set."""
    defs, body, grads = [], [], {}

    def grad(color):
        if color not in grads:
            gid = f"g{len(grads)}"
            grads[color] = gid
            defs.append(f'<linearGradient id="{gid}" x1="0" y1="0" x2=".35" y2="1">'
                        f'<stop stop-color="{_mix(color, "#ffffff", .38)}"/>'
                        f'<stop offset=".55" stop-color="{color}"/>'
                        f'<stop offset="1" stop-color="{_mix(color, "#1b1030", .22)}"/></linearGradient>')
        return grads[color]

    for layer in layers:
        kind = layer[0]
        if kind == "fill":
            body.append(_attrs(layer[2], f'fill="url(#{grad(layer[1])})"'))
        elif kind == "over":
            cid = f"c{len(defs)}"
            defs.append(f'<clipPath id="{cid}">{layer[2]}</clipPath>')
            body.append(_attrs(layer[3], f'fill="url(#{grad(layer[1])})" clip-path="url(#{cid})"'))
        else:
            color = layer[1] if layer[1].lower() == "#ffffff" else _mix(layer[1], "#ffffff", .1)
            body.append(_attrs(layer[2], f'fill="none" stroke="{color}" stroke-width="{layer[3]}" '
                                         'stroke-linecap="round" stroke-linejoin="round"'))
    defs.append('<filter id="shadow" x="-20%" y="-20%" width="150%" height="160%">'
                '<feDropShadow dx="0.6" dy="2.4" stdDeviation="1.8" flood-color="#27213c" flood-opacity=".3"/></filter>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
            f"<defs>{''.join(defs)}</defs>"
            f'<g transform="translate(7 5) scale(1.64)" filter="url(#shadow)">{"".join(body)}</g></svg>\n')


LAYERS = _icons()
ODOO_ICONS = {name: render(layers) for name, layers in LAYERS.items()}
MONO_ICONS = {name: render_mono(layers) for name, layers in LAYERS.items()}
VOLUME_ICONS = {name: render_3d(layers) for name, layers in LAYERS.items()}
