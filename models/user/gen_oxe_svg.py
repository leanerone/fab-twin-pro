# -*- coding: utf-8 -*-
r"""
OXE DRM 顶视图 SVG 资产生成器 v2.2（紧凑真实 cluster + 蛙腿叉形臂）

解决反馈四点：①构造松散 → 工艺腔紧贴多边形传送腔；②送片通道窄 → slit valve 开口≈晶圆直径；
③晶圆太小 → 半径 32；④机械臂样式不对 → 真实蛙腿(frog-leg)双臂 + 叉形末端执行器(fork 两齿)。

- 配色/质感对齐 models/user/amat_metsput.svg（金属渐变/法兰螺栓/彩虹晶圆）
- 保留 motion 管线全部动画部件 id（与 oxe-drm-topview.motion.json 对应，勿改）
- 左右材料详情面板（LOT/状态/完成 + 25 行 Wafer Map 三态）、左右告警消息面板、每槽晶圆条
运行：python gen_oxe_svg.py（默认拒绝覆盖；--force 仅从 token 同步 defs，定稿几何保持不变）
"""
import json
import math
import re
import sys
from pathlib import Path

_MODELS_DIR = Path(__file__).resolve().parents[1]
if str(_MODELS_DIR) not in sys.path:
    sys.path.insert(0, str(_MODELS_DIR))
from svg_kit.primitives import legacy_defs
from svg_kit.validate import extract_ids, extract_parts, extract_pids, validate_content

# ========== 几何常量（motion JSON / deriver 依赖，改动需同步） ==========
# v2.5 镜像对称、机台居中：hub 在机台区几何中心，CH_A/B 关于过 hub 竖轴对称，
# LL1/LL2 同样镜像对齐各自 SMIF；CH_C 正右、PA 正左（水平对称）。
# 所有 slit 内端统一落在六边形外接圆 R108；晶圆 r30 通行。
HUB = (444, 400)
TRANSFER_R = 108                 # 正六边形 TM 外接圆（机械臂收回活动区）
SLIT_INNER_R = TRANSFER_R - 2    # 所有 slit 通道内端半径（统一）
# 各单元由极坐标推导（角度关于竖轴 ± 镜像；0°=右，顺时针正）
CH_R = 70
_CH_POLAR = {"A": (-120, 190), "B": (-60, 190), "C": (0, 201)}
CH = {k: (round(HUB[0] + r * math.cos(math.radians(a)), 1),
          round(HUB[1] + r * math.sin(math.radians(a)), 1))
      for k, (a, r) in _CH_POLAR.items()}
CH_ANG = {k: v[0] for k, v in _CH_POLAR.items()}
PA_ANG = 180                     # 正左（SVG 顺时针对 PA 用 180，与 -180 等价）
PA_DIST = 192
PA_C = (round(HUB[0] + PA_DIST * math.cos(math.radians(PA_ANG)), 1),
        round(HUB[1] + PA_DIST * math.sin(math.radians(PA_ANG)), 1))
PA_RX, PA_RY = 78, 64
# load locks：定稿布局 LL1(PORT1) 左下 120°、LL2(PORT2) 右下 60°（严格镜像），同尺寸 74x68
# 必须与 frontend/src/motionDerivers/oxe.js 的 ARM_ANGLES 一致（PORT1=120 / PORT2=60），否则机械臂送错侧
PORT_ANG = {"1": 120, "2": 60}
_PORT_DIST = {"1": 205, "2": 205}
PORT_C = {p: (round(HUB[0] + _PORT_DIST[p] * math.cos(math.radians(a)), 1),
              round(HUB[1] + _PORT_DIST[p] * math.sin(math.radians(a)), 1))
          for p, a in PORT_ANG.items()}
PORT_W, PORT_H = 74, 68
# 各单元 slit 通道宽（3 个工艺腔统一 72；PA 64、LL 79）
SLIT_W_CH = 72
SLIT_W_PA = 64
SLIT_W_LL = 79
SLIT_W = SLIT_W_CH
_REACH = {
    "CH_A": _CH_POLAR["A"][1], "CH_B": _CH_POLAR["B"][1], "CH_C": _CH_POLAR["C"][1],
    "PA": PA_DIST, "P1": _PORT_DIST["1"], "P2": _PORT_DIST["2"],
}
REACH_R = max(_REACH.values())
BLADE_REACH = REACH_R - 70
WAFER_R = 30
WAFER_R_MOVE = WAFER_R
WAFER_R_CH = WAFER_R
WAFER_R_PA = WAFER_R
# SMIF/晶舟：沿各 LL 径向外移对齐（距离与角度均由 LL 推导，不写死屏幕坐标）
PORT1_OUT_D = 92
PORT_Y = round((PORT_C["1"][1] + PORT_C["2"][1]) / 2)
P1X, P2X = round(PORT_C["1"][0]), round(PORT_C["2"][0])
SLOT_Y0, SLOT_PITCH = PORT_Y + 26, 0
SMIF_Y0, SMIF_H = 0, 96       # 屏幕坐标不再用（SMIF 改为按 LL 径向定位）
CST_X0, CST_W = 0, 46
CST_BAR_Y0, CST_BAR_PITCH = 0, 2.8
BAR_W, BAR_H = 26, 1.7
PLATE = (150, 150, 580, 575)
PAN_L, PAN_R, PAN_Y, PAN_W, PAN_H = 12, 888, 60, 180, 470
ALARM_Y, ALARM_H = 540, 180
ROW_Y0, ROW_PITCH = 212, 12.6
VIEW_W, VIEW_H = 1080, 840


def fmt(v):
    s = f"{v:.2f}".rstrip('0').rstrip('.')
    return s if s else '0'


DEFS = legacy_defs("oxe")


def wafer_g(pid, cx, cy, r=32):
    return f'''  <g id="{pid}" data-motion-base-visibility="hidden">
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#waferPattern)" stroke="#2f3a4d" stroke-width="1.2"/>
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#waferShade)" pointer-events="none"/>
    <circle cx="{cx}" cy="{cy}" r="{fmt(r - 0.6)}" fill="none" stroke="url(#edgeMetal)" stroke-width="1.2" pointer-events="none"/>
    <path d="M{fmt(cx - r * 0.72)},{fmt(cy - r * 0.6)} A{fmt(r * 0.94)},{fmt(r * 0.94)} 0 0 1 {fmt(cx + r * 0.05)},{fmt(cy - r * 0.94)}" fill="none" stroke="#ffffff" stroke-opacity="0.8" stroke-width="1.5" stroke-linecap="round" pointer-events="none"/>
    <path d="M{fmt(cx - 3.2)},{fmt(cy - r + 4.2)} L{fmt(cx + 3.2)},{fmt(cy - r + 4.2)} L{cx},{fmt(cy - r + 8.2)} Z" fill="#0d1117" pointer-events="none"/>
  </g>'''


def _slit_to(cx, cy, half_dep, bore_w, indent="    "):
    """从六边形外接圆（R108）到目标单元内边缘的 slit 通道（任意方位）。
    cx,cy=单元中心；half_dep=单元朝 hub 方向的半径（圆=r，椭圆=rx，矩形=h/2 投影）；
    bore_w=暗槽宽。返回一段 SVG（金属门框 + 暗槽），通道内端统一在 R108。"""
    hx, hy = HUB
    dx, dy = cx - hx, cy - hy
    dist = math.hypot(dx, dy)
    ux, uy = dx / dist, dy / dist
    ang = math.degrees(math.atan2(dy, dx))
    r0 = SLIT_INNER_R                 # 内端（六边形壁）
    r1 = dist - half_dep + 8          # 外端（伸入单元法兰）
    x0, y0 = hx + ux * r0, hy + uy * r0
    w = r1 - r0
    frame = (f'{indent}<rect x="0" y="{-bore_w / 2 - 5}" width="{fmt(w)}" height="{bore_w + 10}" rx="5" '
             f'fill="url(#valveMetal)" stroke="#3a4250" stroke-width="2.4" '
             f'transform="translate({fmt(x0)} {fmt(y0)}) rotate({fmt(ang)})"/>')
    bore = (f'{indent}<rect x="2" y="{-bore_w / 2}" width="{fmt(w - 4)}" height="{bore_w}" rx="3" '
            f'fill="#0d1420" opacity="0.92" transform="translate({fmt(x0)} {fmt(y0)}) rotate({fmt(ang)})"/>')
    return frame, bore, ang, ux, uy, dist


def slit_group(cx, cy, bore_w=SLIT_W_CH, half_dep=CH_R):
    frame, bore, *_ = _slit_to(cx, cy, half_dep, bore_w)
    return frame + '\n' + bore


def chamber_group(ch, cx, cy):
    rr = CH_R
    bore_w = SLIT_W_CH
    frame, bore, ang, ux, uy, dist = _slit_to(cx, cy, rr, bore_w)
    bolts = []
    for k in range(10):
        a = math.radians(18 + 36 * k)
        bolts.append(f'<circle cx="{fmt(cx + (rr - 8) * math.cos(a))}" cy="{fmt(cy + (rr - 8) * math.sin(a))}" r="1.7" fill="#3a4250"/>')
    bolts_s = '\n    '.join(bolts)
    hl1 = (f'M{fmt(cx - rr * 0.72)},{fmt(cy - rr * 0.26)} A{fmt(rr * 0.78)},{fmt(rr * 0.78)} 0 0 1 {fmt(cx + rr * 0.62)},{fmt(cy - rr * 0.5)}')
    hl2 = (f'M{fmt(cx - rr * 0.62)},{fmt(cy + rr * 0.52)} A{fmt(rr * 0.82)},{fmt(rr * 0.82)} 0 0 0 {fmt(cx + rr * 0.62)},{fmt(cy + rr * 0.52)}')
    mouth_x, mouth_y = cx - ux * (rr - 2), cy - uy * (rr - 2)
    mouth = (f'    <rect x="-11" y="{-bore_w / 2}" width="15" height="{bore_w}" rx="3" fill="#0d1420" '
             f'opacity="0.95" transform="translate({fmt(mouth_x)} {fmt(mouth_y)}) rotate({fmt(ang)})"/>')
    out = [f'  <!-- ===== PM 腔 CH_{ch}（slit 内端统一 R{TRANSFER_R}、宽 {bore_w}） ===== -->',
           f'  <g id="CH_{ch}_SLIT">',
           '    ' + frame,
           '    ' + bore,
           '  </g>',
           f'  <g id="CH_{ch}">',
           f'    <ellipse cx="{cx}" cy="{fmt(cy + 18)}" rx="{rr + 8}" ry="14" fill="url(#groundShadow)"/>',
           f'    <circle cx="{cx}" cy="{cy}" r="{rr}" fill="url(#chSteel)" stroke="#3a4250" stroke-width="2.6"/>',
           f'    <circle cx="{cx}" cy="{cy}" r="{rr}" fill="url(#chShade)" pointer-events="none"/>',
           mouth,
           f'    <path d="{hl1}" fill="none" stroke="#ffffff" stroke-opacity="0.8" stroke-width="2.6" stroke-linecap="round" pointer-events="none"/>',
           f'    <path d="{hl2}" fill="none" stroke="#141a24" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round" pointer-events="none"/>',
           f'    <circle cx="{cx}" cy="{cy}" r="{fmt(rr + 5)}" fill="none" stroke="url(#chFlange)" stroke-width="5.5"/>',
           f'    <circle cx="{cx}" cy="{cy}" r="{fmt(rr + 2)}" fill="none" stroke="#454545" stroke-width="1"/>',
           bolts_s,
           f'    <circle id="CH_{ch}_C" cx="{cx}" cy="{cy}" r="1.2" fill="#000" fill-opacity="0.01"/>',
           '  </g>']
    for suffix, fill, stroke in (('run', '#16a34a', '#0b5c2a'), ('alarm', '#dc2626', '#7f1d1d'), ('unload', '#ca8a04', '#713f12')):
        out.append(f'  <g id="CH_{ch}_{suffix}" data-motion-base-visibility="hidden">')
        out.append(f'    <circle cx="{cx}" cy="{cy}" r="{rr}" fill="{fill}" stroke="{stroke}" stroke-width="2"/>')
        out.append('  </g>')
    return '\n'.join(out)


def panel_side(side):
    x0 = PAN_L if side == '1' else PAN_R
    L = []
    L.append(f'  <!-- ===== PORT{side} 材料详情面板 ===== -->')
    L.append(f'  <g id="PANEL_P{side}">')
    L.append(f'    <rect x="{x0}" y="{PAN_Y}" width="{PAN_W}" height="{PAN_H}" rx="6" fill="url(#framePlate)" stroke="#8a94a4" stroke-width="2"/>')
    hx0 = x0 + 6
    L.append(f'    <path d="M{hx0},{PAN_Y} h{PAN_W - 12} a6,6 0 0 1 6,6 v22 h-{PAN_W} v-22 a6,6 0 0 1 6,-6 z" fill="url(#panelMetal)"/>')
    L.append(f'    <text x="{x0 + PAN_W / 2}" y="{PAN_Y + 20}" font-size="11" font-weight="800" fill="#cbd5e1" text-anchor="middle" letter-spacing="1">PORT{side} · WAFER MAP</text>')
    for i, (label, pid) in enumerate((('LOT', f'LOTLBL_P{side}'), ('状态', f'LOTSTAT_P{side}'), ('完成', f'DONE_P{side}'))):
        ry = 104 + i * 26
        L.append(f'    <text x="{x0 + 10}" y="{ry + 14}" font-size="9" font-weight="700" fill="#6b7280">{label}</text>')
        L.append(f'    <rect id="{pid}" x="{x0 + 38}" y="{ry}" width="134" height="20" rx="10" fill="#eef3fa" stroke="#8a94a4" stroke-width="0.8"/>')
    L.append(f'    <line x1="{x0 + 10}" y1="190" x2="{x0 + PAN_W - 10}" y2="190" stroke="#c3ccd9" stroke-width="1"/>')
    L.append(f'    <text x="{x0 + 30}" y="204" font-size="8" font-weight="700" fill="#94a3b8" text-anchor="end">SLOT</text>')
    L.append(f'    <text x="{x0 + 40}" y="204" font-size="8" font-weight="700" fill="#94a3b8">WAFER STATE</text>')
    L.append(f'    <g id="WM_P{side}_LAYER">')
    for n in range(1, 26):
        yc = ROW_Y0 + (n - 1) * ROW_PITCH
        L.append(f'    <text x="{x0 + 30}" y="{fmt(yc + 3)}" font-size="8.5" fill="#334155" text-anchor="end" font-family="Consolas, monospace">{n:02d}</text>')
        for suffix, fill, stroke in (('W', '#cbd5e1', '#94a3b8'), ('R', '#22c55e', '#15803d'), ('D', '#fde047', '#ca8a04')):
            L.append(f'    <rect id="WM_P{side}_S{n}_{suffix}" x="{x0 + 40}" y="{fmt(yc - 3.2)}" width="130" height="6.4" rx="3.2" '
                     f'fill="{fill}" stroke="{stroke}" stroke-width="0.5" data-motion-base-visibility="hidden"/>')
    L.append('    </g>')
    L.append('  </g>')
    ax = x0
    L.append(f'  <!-- ===== PORT{side} 告警消息面板 ===== -->')
    L.append(f'  <g id="ALARMPANEL_P{side}">')
    L.append(f'    <rect x="{ax}" y="{ALARM_Y}" width="{PAN_W}" height="{ALARM_H}" rx="6" fill="#fff5f5" stroke="#dc2626" stroke-width="1.4"/>')
    L.append(f'    <path d="M{ax + 6},{ALARM_Y} h{PAN_W - 12} a6,6 0 0 1 6,6 v18 h-{PAN_W} v-18 a6,6 0 0 1 6,-6 z" fill="#dc2626"/>')
    L.append(f'    <text x="{ax + 12}" y="{ALARM_Y + 18}" font-size="10" font-weight="800" fill="#ffffff">⚠ PORT{side} 告警消息</text>')
    L.append(f'    <rect id="ALARM_P{side}_CNT" x="{ax + 142}" y="{ALARM_Y + 6}" width="30" height="15" rx="7.5" fill="url(#badgeMetal)" stroke="#93a3ba" stroke-width="0.7"/>')
    for i in range(3):
        ly = 572 + i * 46
        L.append(f'    <rect id="ALARM_P{side}_L{i + 1}" x="{ax + 8}" y="{ly}" width="164" height="42" rx="4" fill="#fee2e2" stroke="#fca5a5" stroke-width="0.6"/>')
    L.append('  </g>')
    return '\n'.join(L)


def _port_unit(side):
    """LL 径向单位向量与距离（任意坐标）"""
    cx, cy = PORT_C[side]
    hx, hy = HUB
    d = math.hypot(cx - hx, cy - hy)
    return ((cx - hx) / d, (cy - hy) / d, d)


def _port_out(side, dist):
    """LL 径向外移 dist 处坐标（SMIF/晶舟/POD 升降位）"""
    cx, cy = PORT_C[side]
    ux, uy, _ = _port_unit(side)
    return (round(cx + ux * dist, 1), round(cy + uy * dist, 1))


def port_box(side):
    """load lock：矩形缓冲盒（显式坐标）+ 朝六边形的 slit（宽 SLIT_W_LL）。"""
    cx, cy = PORT_C[side]
    frame, bore, ang, ux, uy, dist = _slit_to(cx, cy, PORT_H / 2 + 4, SLIT_W_LL)
    # 盒朝 hub 一侧的暗口
    mouth_x, mouth_y = cx - ux * (PORT_H / 2 - 2), cy - uy * (PORT_H / 2 - 2)
    L = [f'  <!-- ===== load lock LL{side}（slit 宽 {SLIT_W_LL}） ===== -->',
         f'  <g id="PORT{side}_SLIT">',
         '    ' + frame, '    ' + bore,
         '  </g>',
         f'  <g id="PORT{side}">',
         f'    <ellipse cx="{cx}" cy="{fmt(cy + PORT_H/2 + 10)}" rx="{PORT_W/2 + 6}" ry="11" fill="url(#groundShadow)"/>',
         f'    <rect x="{fmt(cx - PORT_W / 2)}" y="{fmt(cy - PORT_H / 2)}" width="{PORT_W}" height="{PORT_H}" rx="9" class="shape"/>',
         f'    <rect x="{fmt(cx - PORT_W / 2 + 8)}" y="{fmt(cy - PORT_H / 2 + 8)}" width="{PORT_W - 16}" height="{PORT_H - 16}" rx="5" fill="url(#deckPlate)" stroke="#8a94a4" stroke-width="1"/>',
         # 朝 hub 暗口
         f'    <rect x="-11" y="{-SLIT_W_LL / 2}" width="15" height="{SLIT_W_LL}" rx="3" fill="#0d1420" opacity="0.95" transform="translate({fmt(mouth_x)} {fmt(mouth_y)}) rotate({fmt(ang)})"/>',
         # 徽章（背向 hub）
         f'    <g transform="translate({fmt(cx + ux * (PORT_W/2 - 2))} {fmt(cy + uy * (PORT_H/2 - 2))})">',
         f'      <rect x="-20" y="-9" width="40" height="16" rx="8" fill="url(#badgeMetal)" stroke="#93a3ba" stroke-width="0.6"/>',
         f'      <text x="0" y="3" font-size="9" font-weight="800" fill="#e2e8f0" text-anchor="middle">LL{side}</text>',
         f'    </g>',
         f'    <circle id="PORT{side}_C" cx="{cx}" cy="{cy}" r="1.2" fill="#000" fill-opacity="0.01"/>']
    for n in range(1, 26):
        L.append(f'    <circle id="P{side}_SLOT_{n}" cx="{cx}" cy="{cy}" r="1.2" fill="#000" fill-opacity="0.01"/>')
    L.append('  </g>')
    return '\n'.join(L)


def cassette(side):
    # 晶舟在 LL 外侧升降位（snap 到 PORT_C 时进入交接）
    ox, oy = _port_out(side, PORT1_OUT_D)
    cw, chh = 46, 80
    L = [f'  <g id="CST_P{side}" data-motion-base-visibility="hidden">',
         f'    <rect x="{fmt(ox - cw / 2)}" y="{fmt(oy - chh / 2)}" width="{cw}" height="{chh}" rx="3" fill="url(#cassetteMetal)" stroke="#4b5563" stroke-width="1" opacity="0.95"/>',
         f'    <rect x="{fmt(ox - cw / 2 + 6)}" y="{fmt(oy - chh / 2 + 6)}" width="{cw - 12}" height="{chh - 12}" rx="2" fill="#0f172a" opacity="0.4"/>']
    top, pitch = oy - chh / 2 + 10, (chh - 20) / 24
    for n in range(1, 26):
        y = top + (n - 1) * pitch
        L.append(f'    <rect id="WAFER_P{side}_S{n}" x="{fmt(ox - cw / 2 + 9)}" y="{fmt(y - 0.8)}" width="{cw - 18}" height="1.6" rx="0.8" '
                 f'fill="url(#slotMetal)" stroke="#10141a" stroke-width="0.15"/>')
    L.append('  </g>')
    return '\n'.join(L)


def smif_box(side):
    ox, oy = _port_out(side, PORT1_OUT_D)
    bw, bh = 62, 92
    return '\n'.join([
        f'  <g id="SMIF{side}">',
        f'    <ellipse cx="{ox}" cy="{fmt(oy + bh / 2 + 3)}" rx="37" ry="7" fill="url(#groundShadow)"/>',
        f'    <rect x="{fmt(ox - bw / 2)}" y="{fmt(oy - bh / 2)}" width="{bw}" height="{bh}" rx="3" fill="url(#smifShell)" stroke="#3a4250" stroke-width="1.8"/>',
        f'    <rect x="{fmt(ox - bw / 2 + 4)}" y="{fmt(oy - bh / 2 + 4)}" width="{bw - 8}" height="{bh - 8}" rx="2" fill="url(#smifInner)" stroke="#3a4250" stroke-width="1.2"/>',
        f'    <rect x="{fmt(ox - bw / 2 + 4)}" y="{fmt(oy - bh / 2 + 4)}" width="{bw - 8}" height="22" fill="url(#panelMetal)" opacity="0.92"/>',
        f'    <text x="{ox}" y="{fmt(oy - bh / 2 + 19)}" font-size="9" font-weight="700" fill="#cbd5e1" text-anchor="middle" letter-spacing="1">SMIF{side}</text>',
        f'    <rect x="{ox - 21}" y="{fmt(oy - 6)}" width="42" height="30" fill="url(#boardMetal)" opacity="0.95" stroke="#3a4250" stroke-width="0.8"/>',
        f'    <rect x="{fmt(ox - bw / 2 + 7)}" y="{fmt(oy + bh / 2 - 22)}" width="{bw - 14}" height="12" fill="url(#glassDark)" opacity="0.85"/>',
        f'    <circle cx="{fmt(ox - bw / 2 + 11)}" cy="{fmt(oy - bh / 2 + 11)}" r="2.4" fill="#4b1113" stroke="#111827" stroke-width="0.5"/>',
        f'    <circle cx="{fmt(ox - bw / 2 + 19)}" cy="{fmt(oy - bh / 2 + 11)}" r="2.4" fill="#123524" stroke="#111827" stroke-width="0.5"/>',
        f'    <circle id="SMIF{side}_C" cx="{ox}" cy="{oy}" r="1.2" fill="#000" fill-opacity="0.01"/>',
        '  </g>'])


def pod(side):
    ox, oy = _port_out(side, PORT1_OUT_D)
    w, h = 68, 100
    x, y0 = ox - w / 2, oy - h / 2
    return '\n'.join([
        f'  <g id="POD_P{side}" data-motion-base-visibility="hidden">',
        f'    <rect x="{fmt(x)}" y="{fmt(y0)}" width="{w}" height="{h}" rx="10" fill="url(#cassetteMetal)" stroke="#4b5563" stroke-width="1.3"/>',
        f'    <rect x="{ox - 12}" y="{fmt(y0 + 27)}" width="24" height="11" rx="2" fill="rgba(96,165,250,0.45)"/>',
        f'    <rect x="{ox - 23}" y="{fmt(y0 + 46)}" width="46" height="36" rx="4" fill="none" stroke="rgba(148,163,184,0.4)" stroke-width="1"/>',
        '  </g>',
        f'  <g id="POD_P{side}_LK" data-motion-base-visibility="hidden">',
        f'    <rect x="{fmt(x + 6)}" y="{fmt(y0 + h - 11)}" width="6" height="6" fill="#dc2626"/>',
        f'    <rect x="{fmt(x + w - 12)}" y="{fmt(y0 + h - 11)}" width="6" height="6" fill="#dc2626"/>',
        '  </g>'])


def _wafer_circle(cx, cy, r, pid, base_hidden=True):
    """彩虹晶圆（可嵌为任意组子件）；base_hidden=True 时默认隐藏，由 visibility 规则显示"""
    attr = ' data-motion-base-visibility="hidden"' if base_hidden else ''
    return (f'<g id="{pid}"{attr}>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#waferPattern)" stroke="#2f3a4d" stroke-width="1.2"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#waferShade)" pointer-events="none"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{fmt(r - 0.6)}" fill="none" stroke="url(#edgeMetal)" stroke-width="1.2" pointer-events="none"/>'
            f'<path d="M{fmt(cx - r * 0.72)},{fmt(cy - r * 0.6)} A{fmt(r * 0.94)},{fmt(r * 0.94)} 0 0 1 {fmt(cx + r * 0.05)},{fmt(cy - r * 0.94)}" fill="none" stroke="#ffffff" stroke-opacity="0.8" stroke-width="1.5" stroke-linecap="round" pointer-events="none"/>'
            f'<path d="M{fmt(cx - 3.2)},{fmt(cy - r + 4.2)} L{fmt(cx + 3.2)},{fmt(cy - r + 4.2)} L{cx},{fmt(cy - r + 8.2)} Z" fill="#0d1117" pointer-events="none"/>'
            '</g>')


def arm_group():
    """嵌套式蛙腿真空机械臂（晶圆始终坐叉端随动，不再空中飞）：
       ARM_ROBOT：绕 hub 旋转（含锚圆撑 fill-box + hub 转盘）
         ARM_EXTEND：外臂叉端，默认收回（叉托中心 r=70），伸出 offset +BLADE_REACH → r=150
           叉形 blade + WAFER_MOVE（晶圆子件，纯随动，自身不加 transform）"""
    hx, hy = HUB
    reach_in = 70                    # 收回时叉托中心距 hub
    reach_out = REACH_R              # 伸出时叉托中心 = 150（= 各单元中心环）
    tipx = hx + reach_in             # 叉托中心（收回态几何位置）
    fork_len = 46                    # 叉形 blade 长度
    tooth_half = 10                  # 叉齿半宽（开口 20，晶圆 r30 由叉面托住）
    fork_root = tipx - 6
    fork_base = tipx - fork_len + 14
    fork_tip = tipx + fork_len - 6
    # 内/外蛙腿连杆画在收回姿态：肩(hub) → 双肘(r42) → 腕部(tipx-30)
    elbow = 42
    wrist_x = tipx - 26
    S = ['  <!-- ===== 嵌套蛙腿真空机械臂（ARM_ROBOT 旋转 > ARM_EXTEND 伸缩 > 叉+晶圆随动） ===== -->',
         '  <g id="ARM_ROBOT">',
         f'    <circle id="ARM_ANCHOR" cx="{hx}" cy="{hy}" r="210" fill="none" visibility="hidden" data-motion-base-visibility="hidden" pointer-events="none"/>',
         # hub 转盘
         f'    <circle cx="{hx}" cy="{hy}" r="26" fill="url(#armSteel)" stroke="#3a4250" stroke-width="2.6"/>',
         f'    <circle cx="{hx}" cy="{hy}" r="26" fill="url(#chShade)" pointer-events="none"/>',
         f'    <circle cx="{hx}" cy="{hy}" r="19" fill="none" stroke="url(#chFlange)" stroke-width="3"/>',
         f'    <circle cx="{hx}" cy="{hy}" r="5" fill="#39414e"/>']
    for k in range(6):
        ba = math.radians(60 * k)
        S.append(f'    <circle cx="{fmt(hx + 21 * math.cos(ba))}" cy="{fmt(hy + 21 * math.sin(ba))}" r="2.2" fill="#39414e"/>')
    # 内臂（不随外臂伸缩，固定在旋转层；视觉上折叠）
    S.append(f'    <line x1="{hx + 16}" y1="{hy - 13}" x2="{hx + elbow}" y2="{hy - elbow}" stroke="url(#armBlade)" stroke-width="8" stroke-linecap="round"/>')
    S.append(f'    <line x1="{hx + 16}" y1="{hy + 13}" x2="{hx + elbow}" y2="{hy + elbow}" stroke="url(#armBlade)" stroke-width="8" stroke-linecap="round"/>')
    S.append(f'    <circle cx="{hx + elbow}" cy="{hy - elbow}" r="7.5" fill="url(#armSteel)" stroke="#3a4250" stroke-width="2"/>')
    S.append(f'    <circle cx="{hx + elbow}" cy="{hy + elbow}" r="7.5" fill="url(#armSteel)" stroke="#3a4250" stroke-width="2"/>')
    # ===== 外臂伸缩层（默认收回，offset 驱动伸出）=====
    S.append('    <g id="ARM_EXTEND">')
    S.append(f'      <line x1="{hx + elbow}" y1="{hy - elbow}" x2="{wrist_x}" y2="{hy - 12}" stroke="url(#armBlade)" stroke-width="7" stroke-linecap="round"/>')
    S.append(f'      <line x1="{hx + elbow}" y1="{hy + elbow}" x2="{wrist_x}" y2="{hy + 12}" stroke="url(#armBlade)" stroke-width="7" stroke-linecap="round"/>')
    S.append(f'      <rect x="{wrist_x - 5}" y="{hy - 14}" width="13" height="28" rx="4" fill="url(#armSteel)" stroke="#3a4250" stroke-width="2"/>')
    # 叉形末端（U 两齿）
    fork_d = (
        f"M{fork_root},{hy - 5} L{fork_base},{hy - 5} L{fork_base},{hy - tooth_half - 3} "
        f"L{fork_tip},{hy - tooth_half - 3} L{fork_tip},{hy - tooth_half + 1} "
        f"L{fork_base + 12},{hy - tooth_half + 1} L{fork_base + 12},{hy + tooth_half - 1} "
        f"L{fork_tip},{hy + tooth_half - 1} L{fork_tip},{hy + tooth_half + 3} "
        f"L{fork_base},{hy + tooth_half + 3} L{fork_base},{hy + 5} L{fork_root},{hy + 5} Z"
    )
    S.append(f'      <path d="{fork_d}" fill="url(#armBlade)" stroke="#3a4250" stroke-width="2" stroke-linejoin="round"/>')
    S.append(f'      <line x1="{fork_root}" y1="{hy}" x2="{fork_base + 8}" y2="{hy}" stroke="#ffffff" stroke-opacity="0.5" stroke-width="1.4" stroke-linecap="round"/>')
    # 晶圆坐叉托中心（子件随 ARM_EXTEND 伸缩、随 ARM_ROBOT 旋转；默认隐藏）
    S.append('      ' + _wafer_circle(tipx, hy, WAFER_R, 'WAFER_MOVE'))
    # 叉托中心锚点（snap/定位参考，保留 id 兼容）
    S.append(f'      <circle id="ARM_TIP" cx="{tipx}" cy="{hy}" r="1.2" fill="#000" fill-opacity="0.01"/>')
    S.append('    </g>')
    S.append(f'    <circle id="ARM_HUB" cx="{hx}" cy="{hy}" r="1.2" fill="#000" fill-opacity="0.01"/>')
    S.append('  </g>')
    return '\n'.join(S)


def _legacy_generate():
    """旧版全量几何生成参考；定稿资产请使用 main() 的安全同步路径。"""
    hx, hy = HUB
    bolts = []
    # 六边形 6 顶点 + 6 边中点法兰螺栓
    for k in range(6):
        av = math.radians(30 + 60 * k)
        am = math.radians(60 * k)
        bolts.append(f'<circle cx="{fmt(hx + (TRANSFER_R + 7) * math.cos(av))}" cy="{fmt(hy + (TRANSFER_R + 7) * math.sin(av))}" r="3" fill="#39414e"/>')
        bolts.append(f'<circle cx="{fmt(hx + (TRANSFER_R - 4) * math.cos(am))}" cy="{fmt(hy + (TRANSFER_R - 4) * math.sin(am))}" r="2.2" fill="#39414e"/>')
    bolts_s = '\n      '.join(bolts)

    S = []
    S.append('<?xml version="1.0" encoding="UTF-8"?>')
    S.append('<!--')
    S.append('  OXE DRM (TEL ICP 刻蚀机) 顶视图 2D 资产（motion2d）v2.2 紧凑真实 cluster + 蛙腿叉形臂')
    S.append('  由 gen_oxe_svg.py 生成（几何常量集中脚本头部，改动后重新生成）。')
    S.append('  改进：工艺腔紧贴多边形传送腔 / slit valve 宽开口≈晶圆直径 / 晶圆 r32 / 蛙腿双臂+叉形末端。')
    S.append('  面板：左右材料详情（LOT/状态/完成 + 25 槽 Wafer Map 三态）+ 左右告警消息（计数+3行）。')
    S.append('  部件 id 与 oxe-drm-topview.motion.json 对应，勿改：CH_A|B|C(+run/alarm/unload)、PORT1/2、')
    S.append('  SMIF1/2、PA、ARM_ZONE、ARM_ROBOT/ARM_TIP/ARM_HUB/ARM_ANCHOR、WAFER_MOVE/PA/CH_x、')
    S.append('  POD_P1|2(+LK)、CST_P1|2、DOOR_P1|2、MAP_P1|2、*_C、P{1,2}_SLOT_1..25、title_block；')
    S.append('  新增：WAFER_P1|2_S1..25、PANEL_P1|2、LOTLBL/LOTSTAT/DONE、WM_P1|2_LAYER/Sn_W/R/D、')
    S.append('  ALARMPANEL_P1|2、ALARM_P1|2_CNT/L1..L3。viewBox 1080x840，hub=(540,385)。')
    S.append('-->')
    S.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {VIEW_W} {VIEW_H}" font-family="Arial, \'Microsoft YaHei\', sans-serif">')
    S.append(DEFS)
    S.append(f'  <rect width="{VIEW_W}" height="{VIEW_H}" fill="#f6f8fb"/>')

    S.append('  <g id="title_block">')
    S.append('    <rect x="12" y="18" width="8" height="34" fill="#1148d7"/>')
    S.append('    <text x="30" y="34" font-size="17" font-weight="800" fill="#1f2933">OXE DRM UNITY · ICP 刻蚀机</text>')
    S.append('    <text x="30" y="52" font-size="10" fill="#64748b">真实 cluster 顶视图：多边形 Transfer Module + PM×3 宽 slit valve + 蛙腿真空机械臂（叉形末端）· Loadport×2 + SMIF + PA · 左右材料详情 / 告警消息面板</text>')
    S.append(f'    <text x="{VIEW_W - 12}" y="34" font-size="10" fill="#94a3b8" text-anchor="end">TOP VIEW</text>')
    S.append('  </g>')

    S.append(f'  <rect id="baseplate" x="{PLATE[0]}" y="{PLATE[1]}" width="{PLATE[2]}" height="{PLATE[3]}" rx="8" fill="url(#framePlate)" stroke="#8a94a4" stroke-width="2"/>')

    S.append('  <g id="gas_box">')
    S.append(f'    <line x1="{hx}" y1="118" x2="{hx}" y2="172" stroke="#94a3b8" stroke-width="1.2" stroke-dasharray="4,4"/>')
    S.append(f'    <rect x="{hx - 60}" y="76" width="120" height="42" rx="6" fill="url(#valveMetal)" stroke="#3a4250" stroke-width="2.2"/>')
    S.append(f'    <rect x="{hx - 54}" y="82" width="108" height="8" rx="4" fill="none" stroke="url(#chFlange)" stroke-width="2"/>')
    S.append(f'    <circle cx="{hx - 50}" cy="110" r="2" fill="#39414e"/><circle cx="{hx - 17}" cy="110" r="2" fill="#39414e"/>')
    S.append(f'    <circle cx="{hx + 17}" cy="110" r="2" fill="#39414e"/><circle cx="{hx + 50}" cy="110" r="2" fill="#39414e"/>')
    S.append(f'    <rect x="{hx + 60}" y="88" width="12" height="14" fill="url(#valveMetal)" stroke="#3a4250" stroke-width="1.4"/>')
    S.append(f'    <text x="{hx}" y="103" font-size="12" font-weight="700" fill="#1f2933" text-anchor="middle">Gas Box</text>')
    S.append('  </g>')

    for ch in ('A', 'B', 'C'):
        S.append(chamber_group(ch, *CH[ch]))

    S.append('  <g id="chamber_labels">')
    for ch, name in (('A', 'CHAMBER_A'), ('B', 'CHAMBER_B'), ('C', 'CHAMBER_C')):
        ccx, ccy = CH[ch]
        a = math.radians(CH_ANG[ch])
        lx = ccx + (CH_R + 22) * math.cos(a)
        ly = ccy + (CH_R + 22) * math.sin(a) - 4
        S.append(f'    <rect x="{fmt(lx - 42)}" y="{fmt(ly - 9)}" width="84" height="17" rx="8.5" fill="url(#badgeMetal)" stroke="#93a3ba" stroke-width="0.6" opacity="0.96"/>')
        S.append(f'    <text x="{fmt(lx)}" y="{fmt(ly + 3)}" font-size="9.5" font-weight="800" fill="#e2e8f0" text-anchor="middle">{name}</text>')
    S.append('  </g>')

    # ===== 中央正六边形 Transfer Module =====
    hex_pts = []
    for k in range(6):
        a = math.radians(30 + 60 * k)
        hex_pts.append(f'{fmt(hx + TRANSFER_R * math.cos(a))},{fmt(hy + TRANSFER_R * math.sin(a))}')
    S.append('  <g id="ARM_ZONE">')
    S.append(f'    <ellipse cx="{hx}" cy="{fmt(hy + 14)}" rx="{TRANSFER_R + 16}" ry="20" fill="url(#groundShadow)"/>')
    S.append(f'    <polygon points="{" ".join(hex_pts)}" fill="url(#framePlate)" stroke="#2f3a4a" stroke-width="3"/>')
    S.append(f'    <polygon points="{" ".join(hex_pts)}" fill="url(#chShade)" pointer-events="none"/>')
    # 六边形外缘法兰
    hex_out = []
    for k in range(6):
        a = math.radians(30 + 60 * k)
        hex_out.append(f'{fmt(hx + (TRANSFER_R + 6) * math.cos(a))},{fmt(hy + (TRANSFER_R + 6) * math.sin(a))}')
    S.append(f'    <polygon points="{" ".join(hex_out)}" fill="none" stroke="url(#chFlange)" stroke-width="5" stroke-linejoin="round"/>')
    S.append(f'    {bolts_s}')
    # 中心机械臂活动圆盘
    S.append(f'    <circle cx="{hx}" cy="{hy}" r="64" fill="url(#deckPlate)" stroke="#3a4250" stroke-width="1.5"/>')
    S.append(f'    <circle cx="{hx}" cy="{hy}" r="64" fill="none" stroke="#94a3b8" stroke-width="0.8" stroke-dasharray="3,3"/>')
    S.append(f'    <text x="{hx}" y="{hy - 74}" font-size="8" font-weight="600" fill="#94a3b8" text-anchor="middle" letter-spacing="2">ROBOT</text>')
    S.append('  </g>')

    S.append(arm_group())

    # ===== PA 预对准器（正左，椭圆 rx78/ry64 + 独立 slit 宽 64）=====
    pa_frame, pa_bore, pa_ang, pux, puy, _ = _slit_to(PA_C[0], PA_C[1], PA_RX, SLIT_W_PA)
    S.append('  <g id="PA_SLIT">')
    S.append('    ' + pa_frame)
    S.append('    ' + pa_bore)
    S.append('  </g>')
    S.append('  <g id="PA">')
    S.append(f'    <ellipse cx="{PA_C[0]}" cy="{PA_C[1] + 20}" rx="{PA_RX + 6}" ry="12" fill="url(#groundShadow)"/>')
    S.append(f'    <ellipse cx="{PA_C[0]}" cy="{PA_C[1]}" rx="{PA_RX}" ry="{PA_RY}" fill="url(#chSteel)" stroke="#3a4250" stroke-width="2.6"/>')
    S.append(f'    <ellipse cx="{PA_C[0]}" cy="{PA_C[1]}" rx="{PA_RX}" ry="{PA_RY}" fill="url(#chShade)" pointer-events="none"/>')
    # 朝 hub 暗口
    pmx, pmy = PA_C[0] - pux * (PA_RX - 2), PA_C[1] - puy * (PA_RX - 2)
    S.append(f'    <rect x="-11" y="{-SLIT_W_PA / 2}" width="15" height="{SLIT_W_PA}" rx="3" fill="#0d1420" opacity="0.95" transform="translate({fmt(pmx)} {fmt(pmy)}) rotate({fmt(pa_ang)})"/>')
    S.append(f'    <ellipse cx="{PA_C[0]}" cy="{PA_C[1]}" rx="{PA_RX + 5}" ry="{PA_RY + 5}" fill="none" stroke="url(#chFlange)" stroke-width="5"/>')
    # PA 标签徽章放椭圆上方（朝 hub 反方向，即左侧）
    S.append(f'    <rect x="{PA_C[0] - PA_RX - 30}" y="{PA_C[1] - 10}" width="34" height="18" rx="9" fill="url(#badgeMetal)" stroke="#93a3ba" stroke-width="0.7"/>')
    S.append(f'    <text x="{PA_C[0] - PA_RX - 13}" y="{PA_C[1] + 3}" font-size="11" font-weight="800" fill="#fff" text-anchor="middle">PA</text>')
    S.append(f'    <circle id="PA_C" cx="{PA_C[0]}" cy="{PA_C[1]}" r="1.2" fill="#000" fill-opacity="0.01"/>')
    S.append('  </g>')

    # ===== load locks（LL1 右下 / LL2 左下，同尺寸 + slit 宽 79）、DOOR、SMIF、晶舟、POD =====
    for side in ('1', '2'):
        S.append(port_box(side))
    for side in ('1', '2'):
        cx, cy = PORT_C[side]
        dx, dy = cx - hx, cy - hy
        dist = math.hypot(dx, dy)
        ux0, uy0 = dx / dist, dy / dist
        dang = math.degrees(math.atan2(dy, dx))
        # 闸阀门置于 slit 中段（六边形壁外一点）
        dxp, dyp = hx + ux0 * (TRANSFER_R + 22), hy + uy0 * (TRANSFER_R + 22)
        S.append(f'  <g id="DOOR_P{side}"><rect x="-4" y="-16" width="8" height="32" rx="2" fill="url(#valveMetal)" stroke="#3a4250" stroke-width="1" transform="translate({fmt(dxp)} {fmt(dyp)}) rotate({fmt(dang)})"/></g>')
        # mapping 扫描线（沿 LL 径向；STARTMAPPING offset 驱动）
        mxp, myp = hx + ux0 * (TRANSFER_R + 40), hy + uy0 * (TRANSFER_R + 40)
        S.append(f'  <g id="MAP_P{side}" data-motion-base-visibility="hidden"><line x1="-16" y1="0" x2="16" y2="0" stroke="#dc2626" stroke-width="2.5" transform="translate({fmt(mxp)} {fmt(myp)}) rotate({fmt(dang)})"/></g>')
    for side in ('1', '2'):
        S.append(smif_box(side))
    for side in ('1', '2'):
        S.append(cassette(side))
    for side in ('1', '2'):
        S.append(pod(side))

    S.append(wafer_g('WAFER_CH_A', *CH['A'], r=WAFER_R_CH))
    S.append(wafer_g('WAFER_CH_B', *CH['B'], r=WAFER_R_CH))
    S.append(wafer_g('WAFER_CH_C', *CH['C'], r=WAFER_R_CH))
    S.append(wafer_g('WAFER_PA', *PA_C, r=WAFER_R_PA))
    # WAFER_MOVE 已作为 WAFER_MOVE 子件嵌在 ARM_EXTEND 叉端（随臂转动/伸缩，不独立生成）

    S.append(panel_side('1'))
    S.append(panel_side('2'))

    S.append('  <g id="legend">')
    lx = 300
    for fill, stroke, label in (('#cbd5e1', '#94a3b8', '等待'), ('#22c55e', '#15803d', '加工中'), ('#fde047', '#ca8a04', '已完成')):
        S.append(f'    <rect x="{lx}" y="816" width="14" height="10" rx="2" fill="{fill}" stroke="{stroke}" stroke-width="0.6"/><text x="{lx + 19}" y="825" font-size="9.5" fill="#64748b">{label}</text>')
        lx += 78
    S.append(f'    <rect x="{lx}" y="816" width="14" height="10" rx="7" fill="url(#waferPattern)" stroke="#2f3a4d" stroke-width="0.8"/><text x="{lx + 19}" y="825" font-size="9.5" fill="#64748b">晶圆</text>')
    lx += 78
    S.append(f'    <rect x="{lx}" y="816" width="14" height="10" rx="2" fill="#dc2626"/><text x="{lx + 19}" y="825" font-size="9.5" fill="#64748b">告警</text>')
    S.append('  </g>')
    S.append('</svg>')

    out = '\n'.join(S) + '\n'
    dest = Path(__file__).resolve().parent / 'oxe-drm-topview.svg'
    # 定稿守卫：该 SVG 已由用户在可视化编辑器（models/user/oxe_editor.html）手绘定稿，
    # 本生成器不再作为它的生成源；直接运行会覆盖手工偏移与端口布局。
    if dest.exists() and '--force' not in sys.argv:
        raise SystemExit(
            f'[ABORT] {dest.name} 已是手绘定稿版，生成器会覆盖用户布局。\n'
            '        确需重新生成请显式加 --force（手工偏移与定稿布局会丢失）。')
    dest.write_text(out, encoding='utf-8')
    print(f'[OK] 写出 {dest.name} ({len(out)} bytes)')

    ids = set(re.findall(r'id="([^"]+)"', out))
    required = ['title_block', 'ARM_ZONE', 'ARM_ROBOT', 'ARM_TIP', 'ARM_HUB', 'ARM_ANCHOR', 'PA', 'PA_C',
                'chamber_labels', 'legend', 'gas_box', 'WAFER_MOVE', 'WAFER_PA',
                'ARM_EXTEND',
                'PANEL_P1', 'PANEL_P2', 'LOTLBL_P1', 'LOTLBL_P2', 'LOTSTAT_P1', 'LOTSTAT_P2',
                'DONE_P1', 'DONE_P2', 'WM_P1_LAYER', 'WM_P2_LAYER', 'ALARMPANEL_P1', 'ALARMPANEL_P2',
                'ALARM_P1_CNT', 'ALARM_P2_CNT']
    required += [f'CH_{c}{s}' for c in 'ABC' for s in ('', '_C', '_run', '_alarm', '_unload')]
    required += [f'PORT{i}' for i in (1, 2)] + [f'PORT{i}_C' for i in (1, 2)]
    required += [f'SMIF{i}' for i in (1, 2)] + [f'SMIF{i}_C' for i in (1, 2)]
    required += [f'WAFER_CH_{c}' for c in 'ABC']
    required += [f'POD_P{i}' for i in (1, 2)] + [f'POD_P{i}_LK' for i in (1, 2)]
    required += [f'CST_P{i}' for i in (1, 2)] + [f'DOOR_P{i}' for i in (1, 2)] + [f'MAP_P{i}' for i in (1, 2)]
    required += [f'P{i}_SLOT_{n}' for i in (1, 2) for n in range(1, 26)]
    required += [f'WAFER_P{i}_S{n}' for i in (1, 2) for n in range(1, 26)]
    required += [f'WM_P{i}_S{n}_{s}' for i in (1, 2) for n in range(1, 26) for s in 'WRD']
    required += [f'ALARM_P{i}_L{k}' for i in (1, 2) for k in (1, 2, 3)]
    missing = [r for r in required if r not in ids]
    if missing:
        raise SystemExit(f'[FAIL] 缺少部件 id: {missing}')
    print(f'[OK] 自检通过：{len(required)} 个必需 id 全部存在')


def main():
    """同步定稿 SVG 的 token defs，禁止旧版生成器覆盖手工布局与三段机械臂。"""
    dest = Path(__file__).resolve().parent / 'oxe-drm-topview.svg'
    if not dest.exists():
        raise SystemExit('[ABORT] 缺少已定稿的 oxe-drm-topview.svg；旧版全量生成不符合当前 Motion 契约。')
    if '--force' not in sys.argv:
        raise SystemExit(
            f'[ABORT] {dest.name} 已是手绘定稿版，默认不覆盖。\n'
            '        确需从 tokens.json 同步 defs 请显式加 --force；几何、ID 与 data-pid 会逐字节保留。')

    original = dest.read_bytes()
    matches = list(re.finditer(br'<defs\b[^>]*>.*?</defs>', original, re.DOTALL))
    if len(matches) != 1:
        raise SystemExit(f'[FAIL] 应恰好有一个 defs，实际为 {len(matches)}')
    match = matches[0]
    original_body = original[:match.start()] + original[match.end():]
    rendered_defs = DEFS.encode('utf-8')
    updated = original[:match.start()] + rendered_defs + original[match.end():]
    updated_body = updated[:match.start()] + updated[match.start() + len(rendered_defs):]

    if original_body != updated_body:
        raise SystemExit('[FAIL] 非 defs 内容发生变化，已拒绝写入')
    body_text = original_body.decode('utf-8')
    updated_text = updated.decode('utf-8')
    if extract_ids(body_text) != extract_ids(updated_body.decode('utf-8')):
        raise SystemExit('[FAIL] 部件或资源 id 发生变化，已拒绝写入')
    if extract_pids(body_text) != extract_pids(updated_body.decode('utf-8')):
        raise SystemExit('[FAIL] data-pid 发生变化，已拒绝写入')

    motion_path = dest.with_suffix('.motion.json')
    motion = json.loads(motion_path.read_text(encoding='utf-8'))
    errors, warnings = validate_content(updated_text, motion)
    if errors:
        details = '\n'.join(f'  - {error}' for error in errors)
        raise SystemExit(f'[FAIL] SVG × Motion 校验失败，已拒绝写入:\n{details}')

    dest.write_bytes(updated)
    print(f'[OK] {dest.name}: 仅从 tokens.json 同步 defs，非 defs 字节完全保留')
    print(f'[OK] 动画契约保留：{len(set(extract_ids(body_text)))} 个 id，'
          f'{len(set(extract_parts(body_text)))} 个可检视部件，'
          f'{len(motion.get("motions", []))} 个 Motion step')
    print(f'[OK] 校验通过：0 errors，{len(warnings)} warnings（静态部件/运行时占位符提示）')


if __name__ == '__main__':
    main()
