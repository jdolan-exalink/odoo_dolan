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
}
