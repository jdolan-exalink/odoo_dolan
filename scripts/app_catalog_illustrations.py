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
}
