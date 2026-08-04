#!/usr/bin/env python3
"""
FabTwin 模型交付物生成器
根据现有 PODOPENER / OXE 的数据配置，生成 SVG + GLB + JSON 三份文件
供模型开发人员参考和替换

输出目录: ../models/reference/
"""
import json
import struct
import os
import math
from pathlib import Path

# ==================== 数据定义 ====================

PODOPENER_PARTS = [
    {"id": "base_plate",     "name": "底座底板",   "type": "box",      "size": [520, 680, 38],  "pos": [0, -10, 19],   "color": "#4b535c"},
    {"id": "front_stage",   "name": "前载台",     "type": "box",      "size": [300, 240, 48],  "pos": [0, -36, 124],  "color": "#cbd5e1"},
    {"id": "left_rail",     "name": "左侧导轨",   "type": "box",      "size": [18, 306, 760],  "pos": [-181, -22, 484],"color": "#5f6972"},
    {"id": "right_rail",    "name": "右侧导轨",   "type": "box",      "size": [18, 306, 760],  "pos": [181, -22, 484], "color": "#5f6972"},
    {"id": "rear_panel",    "name": "后面板",     "type": "box",      "size": [330, 32, 690],  "pos": [0, 112, 444],   "color": "#b7ad99"},
    {"id": "wafer_port",    "name": "Wafer入口",  "type": "cylinder", "size": [230, 230, 14],  "pos": [0, -142, 130], "color": "#94a3b8"},
    {"id": "chamber",       "name": "工艺腔体",   "type": "cylinder", "size": [200, 200, 50],  "pos": [0, 0, 900],    "color": "#17202a"},
    {"id": "control_box",   "name": "操作控制盒", "type": "box",      "size": [198, 92, 112],  "pos": [0, -472, 76],  "color": "#111827"},
    {"id": "pod",           "name": "POD/晶舟",   "type": "cylinder", "size": [150, 150, 300], "pos": [0, -300, 200], "color": "#f59e0b"},
]

OXE_PARTS = [
    {"id": "loadport_1",      "name": "Load Port 1",   "type": "box",      "size": [120, 180, 60],   "pos": [-285, -80, 180],  "color": "#2a3a5a"},
    {"id": "loadport_2",      "name": "Load Port 2",   "type": "box",      "size": [120, 180, 60],   "pos": [-285, 80, 180],   "color": "#2a3a5a"},
    {"id": "efem",            "name": "EFEM 传输腔",   "type": "box",      "size": [200, 300, 200],  "pos": [-150, 0, 200],    "color": "#374151"},
    {"id": "efem_robot",      "name": "EFEM 机械臂",   "type": "cylinder", "size": [30, 30, 120],    "pos": [-150, 0, 220],    "color": "#60a5fa"},
    {"id": "aligner",         "name": "Aligner 对中器","type": "cylinder", "size": [50, 50, 40],     "pos": [-150, -100, 180], "color": "#94a3b8"},
    {"id": "vacuum_lock_1",   "name": "真空锁 1",      "type": "box",      "size": [100, 120, 80],   "pos": [-20, -80, 200],   "color": "#475569"},
    {"id": "vacuum_lock_2",   "name": "真空锁 2",      "type": "box",      "size": [100, 120, 80],   "pos": [-20, 80, 200],    "color": "#475569"},
    {"id": "transfer_chamber","name": "传输腔 (VTM)",  "type": "cylinder", "size": [220, 220, 180],  "pos": [120, 0, 220],     "color": "#1e293b"},
    {"id": "vtm_robot",       "name": "VTM 机械臂",    "type": "cylinder", "size": [25, 25, 100],    "pos": [120, 0, 230],     "color": "#f59e0b"},
    {"id": "chamber_1",       "name": "工艺腔 PM1",    "type": "cylinder", "size": [120, 120, 150],  "pos": [250, -150, 230],  "color": "#1e3a5f"},
    {"id": "chamber_2",       "name": "工艺腔 PM2",    "type": "cylinder", "size": [120, 120, 150],  "pos": [250, 150, 230],   "color": "#1e3a5f"},
    {"id": "wafer",           "name": "晶圆",          "type": "cylinder", "size": [50, 50, 3],      "pos": [-150, 0, 280],    "color": "#60a5fa"},
]


# ==================== SVG 生成器 ====================

def hex_to_rgb(hex_color):
    h = hex_color.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def darken(color, factor=0.7):
    """降低亮度，用于等角视图的暗面"""
    r, g, b = hex_to_rgb(color)
    return f"#{int(r*factor):02x}{int(g*factor):02x}{int(b*factor):02x}"

def lighten(color, factor=1.3):
    """提高亮度，用于等角视图的亮面"""
    r, g, b = hex_to_rgb(color)
    return f"#{min(255,int(r*factor)):02x}{min(255,int(g*factor)):02x}{min(255,int(b*factor)):02x}"


def generate_podopener_svg():
    """PODOPENER 正视图 SVG（从前方 -y 方向看）"""
    # SVG 参数
    w, h = 800, 1000
    scale = 0.35
    offset_x, offset_z = 400, 50

    def to_svg(x, z):
        return (offset_x + x * scale, offset_z + (1000 - z) * scale)

    # 按 y 从大到小排序（后先画）
    sorted_parts = sorted(PODOPENER_PARTS, key=lambda p: p["pos"][1], reverse=True)

    elements = []
    for part in sorted_parts:
        px, py, pz = part["pos"]
        sx, sy, sz = part["size"]
        color = part["color"]

        if part["type"] == "box":
            # 正视图中 box 是矩形：宽=sx, 高=sz
            x1, y1 = to_svg(px - sx/2, pz + sz/2)
            x2, y2 = to_svg(px + sx/2, pz - sz/2)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            elements.append(
                f'<rect x="{min(x1,x2):.1f}" y="{min(y1,y2):.1f}" width="{rw:.1f}" height="{rh:.1f}" '
                f'fill="{color}" stroke="#1a1a2e" stroke-width="1" rx="2">'
                f'<title>{part["name"]}</title></rect>'
            )
        elif part["type"] == "cylinder":
            # 正视图中 cylinder（轴线垂直）是矩形：宽=直径, 高=高度
            dia = sx
            x1, y1 = to_svg(px - dia/2, pz + sz/2)
            x2, y2 = to_svg(px + dia/2, pz - sz/2)
            rw, rh = abs(x2 - x1), abs(y2 - y1)
            elements.append(
                f'<rect x="{min(x1,x2):.1f}" y="{min(y1,y2):.1f}" width="{rw:.1f}" height="{rh:.1f}" '
                f'fill="{color}" stroke="#1a1a2e" stroke-width="1" rx="3">'
                f'<title>{part["name"]} (cylinder)</title></rect>'
            )

    # 添加标注
    labels = [
        (0, 950, "工艺腔体", "#fff"),
        (0, 250, "POD/晶舟", "#fff"),
        (0, 140, "Wafer入口", "#fff"),
        (0, 50, "操作控制盒", "#fff"),
    ]
    label_elements = []
    for lx, lz, text, color in labels:
        sx, sy = to_svg(lx, lz)
        label_elements.append(
            f'<text x="{sx:.1f}" y="{sy:.1f}" text-anchor="middle" fill="{color}" '
            f'font-size="12" font-family="Arial" pointer-events="none">{text}</text>'
        )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg)"/>
  <g id="machine-body">
    {chr(10).join(elements)}
  </g>
  <g id="labels">
    {chr(10).join(label_elements)}
  </g>
  <text x="{w-10}" y="{h-10}" text-anchor="end" fill="#64748b" font-size="10" font-family="Arial">
    FabTwin - PODOPENER-2200 正视图参考
  </text>
</svg>'''
    return svg


def generate_oxe_svg():
    """OXE 等角视图 SVG（2.5D 风格）"""
    w, h = 800, 500

    # OXE 部件的 view_2d_iso 坐标（来自 seed_data）
    iso_parts = [
        {"id": "loadport_1",       "x": 100,  "y": 50,  "w": 60,  "h": 40,  "d": 20, "color": "#2a3a5a", "name": "Load Port 1"},
        {"id": "loadport_2",       "x": 100,  "y": 150, "w": 60,  "h": 40,  "d": 20, "color": "#2a3a5a", "name": "Load Port 2"},
        {"id": "efem",             "x": 200,  "y": 100, "w": 100, "h": 120, "d": 30, "color": "#374151", "name": "EFEM"},
        {"id": "transfer_chamber", "x": 350,  "y": 100, "w": 100, "h": 120, "d": 30, "color": "#1e293b", "name": "VTM"},
        {"id": "chamber_1",        "x": 480,  "y": 40,  "w": 60,  "h": 60,  "d": 25, "color": "#1e3a5f", "name": "PM1"},
        {"id": "chamber_2",        "x": 480,  "y": 170, "w": 60,  "h": 60,  "d": 25, "color": "#1e3a5f", "name": "PM2"},
    ]

    def draw_isobox(p):
        x, y, bw, bh, bd = p["x"], p["y"], p["w"], p["h"], p["d"]
        c = p["color"]
        c_top = lighten(c, 1.2)
        c_left = c
        c_right = darken(c, 0.75)

        # 等角投影的三个面
        # 顶面（菱形）
        top_pts = f"{x+bw*0.5},{y} {x+bw},{y+bd*0.5} {x+bw*0.5},{y+bd} {x},{y+bd*0.5}"
        # 左侧面
        left_pts = f"{x},{y+bd*0.5} {x+bw*0.5},{y+bd} {x+bw*0.5},{y+bd+bh} {x},{y+bd*0.5+bh}"
        # 右侧面
        right_pts = f"{x+bw},{y+bd*0.5} {x+bw*0.5},{y+bd} {x+bw*0.5},{y+bd+bh} {x+bw},{y+bd*0.5+bh}"

        return [
            f'<polygon points="{top_pts}" fill="{c_top}" stroke="#0f172a" stroke-width="0.5"><title>{p["name"]} (顶面)</title></polygon>',
            f'<polygon points="{left_pts}" fill="{c_left}" stroke="#0f172a" stroke-width="0.5"><title>{p["name"]} (左面)</title></polygon>',
            f'<polygon points="{right_pts}" fill="{c_right}" stroke="#0f172a" stroke-width="0.5"><title>{p["name"]} (右面)</title></polygon>',
        ]

    elements = []
    for p in iso_parts:
        elements.extend(draw_isobox(p))

    # 连接线（示意数据流）
    connections = [
        (160, 70, 200, 120, "#60a5fa"),   # LP1 -> EFEM
        (160, 170, 200, 140, "#60a5fa"),  # LP2 -> EFEM
        (300, 130, 350, 130, "#f59e0b"),  # EFEM -> VTM
        (450, 100, 480, 70, "#22c55e"),   # VTM -> PM1
        (450, 160, 480, 200, "#22c55e"),  # VTM -> PM2
    ]
    conn_elements = []
    for x1, y1, x2, y2, color in connections:
        conn_elements.append(
            f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{color}" stroke-width="2" '
            f'stroke-dasharray="4,3" opacity="0.6"/>'
        )

    # 标签
    labels = [
        (130, 35, "LP1"), (130, 135, "LP2"),
        (250, 85, "EFEM"), (400, 85, "VTM"),
        (510, 55, "PM1"), (510, 185, "PM2"),
    ]
    label_elements = []
    for lx, ly, text in labels:
        label_elements.append(
            f'<text x="{lx}" y="{ly}" text-anchor="middle" fill="#e2e8f0" '
            f'font-size="11" font-family="Arial" font-weight="bold">{text}</text>'
        )

    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <defs>
    <linearGradient id="bg2" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="#0f172a"/>
      <stop offset="100%" stop-color="#1e293b"/>
    </linearGradient>
  </defs>
  <rect width="100%" height="100%" fill="url(#bg2)"/>
  <g id="connections">
    {chr(10).join(conn_elements)}
  </g>
  <g id="machine-body">
    {chr(10).join(elements)}
  </g>
  <g id="labels">
    {chr(10).join(label_elements)}
  </g>
  <text x="{w-10}" y="{h-10}" text-anchor="end" fill="#64748b" font-size="10" font-family="Arial">
    FabTwin - OXE DRM UNITY 等角视图参考
  </text>
</svg>'''
    return svg


# ==================== GLB 生成器 ====================

def build_glb(parts, filename):
    """
    手动构造 GLB 2.0 文件
    每个部件生成一个有色立方体（cylinder 也用立方体近似）
    """
    vertices = []
    indices = []
    accessors = []
    buffer_views = []
    nodes = []
    meshes = []

    vert_offset = 0
    idx_offset = 0

    for part in parts:
        px, py, pz = part["pos"]
        sx, sy, sz = part["size"]
        color = hex_to_rgb(part["color"])
        color_norm = [c / 255.0 for c in color]

        # 立方体 8 个顶点 (x, y, z, r, g, b)
        hw, hh, hd = sx / 2, sy / 2, sz / 2
        local_verts = [
            (-hw, -hh, -hd), (hw, -hh, -hd), (hw, hh, -hd), (-hw, hh, -hd),
            (-hw, -hh, hd),  (hw, -hh, hd),  (hw, hh, hd),  (-hw, hh, hd),
        ]
        # 移动到世界坐标
        for lv in local_verts:
            vertices.extend([lv[0] + px, lv[1] + py, lv[2] + pz])
            vertices.extend(color_norm)

        # 12 个三角形索引
        local_idx = [
            0, 1, 2, 0, 2, 3,   # 前
            4, 6, 5, 4, 7, 6,   # 后
            0, 5, 1, 0, 4, 5,   # 底
            2, 7, 3, 2, 6, 7,   # 顶
            0, 3, 7, 0, 7, 4,   # 左
            1, 6, 2, 1, 5, 6,   # 右
        ]
        for li in local_idx:
            indices.append(vert_offset + li)

        # Accessor
        # 顶点位置 (VEC3, FLOAT)
        v_start = vert_offset * 6 * 4  # 每个顶点 6 floats * 4 bytes
        v_count = 8
        accessors.append({
            "bufferView": len(buffer_views),
            "componentType": 5126,  # FLOAT
            "count": v_count,
            "type": "VEC3",
            "max": [px + hw, py + hh, pz + hd],
            "min": [px - hw, py - hh, pz - hd],
        })
        buffer_views.append({
            "buffer": 0,
            "byteOffset": v_start,
            "byteLength": v_count * 12,  # 3 floats * 4 bytes
        })

        # 顶点颜色 (VEC3, FLOAT)
        accessors.append({
            "bufferView": len(buffer_views),
            "componentType": 5126,
            "count": v_count,
            "type": "VEC3",
        })
        buffer_views.append({
            "buffer": 0,
            "byteOffset": v_start + 12,  # 偏移 12 bytes (位置之后)
            "byteLength": v_count * 12,
            "byteStride": 24,  # 每个顶点 6 floats * 4 bytes
        })

        # 索引 (SCALAR, UNSIGNED_SHORT)
        i_start = idx_offset * 2
        i_count = 36
        idx_accessor_idx = len(accessors)
        accessors.append({
            "bufferView": len(buffer_views),
            "componentType": 5123,  # UNSIGNED_SHORT
            "count": i_count,
            "type": "SCALAR",
        })
        buffer_views.append({
            "buffer": 0,
            "byteOffset": i_start,
            "byteLength": i_count * 2,
        })

        # Mesh
        mesh_idx = len(meshes)
        meshes.append({
            "primitives": [{
                "attributes": {
                    "POSITION": len(accessors) - 3,
                    "COLOR_0": len(accessors) - 2,
                },
                "indices": idx_accessor_idx,
                "mode": 4,  # TRIANGLES
            }]
        })

        # Node
        nodes.append({
            "mesh": mesh_idx,
            "name": part["id"],
        })

        vert_offset += 8
        idx_offset += 36

    # 构建 BIN chunk
    # 顶点数据: interleaved (px, py, pz, r, g, b) * 8 vertices per part
    # 索引数据: unsigned short * 36 indices per part
    vertex_data = struct.pack(f'<{len(vertices)}f', *vertices)
    index_data = struct.pack(f'<{len(indices)}H', *indices)

    # 补齐到 4 字节对齐
    padding = (4 - (len(index_data) % 4)) % 4
    index_data += b'\x00' * padding

    bin_data = vertex_data + index_data

    # 更新 buffer_views 的 byteOffset（索引部分需要加上 vertex_data 的长度）
    for bv in buffer_views:
        if bv["byteOffset"] >= len(vertex_data):
            # 这是索引 bufferView
            pass  # 已经在上面计算好了

    # 构建 JSON
    gltf = {
        "asset": {"version": "2.0", "generator": "FabTwin Model Generator"},
        "scene": 0,
        "scenes": [{"nodes": list(range(len(nodes)))}],
        "nodes": nodes,
        "meshes": meshes,
        "accessors": accessors,
        "bufferViews": buffer_views,
        "buffers": [{"byteLength": len(bin_data)}],
    }

    json_bytes = json.dumps(gltf, separators=(',', ':')).encode('utf-8')
    # JSON chunk 补齐到 4 字节
    json_padding = (4 - (len(json_bytes) % 4)) % 4
    json_bytes += b' ' * json_padding

    # 构建 GLB
    header = struct.pack('<III', 0x46546C67, 2, 12 + 8 + len(json_bytes) + 8 + len(bin_data))
    json_chunk = struct.pack('<II', len(json_bytes), 0x4E4F534A) + json_bytes
    bin_chunk = struct.pack('<II', len(bin_data), 0x004E4942) + bin_data

    glb = header + json_chunk + bin_chunk

    with open(filename, 'wb') as f:
        f.write(glb)

    print(f"[OK] GLB: {filename} ({len(glb)} bytes, {len(parts)} parts)")


# ==================== JSON 生成器 ====================

def generate_podopener_json():
    return {
        "machine_type": "PODOPENER-2200",
        "version": "1.0.0",
        "description": "VPO 2200 PODOPENER 穿入/脱出流程统一动画配置（2D/3D 共用）",
        "vendor": "TEL",
        "process_type": "PODOPENER",
        "views": {
            "view_3d": {"type": "vpo", "model_source": "PODOPENER-2200.glb",
                        "default_camera": {"position": [700, -300, 400], "target": [0, 0, 400]}},
            "view_2d": {"type": "vpo", "svg_source": "PODOPENER-2200.svg",
                        "view_label": "正视图"},
        },
        "parts": [
            {"part_id": "base_plate", "part_name": "底座底板", "part_type": "structure",
             "view_3d": {"type": "box", "size": [520, 680, 38], "position": [0, -10, 19], "color": "#4b535c"}},
            {"part_id": "front_stage", "part_name": "前载台", "part_type": "stage",
             "view_3d": {"type": "box", "size": [300, 240, 48], "position": [0, -36, 124], "color": "#cbd5e1"}},
            {"part_id": "left_rail", "part_name": "左侧导轨", "part_type": "rail",
             "view_3d": {"type": "box", "size": [18, 306, 760], "position": [-181, -22, 484], "color": "#5f6972"}},
            {"part_id": "right_rail", "part_name": "右侧导轨", "part_type": "rail",
             "view_3d": {"type": "box", "size": [18, 306, 760], "position": [181, -22, 484], "color": "#5f6972"}},
            {"part_id": "rear_panel", "part_name": "后面板", "part_type": "panel",
             "view_3d": {"type": "box", "size": [330, 32, 690], "position": [0, 112, 444], "color": "#b7ad99"}},
            {"part_id": "wafer_port", "part_name": "Wafer入口", "part_type": "port",
             "view_3d": {"type": "cylinder", "size": [230, 230, 14], "position": [0, -142, 130], "color": "#94a3b8"}},
            {"part_id": "chamber", "part_name": "工艺腔体", "part_type": "chamber",
             "view_3d": {"type": "cylinder", "size": [200, 200, 50], "position": [0, 0, 900], "color": "#17202a"}},
            {"part_id": "control_box", "part_name": "操作控制盒", "part_type": "control",
             "view_3d": {"type": "box", "size": [198, 92, 112], "position": [0, -472, 76], "color": "#111827"}},
            {"part_id": "pod", "part_name": "POD/晶舟", "part_type": "pod",
             "view_3d": {"type": "cylinder", "size": [150, 150, 300], "position": [0, -300, 200], "color": "#f59e0b"},
             "animated": True},
        ],
        "hotspots": [
            {"hotspot_id": "machine_body", "name": "机身主体", "part_ids": ["left_rail", "right_rail", "rear_panel"]},
            {"hotspot_id": "wafer_port_front", "name": "Wafer入口", "part_ids": ["wafer_port"]},
            {"hotspot_id": "operator_control", "name": "控制盒", "part_ids": ["control_box"]},
        ],
        "states": [
            {"state_id": "idle", "state_name": "待机", "color": "#9ca3af",
             "part_overrides": [{"part_id": "chamber", "emissive_intensity": 0}]},
            {"state_id": "running", "state_name": "运行", "color": "#22c55e",
             "part_overrides": [{"part_id": "chamber", "emissive": "#22c55e", "emissive_intensity": 0.5}]},
            {"state_id": "hold", "state_name": "暂停", "color": "#f59e0b",
             "part_overrides": [{"part_id": "wafer_port", "emissive": "#f59e0b", "emissive_intensity": 0.3}]},
            {"state_id": "alarm", "state_name": "告警", "color": "#ef4444",
             "part_overrides": [{"part_id": "chamber", "emissive": "#ef4444", "emissive_intensity": 0.8, "pulse": True}]},
        ],
        "notes_for_modeler": {
            "svg": "PODOPENER-2200.svg 是正视图参考，模型开发人员应替换为精细绘制的 SVG",
            "glb": "PODOPENER-2200.glb 是简化立方体组合，模型开发人员应替换为精细 3D 模型",
            "naming": "GLB 中的 mesh/node 名称必须与 parts 中的 part_id 一一对应",
            "animation": "动画配置见 podopener.json（单独文件）",
            "coordinates": "所有坐标单位:mm，原点位于机台底座中心",
        }
    }


def generate_oxe_json():
    return {
        "machine_type": "TEL-DRM-UNIT",
        "version": "1.0.0",
        "description": "TEL DRM UNITY 刻蚀机（OXE）2.5D 等角视图配置",
        "vendor": "TEL",
        "process_type": "ETCH",
        "views": {
            "view_3d": {"type": "threejs", "model_source": "OXE-DRM.glb",
                        "default_camera": {"position": [7, 5, 8], "target": [0, 1.8, 0]}},
            "view_2d": {"type": "isometric", "svg_source": "OXE-DRM.svg",
                        "projection": {"scale": 30, "angle_x": 30, "angle_y": 45},
                        "view_label": "等角 2.5D 视图"},
        },
        "parts": [
            {"part_id": "loadport_1", "part_name": "Load Port 1", "part_type": "loadport",
             "view_3d": {"type": "box", "size": [120, 180, 60], "position": [-285, -80, 180], "color": "#2a3a5a"},
             "view_2d_iso": {"x": 100, "y": 50, "width": 60, "height": 40, "isometric_depth": 20}},
            {"part_id": "loadport_2", "part_name": "Load Port 2", "part_type": "loadport",
             "view_3d": {"type": "box", "size": [120, 180, 60], "position": [-285, 80, 180], "color": "#2a3a5a"},
             "view_2d_iso": {"x": 100, "y": 150, "width": 60, "height": 40, "isometric_depth": 20}},
            {"part_id": "efem", "part_name": "EFEM 传输腔", "part_type": "efem",
             "view_3d": {"type": "box", "size": [200, 300, 200], "position": [-150, 0, 200], "color": "#374151"},
             "view_2d_iso": {"x": 200, "y": 100, "width": 100, "height": 120, "isometric_depth": 30}},
            {"part_id": "efem_robot", "part_name": "EFEM 机械臂", "part_type": "robot",
             "view_3d": {"type": "cylinder", "size": [30, 30, 120], "position": [-150, 0, 220], "color": "#60a5fa"},
             "animated": True},
            {"part_id": "aligner", "part_name": "Aligner 对中器", "part_type": "aligner",
             "view_3d": {"type": "cylinder", "size": [50, 50, 40], "position": [-150, -100, 180], "color": "#94a3b8"}},
            {"part_id": "vacuum_lock_1", "part_name": "真空锁 1", "part_type": "vacuum_lock",
             "view_3d": {"type": "box", "size": [100, 120, 80], "position": [-20, -80, 200], "color": "#475569"}},
            {"part_id": "vacuum_lock_2", "part_name": "真空锁 2", "part_type": "vacuum_lock",
             "view_3d": {"type": "box", "size": [100, 120, 80], "position": [-20, 80, 200], "color": "#475569"}},
            {"part_id": "transfer_chamber", "part_name": "传输腔 (VTM)", "part_type": "vtm",
             "view_3d": {"type": "cylinder", "size": [220, 220, 180], "position": [120, 0, 220], "color": "#1e293b"},
             "view_2d_iso": {"x": 350, "y": 100, "width": 100, "height": 120, "isometric_depth": 30}},
            {"part_id": "vtm_robot", "part_name": "VTM 机械臂", "part_type": "robot",
             "view_3d": {"type": "cylinder", "size": [25, 25, 100], "position": [120, 0, 230], "color": "#f59e0b"},
             "animated": True},
            {"part_id": "chamber_1", "part_name": "工艺腔 PM1", "part_type": "chamber",
             "view_3d": {"type": "cylinder", "size": [120, 120, 150], "position": [250, -150, 230], "color": "#1e3a5f"},
             "view_2d_iso": {"x": 480, "y": 40, "width": 60, "height": 60, "isometric_depth": 25}},
            {"part_id": "chamber_2", "part_name": "工艺腔 PM2", "part_type": "chamber",
             "view_3d": {"type": "cylinder", "size": [120, 120, 150], "position": [250, 150, 230], "color": "#1e3a5f"},
             "view_2d_iso": {"x": 480, "y": 170, "width": 60, "height": 60, "isometric_depth": 25}},
            {"part_id": "wafer", "part_name": "晶圆", "part_type": "wafer",
             "view_3d": {"type": "cylinder", "size": [50, 50, 3], "position": [-150, 0, 280], "color": "#60a5fa"},
             "animated": True},
        ],
        "hotspots": [
            {"hotspot_id": "lp1", "name": "Load Port 1", "part_ids": ["loadport_1"]},
            {"hotspot_id": "lp2", "name": "Load Port 2", "part_ids": ["loadport_2"]},
            {"hotspot_id": "efem", "name": "EFEM", "part_ids": ["efem", "efem_robot"]},
            {"hotspot_id": "vtm", "name": "传输腔", "part_ids": ["transfer_chamber", "vtm_robot"]},
            {"hotspot_id": "pm1", "name": "工艺腔 1", "part_ids": ["chamber_1"]},
            {"hotspot_id": "pm2", "name": "工艺腔 2", "part_ids": ["chamber_2"]},
        ],
        "states": [
            {"state_id": "idle", "state_name": "待机", "color": "#9ca3af"},
            {"state_id": "running", "state_name": "运行", "color": "#22c55e",
             "part_overrides": [
                 {"part_id": "chamber_1", "emissive": "#22c55e", "emissive_intensity": 0.5},
                 {"part_id": "chamber_2", "emissive": "#22c55e", "emissive_intensity": 0.5},
             ]},
            {"state_id": "hold", "state_name": "暂停", "color": "#f59e0b"},
            {"state_id": "alarm", "state_name": "告警", "color": "#ef4444",
             "part_overrides": [
                 {"part_id": "transfer_chamber", "emissive": "#ef4444", "emissive_intensity": 0.8, "pulse": True},
             ]},
        ],
        "notes_for_modeler": {
            "svg": "OXE-DRM.svg 是等角视图参考，模型开发人员应替换为精细绘制的 SVG",
            "glb": "OXE-DRM.glb 是简化立方体组合，模型开发人员应替换为精细 3D 模型",
            "naming": "GLB 中的 mesh/node 名称必须与 parts 中的 part_id 一一对应",
            "coordinates": "所有坐标单位:mm，EFEM 在左侧，VTM 在中间，PM 在右侧",
            "animation": "机械臂(efem_robot/vtm_robot)和晶圆(wafer)标记为 animated，需要骨骼或变形动画支持",
        }
    }


# ==================== 主程序 ====================

def main():
    out_dir = Path(__file__).parent.parent / "models" / "reference"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"输出目录: {out_dir}")

    # PODOPENER
    print("\n--- PODOPENER-2200 ---")
    svg_pod = generate_podopener_svg()
    (out_dir / "PODOPENER-2200.svg").write_text(svg_pod, encoding="utf-8")
    print(f"[OK] SVG: PODOPENER-2200.svg")

    build_glb(PODOPENER_PARTS, str(out_dir / "PODOPENER-2200.glb"))

    json_pod = generate_podopener_json()
    (out_dir / "PODOPENER-2200.json").write_text(
        json.dumps(json_pod, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] JSON: PODOPENER-2200.json")

    # OXE
    print("\n--- OXE DRM UNITY ---")
    svg_oxe = generate_oxe_svg()
    (out_dir / "OXE-DRM.svg").write_text(svg_oxe, encoding="utf-8")
    print(f"[OK] SVG: OXE-DRM.svg")

    build_glb(OXE_PARTS, str(out_dir / "OXE-DRM.glb"))

    json_oxe = generate_oxe_json()
    (out_dir / "OXE-DRM.json").write_text(
        json.dumps(json_oxe, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"[OK] JSON: OXE-DRM.json")

    print(f"\n全部完成！输出目录: {out_dir}")
    print("文件清单:")
    for f in sorted(out_dir.iterdir()):
        print(f"  - {f.name} ({f.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
