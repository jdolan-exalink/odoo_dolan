"""Ilustraciones propias para los estilos ilustrados del theme (Expresivo 3D y Flat).

Cuando una app del catálogo pasa a tener implementación real, deja de usar el
mosaico genérico generado y recibe un objeto ilustrado propio, como el resto de
las apps del set: volumen con degradés y sombra en fluent_3d, colores planos con
contorno en fluent_flat. Los estilos de máscara (Mosaico, Contorno, Tabler)
siguen usando el glifo de app_catalog_glyphs.py, que tiene la misma silueta.

Dibujos propios del proyecto (LGPL-3). La paleta de cada app sale del área de su
carpeta para que las apps de un mismo grupo se reconozcan juntas.
"""

SHADOW = ('<filter id="shadow" x="-20%" y="-20%" width="150%" height="160%">'
          '<feDropShadow dx="1" dy="4" stdDeviation="3" flood-color="#27213c" flood-opacity=".28"/></filter>')

ILLUSTRATIONS = {
    # Mesa de ayuda: salvavidas con un ticket colgando (área Servicios, ámbar).
    "helpdesk": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <radialGradient id="ring" cx=".4" cy=".35" r=".75"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#e6e1d6"/></radialGradient>
    <linearGradient id="band" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffcf5c"/><stop offset="1" stop-color="#d97706"/></linearGradient>
    <linearGradient id="ticket" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#fff7e6"/><stop offset="1" stop-color="#ffe0a3"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <circle cx="44" cy="42" r="27" fill="none" stroke="url(#ring)" stroke-width="17"/>
    <circle cx="44" cy="42" r="27" fill="none" stroke="url(#band)" stroke-width="17" stroke-dasharray="21 21.4" transform="rotate(-34 44 42)"/>
    <circle cx="44" cy="42" r="35.5" fill="none" stroke="#b45309" stroke-opacity=".35" stroke-width="1.5"/>
    <circle cx="44" cy="42" r="18.5" fill="none" stroke="#b45309" stroke-opacity=".35" stroke-width="1.5"/>
    <path d="M65 62l9 9" stroke="#8a5a1f" stroke-width="3" stroke-linecap="round"/>
    <path d="M66 70h22a4 4 0 0 1 4 4v4a4 4 0 0 0 0 8v0a4 4 0 0 1-4 4H66a4 4 0 0 1-4-4v0a4 4 0 0 0 0-8v-4a4 4 0 0 1 4-4Z" fill="url(#ticket)" stroke="#d97706" stroke-width="2"/>
    <path d="M70 78h14M70 83h9" stroke="#c27803" stroke-width="2.5" stroke-linecap="round"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <circle cx="44" cy="42" r="27" fill="none" stroke="#fffaf0" stroke-width="17"/>
  <circle cx="44" cy="42" r="27" fill="none" stroke="#f6bd3a" stroke-width="17" stroke-dasharray="21 21.4" transform="rotate(-34 44 42)"/>
  <circle cx="44" cy="42" r="35.5" fill="none" stroke="#c27803" stroke-width="2.5"/>
  <circle cx="44" cy="42" r="18.5" fill="none" stroke="#c27803" stroke-width="2.5"/>
  <path d="M65 62l9 9" stroke="#8a5a1f" stroke-width="3" stroke-linecap="round"/>
  <path d="M66 70h22a4 4 0 0 1 4 4v4a4 4 0 0 0 0 8v0a4 4 0 0 1-4 4H66a4 4 0 0 1-4-4v0a4 4 0 0 0 0-8v-4a4 4 0 0 1 4-4Z" fill="#fff4dc" stroke="#c27803" stroke-width="2.5"/>
  <path d="M70 78h14M70 83h9" stroke="#c27803" stroke-width="2.5" stroke-linecap="round"/>
</svg>
""",
    },
    # Agenda de turnos: agenda anillada con señalador y un tilde de turno confirmado (área Servicios).
    "appointments": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="cover" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffd166"/><stop offset="1" stop-color="#d97706"/></linearGradient>
    <linearGradient id="paper" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#f1ece2"/></linearGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#9aa3b5"/><stop offset=".5" stop-color="#eef1f6"/><stop offset="1" stop-color="#7c859a"/></linearGradient>
    <linearGradient id="badge" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#5eead4"/><stop offset="1" stop-color="#0f9488"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <rect x="18" y="8" width="58" height="74" rx="9" fill="url(#cover)"/>
    <rect x="25" y="13" width="47" height="64" rx="5" fill="url(#paper)"/>
    <path d="M60 8h9v26l-4.5-4-4.5 4Z" fill="#dc2626"/>
    <g fill="#e2d9c6"><rect x="33" y="24" width="24" height="4" rx="2"/><rect x="33" y="34" width="30" height="4" rx="2"/><rect x="33" y="44" width="20" height="4" rx="2"/></g>
    <g fill="none" stroke="url(#ring)" stroke-width="4" stroke-linecap="round">
      <path d="M12 20h14"/><path d="M12 34h14"/><path d="M12 48h14"/><path d="M12 62h14"/>
    </g>
    <circle cx="66" cy="68" r="17" fill="url(#badge)" stroke="#ffffff" stroke-width="3"/>
    <path d="M58 68l6 6 10-11" fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <rect x="18" y="8" width="58" height="74" rx="9" fill="#f6bd3a"/>
  <rect x="25" y="13" width="47" height="64" rx="5" fill="#ffffff"/>
  <path d="M60 8h9v26l-4.5-4-4.5 4Z" fill="#e5484d"/>
  <g fill="#f1e4c8"><rect x="33" y="24" width="24" height="4" rx="2"/><rect x="33" y="34" width="30" height="4" rx="2"/><rect x="33" y="44" width="20" height="4" rx="2"/></g>
  <g fill="none" stroke="#7c859a" stroke-width="4" stroke-linecap="round">
    <path d="M12 20h14"/><path d="M12 34h14"/><path d="M12 48h14"/><path d="M12 62h14"/>
  </g>
  <circle cx="66" cy="68" r="17" fill="#14b8a6" stroke="#ffffff" stroke-width="3"/>
  <path d="M58 68l6 6 10-11" fill="none" stroke="#ffffff" stroke-width="5" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
""",
    },
    # Órdenes de servicio: pin de ubicación con llave de trabajo (trabajo en el domicilio del cliente).
    "service_orders": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="pin" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#ffcf5c"/><stop offset="1" stop-color="#c2410c"/></linearGradient>
    <radialGradient id="face" cx=".4" cy=".35" r=".8"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#ece7dd"/></radialGradient>
    <linearGradient id="steel" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#cfd6e3"/><stop offset="1" stop-color="#6b7488"/></linearGradient>
    <radialGradient id="ground" cx=".5" cy=".5" r=".5"><stop stop-color="#27213c" stop-opacity=".3"/><stop offset="1" stop-color="#27213c" stop-opacity="0"/></radialGradient>
    {SHADOW}
  </defs>
  <ellipse cx="48" cy="86" rx="22" ry="6" fill="url(#ground)"/>
  <g filter="url(#shadow)">
    <path d="M48 86S20 60 20 37a28 28 0 0 1 56 0c0 23-28 49-28 49Z" fill="url(#pin)"/>
    <circle cx="48" cy="37" r="18" fill="url(#face)"/>
    <path d="M40 46l12-12" stroke="url(#steel)" stroke-width="6" stroke-linecap="round"/>
    <path d="M57.5 25.5a7 7 0 1 0 3.2 11.3l-6.4-2.5-.6-6.6Z" fill="url(#steel)"/>
    <circle cx="39.5" cy="46.5" r="3.5" fill="#6b7488"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <ellipse cx="48" cy="86" rx="20" ry="5" fill="#27213c" fill-opacity=".15"/>
  <path d="M48 86S20 60 20 37a28 28 0 0 1 56 0c0 23-28 49-28 49Z" fill="#f59e0b"/>
  <circle cx="48" cy="37" r="18" fill="#ffffff"/>
  <path d="M40 46l12-12" stroke="#64748b" stroke-width="6" stroke-linecap="round"/>
  <path d="M57.5 25.5a7 7 0 1 0 3.2 11.3l-6.4-2.5-.6-6.6Z" fill="#64748b"/>
  <circle cx="39.5" cy="46.5" r="3.5" fill="#475569"/>
</svg>
""",
    },
    # Contratos: hoja firmada con sello de lacre y cinta (área Servicios).
    "contracts": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="sheet" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#efe8da"/></linearGradient>
    <linearGradient id="fold" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f4ead6"/><stop offset="1" stop-color="#d9cbb0"/></linearGradient>
    <radialGradient id="seal" cx=".4" cy=".35" r=".8"><stop stop-color="#ffd166"/><stop offset="1" stop-color="#c27803"/></radialGradient>
    <linearGradient id="ribbon" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#e5484d"/><stop offset="1" stop-color="#a1191f"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <path d="M18 8h40l18 18v58a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4V12a4 4 0 0 1 4-4Z" fill="url(#sheet)"/>
    <path d="M58 8v14a4 4 0 0 0 4 4h14Z" fill="url(#fold)"/>
    <g fill="#d6ccb8"><rect x="24" y="24" width="26" height="4" rx="2"/><rect x="24" y="34" width="40" height="4" rx="2"/><rect x="24" y="44" width="34" height="4" rx="2"/></g>
    <path d="M24 66c4-7 7-7 9 0 2 5 4 5 7-1" fill="none" stroke="#1d4ed8" stroke-width="3" stroke-linecap="round"/>
    <path d="M58 72l-4 18 8-4 8 4-4-18Z" fill="url(#ribbon)"/>
    <circle cx="62" cy="66" r="13" fill="url(#seal)" stroke="#fff3d6" stroke-width="2.5"/>
    <path d="M62 58.5l2.2 4.5 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5-3.6-3.5 5-.7Z" fill="#fff3d6"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <path d="M18 8h40l18 18v58a4 4 0 0 1-4 4H18a4 4 0 0 1-4-4V12a4 4 0 0 1 4-4Z" fill="#ffffff" stroke="#c27803" stroke-width="2.5"/>
  <path d="M58 8v14a4 4 0 0 0 4 4h14Z" fill="#fde7b0"/>
  <g fill="#f1e4c8"><rect x="24" y="24" width="26" height="4" rx="2"/><rect x="24" y="34" width="40" height="4" rx="2"/><rect x="24" y="44" width="34" height="4" rx="2"/></g>
  <path d="M24 66c4-7 7-7 9 0 2 5 4 5 7-1" fill="none" stroke="#2563eb" stroke-width="3" stroke-linecap="round"/>
  <path d="M58 72l-4 18 8-4 8 4-4-18Z" fill="#e5484d"/>
  <circle cx="62" cy="66" r="13" fill="#f6bd3a" stroke="#ffffff" stroke-width="2.5"/>
  <path d="M62 58.5l2.2 4.5 5 .7-3.6 3.5.9 5-4.5-2.4-4.5 2.4.9-5-3.6-3.5 5-.7Z" fill="#ffffff"/>
</svg>
""",
    },
    # Cuentas corrientes: ficha de cliente con flechas de debe y haber (área Finanzas, azul).
    "current_accounts": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="card" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#e3ecfb"/></linearGradient>
    <linearGradient id="head" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#6ea8ff"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient>
    <linearGradient id="avatar" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#93c5fd"/><stop offset="1" stop-color="#2563eb"/></linearGradient>
    <linearGradient id="up" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#4ade80"/><stop offset="1" stop-color="#15803d"/></linearGradient>
    <linearGradient id="down" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#fb7185"/><stop offset="1" stop-color="#be123c"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <rect x="8" y="14" width="80" height="64" rx="12" fill="url(#card)"/>
    <path d="M20 14h56a12 12 0 0 1 12 12v2H8v-2a12 12 0 0 1 12-12Z" fill="url(#head)"/>
    <circle cx="30" cy="48" r="9" fill="url(#avatar)"/>
    <path d="M16 70a14 14 0 0 1 28 0Z" fill="url(#avatar)"/>
    <path d="M58 46l8-9 8 9h-5v10h-6V46Z" fill="url(#up)"/>
    <path d="M58 58l8 9 8-9h-5V50h-6v8Z" fill="url(#down)" transform="translate(14 4)"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <rect x="8" y="14" width="80" height="64" rx="12" fill="#ffffff" stroke="#1d4ed8" stroke-width="2.5"/>
  <path d="M20 14h56a12 12 0 0 1 12 12v2H8v-2a12 12 0 0 1 12-12Z" fill="#4b8df8"/>
  <circle cx="30" cy="48" r="9" fill="#4b8df8"/>
  <path d="M16 70a14 14 0 0 1 28 0Z" fill="#4b8df8"/>
  <path d="M58 46l8-9 8 9h-5v10h-6V46Z" fill="#22c55e"/>
  <path d="M58 58l8 9 8-9h-5V50h-6v8Z" fill="#f43f5e" transform="translate(14 4)"/>
</svg>
""",
    },
    # Caja y Tesorería: caja fuerte con perilla y manija (área Finanzas, azul).
    "treasury": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="body" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#7fb0ff"/><stop offset="1" stop-color="#1e40af"/></linearGradient>
    <linearGradient id="door" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#5b8ff0"/><stop offset="1" stop-color="#1d4ed8"/></linearGradient>
    <radialGradient id="dial" cx=".4" cy=".35" r=".8"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#c7d2e6"/></radialGradient>
    <linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffe08a"/><stop offset="1" stop-color="#d4a017"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <rect x="12" y="12" width="72" height="66" rx="10" fill="url(#body)"/>
    <rect x="19" y="19" width="58" height="52" rx="7" fill="url(#door)" stroke="#9ec0ff" stroke-width="1.5"/>
    <circle cx="42" cy="45" r="14" fill="url(#dial)"/>
    <circle cx="42" cy="45" r="5" fill="#1e40af"/>
    <g stroke="#1e40af" stroke-width="2.5" stroke-linecap="round"><path d="M42 33v4M42 57v-4M30 45h4M54 45h-4"/></g>
    <rect x="63" y="34" width="6" height="22" rx="3" fill="url(#gold)"/>
    <rect x="18" y="78" width="10" height="7" rx="2" fill="#1e3a8a"/><rect x="68" y="78" width="10" height="7" rx="2" fill="#1e3a8a"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <rect x="12" y="12" width="72" height="66" rx="10" fill="#1d4ed8"/>
  <rect x="19" y="19" width="58" height="52" rx="7" fill="#4b8df8"/>
  <circle cx="42" cy="45" r="14" fill="#ffffff"/>
  <circle cx="42" cy="45" r="5" fill="#1d4ed8"/>
  <g stroke="#1d4ed8" stroke-width="2.5" stroke-linecap="round"><path d="M42 33v4M42 57v-4M30 45h4M54 45h-4"/></g>
  <rect x="63" y="34" width="6" height="22" rx="3" fill="#f6bd3a"/>
  <rect x="18" y="78" width="10" height="7" rx="2" fill="#1e3a8a"/><rect x="68" y="78" width="10" height="7" rx="2" fill="#1e3a8a"/>
</svg>
""",
    },
    # Turnos de caja: cajón abierto con billetes y flecha de traspaso entre turnos (área Punto de venta).
    "cash_shifts": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="drawer" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#b79cfb"/><stop offset="1" stop-color="#5b21b6"/></linearGradient>
    <linearGradient id="front" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#8b5cf6"/><stop offset="1" stop-color="#4c1d95"/></linearGradient>
    <linearGradient id="bill" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#86efac"/><stop offset="1" stop-color="#16a34a"/></linearGradient>
    <linearGradient id="arrow" x1="0" y1="0" x2="1" y2="0"><stop stop-color="#fbbf24"/><stop offset="1" stop-color="#d97706"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <path d="M10 50l8-14h60l8 14Z" fill="url(#drawer)"/>
    <g transform="rotate(-6 40 42)"><rect x="24" y="34" width="22" height="14" rx="2" fill="url(#bill)"/></g>
    <g transform="rotate(5 58 42)"><rect x="48" y="34" width="22" height="14" rx="2" fill="url(#bill)"/></g>
    <path d="M10 50h76v26a6 6 0 0 1-6 6H16a6 6 0 0 1-6-6Z" fill="url(#front)"/>
    <rect x="38" y="62" width="20" height="6" rx="3" fill="#ede9fe"/>
    <path d="M28 22a24 24 0 0 1 40 0" fill="none" stroke="url(#arrow)" stroke-width="5" stroke-linecap="round"/>
    <path d="M70 10l-1 14-13-4Z" fill="#d97706"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <path d="M10 50l8-14h60l8 14Z" fill="#a78bfa"/>
  <g transform="rotate(-6 40 42)"><rect x="24" y="34" width="22" height="14" rx="2" fill="#22c55e"/></g>
  <g transform="rotate(5 58 42)"><rect x="48" y="34" width="22" height="14" rx="2" fill="#22c55e"/></g>
  <path d="M10 50h76v26a6 6 0 0 1-6 6H16a6 6 0 0 1-6-6Z" fill="#7c3aed"/>
  <rect x="38" y="62" width="20" height="6" rx="3" fill="#ede9fe"/>
  <path d="M28 22a24 24 0 0 1 40 0" fill="none" stroke="#f59e0b" stroke-width="5" stroke-linecap="round"/>
  <path d="M70 10l-1 14-13-4Z" fill="#f59e0b"/>
</svg>
""",
    },
    # Costos: etiqueta de precio sobre una pila de monedas (área Inventario y Compras, naranja).
    "costs": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="tag" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fdba74"/><stop offset="1" stop-color="#c2410c"/></linearGradient>
    <linearGradient id="coin" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#fde68a"/><stop offset="1" stop-color="#d4a017"/></linearGradient>
    <linearGradient id="coinside" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#e0b030"/><stop offset="1" stop-color="#a87a08"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <path d="M50 8h28a6 6 0 0 1 6 6v28L52 74 18 40Z" fill="url(#tag)"/>
    <circle cx="70" cy="22" r="6" fill="#fff7ed"/>
    <path d="M38 40l16-16M44 46l14-14" stroke="#fff7ed" stroke-width="4" stroke-linecap="round" opacity=".8"/>
    <g>
      <path d="M12 74v8c0 4 9 7 20 7s20-3 20-7v-8" fill="url(#coinside)"/>
      <ellipse cx="32" cy="74" rx="20" ry="7" fill="url(#coin)"/>
      <path d="M12 64v8c0 4 9 7 20 7s20-3 20-7v-8" fill="url(#coinside)"/>
      <ellipse cx="32" cy="64" rx="20" ry="7" fill="url(#coin)"/>
      <text x="32" y="68" font-family="Arial, sans-serif" font-size="11" font-weight="700" text-anchor="middle" fill="#8a5a00">$</text>
    </g>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <path d="M50 8h28a6 6 0 0 1 6 6v28L52 74 18 40Z" fill="#fb923c"/>
  <circle cx="70" cy="22" r="6" fill="#ffffff"/>
  <path d="M38 40l16-16M44 46l14-14" stroke="#ffedd5" stroke-width="4" stroke-linecap="round"/>
  <path d="M12 74v8c0 4 9 7 20 7s20-3 20-7v-8" fill="#ca8a04"/>
  <ellipse cx="32" cy="74" rx="20" ry="7" fill="#facc15"/>
  <path d="M12 64v8c0 4 9 7 20 7s20-3 20-7v-8" fill="#ca8a04"/>
  <ellipse cx="32" cy="64" rx="20" ry="7" fill="#facc15"/>
  <text x="32" y="68" font-family="Arial, sans-serif" font-size="11" font-weight="700" text-anchor="middle" fill="#854d0e">$</text>
</svg>
""",
    },
    # Flujo de caja: tarjeta con la curva de saldo y el tramo proyectado punteado (área Gestión y Análisis, rosa).
    "cash_flow": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="card" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#fbe4ef"/></linearGradient>
    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#f178b0" stop-opacity=".55"/><stop offset="1" stop-color="#f178b0" stop-opacity="0"/></linearGradient>
    <linearGradient id="coin" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#fde68a"/><stop offset="1" stop-color="#d4a017"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <rect x="8" y="14" width="80" height="66" rx="12" fill="url(#card)"/>
    <path d="M16 64c8 0 10-18 18-18s10 10 16 10V72H16Z" fill="url(#area)"/>
    <path d="M16 64c8 0 10-18 18-18s10 10 16 10" fill="none" stroke="#c42d72" stroke-width="4" stroke-linecap="round"/>
    <path d="M50 56c8 0 10-20 18-20s8 6 12 6" fill="none" stroke="#c42d72" stroke-width="4" stroke-linecap="round" stroke-dasharray="2 7"/>
    <path d="M50 22v52" stroke="#e9a8c6" stroke-width="2" stroke-dasharray="3 4"/>
    <circle cx="74" cy="26" r="11" fill="url(#coin)" stroke="#fff3d6" stroke-width="2"/>
    <text x="74" y="30.5" font-family="Arial, sans-serif" font-size="12" font-weight="700" text-anchor="middle" fill="#8a5a00">$</text>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <rect x="8" y="14" width="80" height="66" rx="12" fill="#ffffff" stroke="#c42d72" stroke-width="2.5"/>
  <path d="M16 64c8 0 10-18 18-18s10 10 16 10V72H16Z" fill="#fbd0e3"/>
  <path d="M16 64c8 0 10-18 18-18s10 10 16 10" fill="none" stroke="#c42d72" stroke-width="4" stroke-linecap="round"/>
  <path d="M50 56c8 0 10-20 18-20s8 6 12 6" fill="none" stroke="#c42d72" stroke-width="4" stroke-linecap="round" stroke-dasharray="2 7"/>
  <path d="M50 22v52" stroke="#f0b5cf" stroke-width="2" stroke-dasharray="3 4"/>
  <circle cx="74" cy="26" r="11" fill="#facc15" stroke="#ffffff" stroke-width="2"/>
  <text x="74" y="30.5" font-family="Arial, sans-serif" font-size="12" font-weight="700" text-anchor="middle" fill="#854d0e">$</text>
</svg>
""",
    },
    # Rentabilidad: bolsa de dinero con flecha de crecimiento.
    "profitability": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <radialGradient id="bag" cx=".4" cy=".35" r=".8"><stop stop-color="#f9a8d4"/><stop offset="1" stop-color="#be185d"/></radialGradient>
    <linearGradient id="tie" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#fde68a"/><stop offset="1" stop-color="#d4a017"/></linearGradient>
    <linearGradient id="arrow" x1="0" y1="1" x2="0" y2="0"><stop stop-color="#16a34a"/><stop offset="1" stop-color="#4ade80"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <path d="M36 14h22l-6 12H42Z" fill="url(#bag)"/>
    <path d="M40 26C22 34 14 50 14 62c0 12 8 20 20 20h26c12 0 20-8 20-20 0-12-8-28-26-36Z" fill="url(#bag)"/>
    <rect x="38" y="23" width="18" height="6" rx="3" fill="url(#tie)"/>
    <text x="47" y="66" font-family="Arial, sans-serif" font-size="26" font-weight="700" text-anchor="middle" fill="#fff0f7">$</text>
    <path d="M66 70V40" stroke="url(#arrow)" stroke-width="8" stroke-linecap="round"/>
    <path d="M54 46l12-14 12 14Z" fill="#22c55e"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <path d="M36 14h22l-6 12H42Z" fill="#ec4899"/>
  <path d="M40 26C22 34 14 50 14 62c0 12 8 20 20 20h26c12 0 20-8 20-20 0-12-8-28-26-36Z" fill="#f472b6"/>
  <rect x="38" y="23" width="18" height="6" rx="3" fill="#facc15"/>
  <text x="47" y="66" font-family="Arial, sans-serif" font-size="26" font-weight="700" text-anchor="middle" fill="#ffffff">$</text>
  <path d="M66 70V40" stroke="#22c55e" stroke-width="8" stroke-linecap="round"/>
  <path d="M54 46l12-14 12 14Z" fill="#22c55e"/>
</svg>
""",
    },
    # Auditoría: lupa sobre una hoja de registro con huella.
    "audit": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="sheet" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#f6e3ec"/></linearGradient>
    <radialGradient id="glass" cx=".35" cy=".3" r=".8"><stop stop-color="#ffffff" stop-opacity=".95"/><stop offset="1" stop-color="#fbcfe2" stop-opacity=".75"/></radialGradient>
    <linearGradient id="ring" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f178b0"/><stop offset="1" stop-color="#9d174d"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <rect x="12" y="8" width="54" height="70" rx="8" fill="url(#sheet)"/>
    <g fill="#e9c4d5"><rect x="20" y="20" width="30" height="4" rx="2"/><rect x="20" y="30" width="38" height="4" rx="2"/><rect x="20" y="40" width="24" height="4" rx="2"/></g>
    <circle cx="58" cy="56" r="20" fill="url(#glass)" stroke="url(#ring)" stroke-width="6"/>
    <g fill="none" stroke="#c42d72" stroke-width="2" stroke-linecap="round">
      <path d="M50 58a8 8 0 0 1 16 0"/><path d="M53 62a5 5 0 0 1 10 0"/><path d="M47 54a11 11 0 0 1 22 0"/>
    </g>
    <path d="M73 71l13 13" stroke="url(#ring)" stroke-width="9" stroke-linecap="round"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <rect x="12" y="8" width="54" height="70" rx="8" fill="#ffffff" stroke="#c42d72" stroke-width="2.5"/>
  <g fill="#f5cfe0"><rect x="20" y="20" width="30" height="4" rx="2"/><rect x="20" y="30" width="38" height="4" rx="2"/><rect x="20" y="40" width="24" height="4" rx="2"/></g>
  <circle cx="58" cy="56" r="20" fill="#fde7f0" stroke="#db2777" stroke-width="6"/>
  <g fill="none" stroke="#c42d72" stroke-width="2" stroke-linecap="round">
    <path d="M50 58a8 8 0 0 1 16 0"/><path d="M53 62a5 5 0 0 1 10 0"/><path d="M47 54a11 11 0 0 1 22 0"/>
  </g>
  <path d="M73 71l13 13" stroke="#db2777" stroke-width="9" stroke-linecap="round"/>
</svg>
""",
    },
    # Alertas: campana con aviso rojo.
    "alerts": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <linearGradient id="bell" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#f9a8d4"/><stop offset="1" stop-color="#be185d"/></linearGradient>
    <linearGradient id="clapper" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#fde68a"/><stop offset="1" stop-color="#d4a017"/></linearGradient>
    <radialGradient id="badge" cx=".4" cy=".35" r=".8"><stop stop-color="#fb7185"/><stop offset="1" stop-color="#be123c"/></radialGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <circle cx="44" cy="80" r="8" fill="url(#clapper)"/>
    <path d="M44 12a6 6 0 0 1 6 6v2c12 3 20 14 20 27v14l7 9H17l7-9V47c0-13 8-24 20-27v-2a6 6 0 0 1 6-6Z" fill="url(#bell)" transform="translate(-6 0)"/>
    <path d="M24 46c0-10 6-18 14-21" fill="none" stroke="#fff0f7" stroke-width="4" stroke-linecap="round" opacity=".7"/>
    <circle cx="70" cy="22" r="14" fill="url(#badge)" stroke="#ffffff" stroke-width="3"/>
    <path d="M70 14v10" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/><circle cx="70" cy="30" r="2.4" fill="#ffffff"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <circle cx="44" cy="80" r="8" fill="#facc15"/>
  <path d="M44 12a6 6 0 0 1 6 6v2c12 3 20 14 20 27v14l7 9H17l7-9V47c0-13 8-24 20-27v-2a6 6 0 0 1 6-6Z" fill="#ec4899" transform="translate(-6 0)"/>
  <circle cx="70" cy="22" r="14" fill="#f43f5e" stroke="#ffffff" stroke-width="3"/>
  <path d="M70 14v10" stroke="#ffffff" stroke-width="4" stroke-linecap="round"/><circle cx="70" cy="30" r="2.4" fill="#ffffff"/>
</svg>
""",
    },
    # Presupuesto financiero: diana con flecha clavada en el centro.
    "budget": {
        "fluent_3d": f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <defs>
    <radialGradient id="outer" cx=".4" cy=".35" r=".8"><stop stop-color="#f9a8d4"/><stop offset="1" stop-color="#be185d"/></radialGradient>
    <radialGradient id="mid" cx=".4" cy=".35" r=".8"><stop stop-color="#ffffff"/><stop offset="1" stop-color="#fbe4ef"/></radialGradient>
    <linearGradient id="shaft" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fde68a"/><stop offset="1" stop-color="#b45309"/></linearGradient>
    {SHADOW}
  </defs>
  <g filter="url(#shadow)">
    <circle cx="42" cy="54" r="34" fill="url(#outer)"/>
    <circle cx="42" cy="54" r="24" fill="url(#mid)"/>
    <circle cx="42" cy="54" r="14" fill="url(#outer)"/>
    <circle cx="42" cy="54" r="5" fill="#ffffff"/>
    <path d="M42 54L80 16" stroke="url(#shaft)" stroke-width="5" stroke-linecap="round"/>
    <path d="M74 10l12 0-2 6-8 2 2-8Z M86 10v12l-6-2-2-8Z" fill="#22c55e"/>
  </g>
</svg>
""",
        "fluent_flat": """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
  <circle cx="42" cy="54" r="34" fill="#ec4899"/>
  <circle cx="42" cy="54" r="24" fill="#ffffff"/>
  <circle cx="42" cy="54" r="14" fill="#ec4899"/>
  <circle cx="42" cy="54" r="5" fill="#ffffff"/>
  <path d="M42 54L80 16" stroke="#b45309" stroke-width="5" stroke-linecap="round"/>
  <path d="M74 10l12 0-2 6-8 2 2-8Z M86 10v12l-6-2-2-8Z" fill="#22c55e"/>
</svg>
""",
    },
}
