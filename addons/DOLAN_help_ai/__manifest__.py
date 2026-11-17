{
    'name': 'DOLAN Ayuda en el Asistente IA',
    'version': '20.0.1.0.0',
    'summary': 'El Asistente IA responde las preguntas de «cómo se hace» con las guías de la Ayuda',
    'description': """
Puente entre la Ayuda (DOLAN_help) y el Asistente IA (DOLAN_ai): agrega la herramienta
``help_search`` al chat. Cuando el usuario pregunta cómo se hace algo, el asistente busca
en las guías y procedimientos (solo los de las apps que el usuario tiene) y responde con
los pasos y el link a la guía con capturas.
""",
    'author': 'DOLAN',
    'license': 'LGPL-3',
    'category': 'Productivity',
    'depends': ['DOLAN_help', 'DOLAN_ai'],
    'data': [],
    'installable': True,
    'auto_install': True,
}
