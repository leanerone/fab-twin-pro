import sys
sys.path.insert(0, r'C:\Users\A\AppData\Roaming\TRAE SOLO CN\ModularData\ai-agent\work-mode-projects\6a558d0e1709fecd225c0cc2\fab-twin-pro\backend')
from services.ai_tools import TOOL_DEFINITIONS, TOOL_HANDLERS

print(f'TOOL_DEFINITIONS: {len(TOOL_DEFINITIONS)} 个')
for t in TOOL_DEFINITIONS:
    print(f'  - {t["function"]["name"]}')

print(f'\nTOOL_HANDLERS: {len(TOOL_HANDLERS)} 个')
for k in TOOL_HANDLERS.keys():
    print(f'  - {k}')
