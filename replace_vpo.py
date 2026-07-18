import os
import re

def replace_in_file(filepath, replacements):
    """在文件中执行多个替换"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original = content
        for old, new in replacements:
            content = content.replace(old, new)
        
        if content != original:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            return True
        return False
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return False

replacements = [
    ('VPO 2D', 'PODOPENER 2D'),
    ('VPO 3D', 'PODOPENER 3D'),
    ('VPO机台', 'PODOPENER机台'),
    ('VPO FRONT VIEW', 'PODOPENER FRONT VIEW'),
    ('VPO 2D 视图', 'PODOPENER 2D 视图'),
    ('VPO 3D模型', 'PODOPENER 3D模型'),
    ('VPO（真空预对准）', 'PODOPENER（POD开盖机）'),
    ('VPO-01', 'PODOPENER-1'),
    ('"vpo"', '"podopener"'),
    ('"vpo3d"', '"podopener3d"'),
    ("value=\"vpo\"", "value=\"podopener\""),
    ("value=\"vpo3d\"", "value=\"podopener3d\""),
    ("'vpo'", "'podopener'"),
    ("'vpo3d'", "'podopener3d'"),
    ('type === \'vpo\'', 'type === \'podopener\''),
    ('type === "vpo"', 'type === "podopener"'),
    ("== 'vpo'", "== 'podopener'"),
    ("== \"vpo\"", "== \"podopener\""),
    ('=== \'vpo\'', '=== \'podopener\''),
    ('=== "vpo"', '=== "podopener"'),
    ('.vpo', '.podopener'),
    ('vpo-', 'podopener-'),
    ('VPO_', 'PODOPENER_'),
    ('VPO-', 'PODOPENER-'),
    ('Vpo', 'Podopener'),
]

files_to_process = [
    r'frontend\src\components\MachineVpoView.vue',
    r'frontend\src\views\MachineDetail.vue',
    r'frontend\src\views\ModelEditor.vue',
    r'frontend\public\models\vpo-2200-3d.json',
]

print("开始替换VPO → PODOPENER...\n")
for filepath in files_to_process:
    full_path = os.path.join(r'n:\AI\fab-twin-pro-ver1', filepath)
    if not os.path.exists(full_path):
        print(f"跳过（不存在）: {filepath}")
        continue
    
    changed = replace_in_file(full_path, replacements)
    if changed:
        print(f"✓ 已修改: {filepath}")
    else:
        print(f"- 未修改: {filepath}")

print("\n替换完成！")
