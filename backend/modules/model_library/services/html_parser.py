"""
HTML 文件解析器

功能：
1. 解析上传的 HTML 文件
2. 提取 UNITS 定义（部件坐标/尺寸）
3. 提取 Canvas 绘制逻辑中的部件 ID
4. 生成 parts_config_json 初稿

支持格式：
- OXE_2D.html 风格：包含 UNITS = {...} 定义
- 通用 HTML：提取 id="xxx" 属性
"""

import re
import json
from typing import Dict, List, Any, Optional


def extract_units_from_html(html_content: str) -> Dict[str, Any]:
    """从 HTML 中提取 UNITS 定义
    
    支持 OXE_2D.html 风格：
      const UNITS = {
        PORT1: { id: 'PORT1', x: -285, y: -80, w: 120, d: 180, h: 60 },
        ...
      }
    """
    result = {
        'units': {},
        'functions': [],
        'events': [],
        'api_calls': [],
    }
    
    # 提取 UNITS 对象定义
    # 匹配: const UNITS = { ... } 或 var UNITS = { ... }
    units_pattern = r'(?:const|var|let)\s+UNITS\s*=\s*\{([^}]+(?:\{[^}]*\}[^}]*)*)\}'
    units_match = re.search(units_pattern, html_content, re.DOTALL)
    
    if units_match:
        units_str = units_match.group(1)
        # 解析每个 unit 定义
        # 格式: UNIT_NAME: { id: 'xxx', x: 123, y: 456, ... }
        unit_pattern = r"(\w+)\s*:\s*\{([^}]+)\}"
        for match in re.finditer(unit_pattern, units_str):
            unit_name = match.group(1)
            unit_props_str = match.group(2)
            
            # 解析属性
            props = {}
            for prop_match in re.finditer(r"(\w+)\s*:\s*([^,}]+)", unit_props_str):
                key = prop_match.group(1)
                value_str = prop_match.group(2).strip()
                # 尝试解析值
                if value_str.startswith("'") or value_str.startswith('"'):
                    props[key] = value_str[1:-1] if len(value_str) > 1 else ''
                elif value_str.startswith('['):
                    # 数组
                    try:
                        props[key] = json.loads(value_str.replace("'", '"'))
                    except:
                        props[key] = value_str
                else:
                    # 数字
                    try:
                        props[key] = float(value_str) if '.' in value_str else int(value_str)
                    except:
                        props[key] = value_str
            
            result['units'][unit_name] = props
    
    return result


def extract_draw_functions(html_content: str) -> List[str]:
    """提取 Canvas 绘制函数名"""
    # 匹配 function drawXxx() 或 const drawXxx = function
    pattern = r'function\s+(draw\w+)\s*\('
    return re.findall(pattern, html_content)


def extract_event_listeners(html_content: str) -> List[str]:
    """提取事件监听器"""
    # 匹配 .addEventListener('xxx', ...) 或 .onclick = ...
    pattern = r"\.addEventListener\s*\(\s*['\"](\w+)['\"]"
    return re.findall(pattern, html_content)


def extract_api_calls(html_content: str) -> List[str]:
    """提取 API 调用路径"""
    # 匹配 fetch('/api/xxx') 或 apiUrl('/xxx')
    patterns = [
        r"fetch\s*\(\s*['\"]([^'\"]+)['\"]",
        r"apiUrl\s*\(\s*['\"]([^'\"]+)['\"]",
    ]
    calls = []
    for pattern in patterns:
        calls.extend(re.findall(pattern, html_content))
    return calls


def generate_parts_config(units: Dict[str, Any], model_id: str = 'UNKNOWN') -> List[Dict]:
    """从 UNITS 生成 parts_config 格式
    
    输出格式：
    [
      {
        "part_id": "PORT1",
        "part_name": "Load Port 1",
        "part_type": "loadport",
        "view_3d": {"type": "box", "size": [...], "position": [...], "color": "..."},
        "view_2d_iso": {"x": ..., "y": ..., "width": ..., "height": ...}
      }
    ]
    """
    parts = []
    
    # 部件 ID 到类型的映射
    type_mapping = {
        'PORT': 'loadport',
        'LP': 'loadport',
        'EFEM': 'efem',
        'ARM': 'robot',
        'ROBOT': 'robot',
        'CHAMBER': 'chamber',
        'PM': 'chamber',
        'VTM': 'vtm',
        'TRANSFER': 'vtm',
        'ALIGNER': 'aligner',
        'PA': 'aligner',
        'WAFER': 'wafer',
        'CASSETTE': 'cassette',
        'CST': 'cassette',
        'POD': 'pod',
        'LATCH': 'latch',
        'LOCK': 'latch',
        'VACUUM': 'vacuum_lock',
        'LOADLOCK': 'vacuum_lock',
    }
    
    for unit_name, props in units.items():
        # 推断部件类型
        part_type = 'structure'
        for key, type_name in type_mapping.items():
            if key in unit_name.upper():
                part_type = type_name
                break
        
        # 构建 part 配置
        part = {
            'part_id': unit_name,
            'part_name': props.get('id', unit_name),
            'part_type': part_type,
        }
        
        # 3D 视图配置（基于坐标估算）
        if 'x' in props and 'y' in props:
            w = props.get('w', 100)
            d = props.get('d', 100)
            h = props.get('h', props.get('height', 60))
            
            part['view_3d'] = {
                'type': 'box',
                'size': [w, d, h],
                'position': [props['x'], props['y'], h / 2],
                'color': '#374151',
            }
            
            # 2D 等角视图配置
            part['view_2d_iso'] = {
                'x': props['x'],
                'y': props['y'],
                'width': w,
                'height': d,
                'isometric_depth': h,
            }
        
        parts.append(part)
    
    return parts


def parse_html_file(html_content: str, model_id: str = 'UNKNOWN') -> Dict[str, Any]:
    """解析 HTML 文件并生成配置初稿
    
    返回：
    {
        'units': {...},           # 提取的 UNITS 定义
        'functions': [...],       # 绘制函数列表
        'events': [...],          # 事件监听器列表
        'api_calls': [...],       # API 调用路径列表
        'parts_config': [...],    # 生成的 parts_config
        'source_info': {          # 来源信息
            'type': 'html',
            'units_count': 0,
            'has_canvas': False,
        }
    }
    """
    # 提取各部分
    units_result = extract_units_from_html(html_content)
    functions = extract_draw_functions(html_content)
    events = extract_event_listeners(html_content)
    api_calls = extract_api_calls(html_content)
    
    # 生成 parts_config
    parts_config = generate_parts_config(units_result['units'], model_id)
    
    # 检查是否有 Canvas
    has_canvas = '<canvas' in html_content.lower()
    
    return {
        'units': units_result['units'],
        'functions': functions,
        'events': events,
        'api_calls': api_calls,
        'parts_config': parts_config,
        'source_info': {
            'type': 'html',
            'units_count': len(units_result['units']),
            'functions_count': len(functions),
            'has_canvas': has_canvas,
        }
    }


# 测试代码
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python html_parser.py <html_file>")
        sys.exit(1)
    
    html_file = sys.argv[1]
    with open(html_file, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    result = parse_html_file(html_content)
    
    print("=" * 60)
    print(f"HTML 解析结果: {html_file}")
    print("=" * 60)
    print(f"\n提取的 UNITS 数量: {result['source_info']['units_count']}")
    print(f"绘制函数数量: {result['source_info']['functions_count']}")
    print(f"包含 Canvas: {result['source_info']['has_canvas']}")
    
    print("\n" + "-" * 60)
    print("部件列表:")
    print("-" * 60)
    for part in result['parts_config'][:10]:  # 只显示前 10 个
        print(f"  {part['part_id']}: {part['part_type']} ({part['part_name']})")
    
    if len(result['parts_config']) > 10:
        print(f"  ... 还有 {len(result['parts_config']) - 10} 个部件")
    
    print("\n" + "-" * 60)
    print("API 调用:")
    print("-" * 60)
    for api in result['api_calls'][:10]:
        print(f"  {api}")
    
    print("\n" + "-" * 60)
    print("生成的 parts_config_json:")
    print("-" * 60)
    print(json.dumps(result['parts_config'][:3], indent=2, ensure_ascii=False))