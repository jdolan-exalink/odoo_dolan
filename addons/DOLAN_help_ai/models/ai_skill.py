from odoo import api, models

HELP_TOOL = {
    'type': 'function',
    'function': {
        'name': 'help_search',
        'description': (
            'Busca en la Ayuda de DOLAN ERP (guías paso a paso de cada app y procedimientos de la empresa). '
            'Usala cuando el usuario pregunta CÓMO SE HACE algo en el sistema (emitir una factura, cerrar la caja, '
            'pedir vacaciones, cargar un producto…). Devuelve las guías que mejor coinciden con sus pasos y un link. '
            'Respondé con los pasos resumidos y agregá el link para ver la guía con capturas.'),
        'parameters': {
            'type': 'object',
            'properties': {
                'query': {'type': 'string', 'description': 'Lo que el usuario quiere hacer, en pocas palabras.'},
                'limit': {'type': 'integer', 'description': 'Cuántas guías devolver (1 a 10, por defecto 3).'},
            },
            'required': ['query'],
        },
    },
}


class AiSkill(models.Model):
    _inherit = 'ai.skill'

    @api.model
    def get_openai_tools_spec(self, skills=None):
        tools = super().get_openai_tools_spec(skills=skills)
        if not any(tool.get('function', {}).get('name') == 'help_search' for tool in tools):
            tools.append(HELP_TOOL)
        return tools

    @api.model
    def execute_skill_tool(self, tool_name, params=None):
        if tool_name != 'help_search':
            return super().execute_skill_tool(tool_name, params)
        if isinstance(params, str):
            import json
            try:
                params = json.loads(params)
            except ValueError:
                params = {}
        params = params or {}
        results = self.env['dolan.help.center'].search_help(params.get('query', ''), params.get('limit') or 3)
        if not results:
            return {'status': 'success', 'result': [], 'message': 'No hay una guía para eso en la Ayuda.'}
        return {'status': 'success', 'result': results}
