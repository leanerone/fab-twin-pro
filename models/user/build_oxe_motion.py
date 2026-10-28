# -*- coding: utf-8 -*-
"""
oxe-drm-topview.motion.json 构建器（在原 23 step 基础上增量增强，保留既有编排）

新增语义：
- WAFER_MAPPING：解析 deriver 产出的 SMAP（25 位 0/1/2/3）→ Wafer Map 三态条 +
  晶舟 25 条金属片条逐槽显示（1=等待 W / 2=加工 R / 3=完成 D）
- WAFERLOADED：本槽 W→R（绿）
- WAFERUNLOADED：本槽 R→D（黄）+ DONE 计数 + 状态文案「Processing end」
- BATCH_INFO_FROM_ECUI：LOT 徽章写批次号
- 各工艺节点：状态徽章写中文状态
- ALARM_REPORT：计数徽章 + 3 行最近告警（队列由 deriver 维护）
- POD_PLACED / POD_REMOVED：面板与片条初始化/复位
"""
import json
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent
SRC = BASE / "oxe-drm-topview.motion.json"

# 幂等：每次从 git HEAD 的基线 JSON 重建（本脚本只增量、不去重，重复运行不能叠加规则）
head = subprocess.run(
    ["git", "show", "HEAD:models/user/oxe-drm-topview.motion.json"],
    cwd=BASE.parents[1], capture_output=True, text=True, encoding="utf-8", check=True)
d = json.loads(head.stdout)

# ---- document / ext ----
d["document"]["coord"]["viewBox"] = [0, 0, 1080, 840]

# v2.2 几何变化：PORT 内部高度 88，mapping 水平扫描线行程改为 84；底部滑门横移收窄到 30
for _m in d["motions"]:
    if _m["step"] == "STARTMAPPING":
        for _r in _m["rules"]:
            for _a in _r.get("actions", []):
                if _a.get("type") == "offset":
                    _a["offset_y"] = -84
    if _m["step"] == "DOOR_OPEN":
        for _r in _m["rules"]:
            for _a in _r.get("actions", []):
                if _a.get("type") == "offset":
                    _a["offset_x"] = -30
    if _m["step"] == "DOOR_CLOSE":
        for _r in _m["rules"]:
            for _a in _r.get("actions", []):
                if _a.get("type") == "offset":
                    _a["offset_x"] = 30

ext = d.setdefault("ext", {})
ext["version"] = "2.1"
ext["description"] = (
    "OXE DRM UNITY 刻蚀机 2D 顶视图动画（motion2d 统一管线，v2.1 AMAT 风格版）："
    "POD/CST 进出、门、mapping 扫描、取放片编排、腔体状态；"
    "材料详情面板（LOT/状态/完成 + 25 槽 Wafer Map 三态 + 晶舟片条）与左右告警消息面板"
)
ext["viewBox_fallback"] = [0, 0, 1080, 840]
aliases = ext.setdefault("event_aliases", {})
aliases.setdefault("ENDMAPPING", "WAFER_MAPPING")

SLOTS = list(range(1, 26))


# ============ v2.3 真实机械臂运动原语 ============
# 嵌套结构：ARM_ROBOT(绕 hub rotate) > ARM_EXTEND(径向 offset 伸缩) > 叉端 + WAFER_MOVE(随动)
# 标准动作：收回状态下旋转 → 伸出取/放 → 收回。晶圆为叉端子件，全程不脱离 blade。
def rotate(part, angle_param, dur=700, phase=None):
    return {"phase": phase if phase is not None else 0, "target_part_id": part,
            "actions": [{"type": "rotate", "angle": "{" + angle_param + "}",
                         "duration": dur, "easing": "linear"}]}


def extend(out, dur=650, phase=None, target_param="ARM_EXTEND_CH"):
    """ARM_EXTEND 径向伸缩：out=True 伸出(offset +对应单元距离参数)，False 收回(offset 0)。
    target_param: ARM_EXTEND_PORT / _PA / _CH（各单元距离不同）"""
    return {"phase": phase if phase is not None else 0, "target_part_id": "ARM_EXTEND",
            "actions": [{"type": "offset", "offset_x": "{" + target_param + "}" if out else 0,
                         "offset_y": 0, "duration": dur, "easing": "linear"}]}


def snap_home(part, phase=None):
    return {"phase": phase if phase is not None else 0, "target_part_id": part,
            "actions": [{"type": "snap", "to_part_id": "{home}", "duration": 0}]}


def replace_rules(step, rules):
    by_step(step)["rules"] = rules


PH = 0  # 全局 phase 计数器工厂


def phases_for(*seq):
    """给 [(kind, payload)...] 顺序分配递增 phase，返回规则列表。
    kind: 'r'(rotate arm) / 'eout'/'ein'(extend, payload=port/pa/ch) /
          'v'(visibility) / 'snap' / 't'(text)"""
    out = []
    ph = [0]

    def nxt():
        v = ph[0]; ph[0] += 1; return v

    for kind, payload in seq:
        if kind == "r":
            out.append(rotate("ARM_ROBOT", payload, phase=nxt()))
        elif kind == "eout":
            unit = payload or "ch"
            param = {"port": "ARM_EXTEND_PORT", "pa": "ARM_EXTEND_PA",
                     "ch": "ARM_EXTEND_CH"}[unit]
            out.append(extend(True, phase=nxt(), target_param=param))
        elif kind == "ein":
            out.append(extend(False, phase=nxt()))
        elif kind == "v":
            target, show = payload
            out.append(vis(target, show, phase=nxt()))
        elif kind == "snap":
            out.append(snap_home(payload, phase=nxt()))
        elif kind == "t":
            target, content, fill = payload
            out.append(text_on(target, content, fill, phase=nxt()))
        elif kind == "phasegap":
            ph[0] += payload
    return out


def vis(target, show, when=None, phase=1):
    r = {"phase": phase, "target_part_id": target,
         "actions": [{"type": "visibility", "to": bool(show), "duration": 0}]}
    if when:
        r["when"] = when
    return r


def text_on(target, content, fill="#1f2933", size=9, phase=1, when=None):
    r = {"phase": phase, "target_part_id": target,
         "actions": [{"type": "text", "content": content, "fill": fill,
                      "fontSize": size, "strokeWidth": 0}]}
    if when:
        r["when"] = when
    return r


def text_clear(target, phase=1):
    return {"phase": phase, "target_part_id": target,
            "actions": [{"type": "text", "content": " ", "strokeWidth": 0}]}


def by_step(name):
    for m in d["motions"]:
        if m["step"] == name:
            return m
    raise KeyError(name)


def add_rule(step, rule):
    by_step(step)["rules"].append(rule)


# ================= POD_PLACED：面板初始化 =================
for p in (1, 2):
    P = str(p)
    add_rule("POD_PLACED", text_on(f"LOTLBL_P{P}", "等待绑定…", "#94a3b8", 8.5,
                                   when=f"params.PORT == '{P}'"))
    add_rule("POD_PLACED", text_on(f"LOTSTAT_P{P}", "POD PLACED", "#1f2933", 8.5,
                                   when=f"params.PORT == '{P}'"))
    add_rule("POD_PLACED", text_on(f"DONE_P{P}", "0/25", "#1f2933", 8.5,
                                   when=f"params.PORT == '{P}'"))
    add_rule("POD_PLACED", text_clear(f"ALARM_P{P}_CNT", when=None) if False else
             text_on(f"ALARM_P{P}_CNT", "0", "#fecaca", 8.5,
                     when=f"params.PORT == '{P}'"))
    for k in (1, 2, 3):
        add_rule("POD_PLACED", text_clear(f"ALARM_P{P}_L{k}"))
    add_rule("POD_PLACED", {"phase": 1, "target_part_id": f"WM_P{P}_LAYER",
                            "when": f"params.PORT == '{P}'",
                            "actions": [{"type": "visibility", "to": True, "duration": 0}]})
    # 新批次入场：三态条全部隐藏（等 WAFER_MAPPING 展开）；晶舟片条也全隐藏（mapping 后按 SMAP 亮）
    for n in SLOTS:
        for s in "WRD":
            add_rule("POD_PLACED", vis(f"WM_P{P}_S{n}_{s}", False,
                                       when=f"params.PORT == '{P}'"))
        add_rule("POD_PLACED", vis(f"WAFER_P{P}_S{n}", False,
                                   when=f"params.PORT == '{P}'"))

# ================= LOCK_PORT_COMPLETED / MVIN / 门 / LOAD / STARTMAPPING：状态文案 =================
STATUS_TEXTS = [
    ("LOCK_PORT_COMPLETED", "CHECK RCMS"),
    ("COMPLETED_PORT_LOCK", "CHECK RCMS"),
    ("MVIN", "LOADING LOT"),
    ("DOOR_OPEN", "DOOR OPEN"),
    ("DOOR_CLOSE", "DOOR CLOSE"),
    ("LOAD_CYCLE_STARTED", "LOAD START"),
    ("LOAD_CYCLE_COMPLETED", "LOAD OK"),
    ("STARTMAPPING", "MAPPING…"),
]
for step, label in STATUS_TEXTS:
    for p in (1, 2):
        add_rule(step, text_on(f"LOTSTAT_P{p}", label, "#1f2933", 8.5,
                               when=f"params.PORT == '{p}'"))

# ================= BATCH_INFO_FROM_ECUI：LOT 徽章 =================
for p in (1, 2):
    add_rule("BATCH_INFO_FROM_ECUI",
             text_on(f"LOTLBL_P{p}", "{LOT_ID}", "#e2e8f0", 8.5,
                     when=f"params.PORT == '{p}'"))
    add_rule("BATCH_INFO_FROM_ECUI",
             text_on(f"LOTSTAT_P{p}", "BATCH INFO", "#1f2933", 8.5,
                     when=f"params.PORT == '{p}'"))

# ================= WAFER_MAPPING（含 ENDMAPPING 别名）：SMAP → 片条 + 三态 =================
# deriver 参数：SMAP=25 位映射串；SM01..SM25=逐槽字符（when 白名单不允许 []，下标在 deriver 展开）
m_map = by_step("WAFER_MAPPING")
for p in (1, 2):
    P = str(p)
    add_rule("WAFER_MAPPING", text_on(f"LOTSTAT_P{P}", "MAPPING OK", "#1f2933", 8.5,
                                      when=f"params.PORT == '{P}'"))
    for n in SLOTS:
        sm = f"SM{n:02d}"
        gate = f"params.PORT == '{P}'"
        occupied = (f"params.{sm} == '1' || params.{sm} == '2' || params.{sm} == '3'")
        # 晶舟金属片条（1/2/3 亮，0 灭）；PORT 门控防止重映射一端口时误改另一端口
        add_rule("WAFER_MAPPING", vis(f"WAFER_P{P}_S{n}", True, phase=1,
                                      when=f"{gate} && ({occupied})"))
        add_rule("WAFER_MAPPING", vis(f"WAFER_P{P}_S{n}", False, phase=1,
                                      when=f"{gate} && !({occupied})"))
        # 三态条互斥（0 值时三者全灭，保持 POD_PLACED 的隐藏态）
        add_rule("WAFER_MAPPING", vis(f"WM_P{P}_S{n}_W", True, phase=1,
                                      when=f"{gate} && params.{sm} == '1'"))
        add_rule("WAFER_MAPPING", vis(f"WM_P{P}_S{n}_R", True, phase=1,
                                      when=f"{gate} && params.{sm} == '2'"))
        add_rule("WAFER_MAPPING", vis(f"WM_P{P}_S{n}_D", True, phase=1,
                                      when=f"{gate} && params.{sm} == '3'"))

# ================= WAFERLOADED：本槽 W→R + 状态/完成计数不变 =================
# ================= WAFERLOADED：真实伸缩臂送片（取片口→PA 预对准→工艺腔）=================
# 标准动作模型：收回状态旋转 → 伸出取/放 → 收回；WAFER_MOVE 为叉端子件全程随动。
# 先清掉基线里基于 snap 的旧编排（避免晶圆瞬移），只保留本脚本生成的运动 + 下方面板规则。
for _p in (1, 2):
    seq = []
    # 0 复位：臂收回、朝向取片口（收回时旋转，安全不撞通道）
    seq.append(("ein", None))
    seq.append(("r", "ARM_PORT_ANGLE"))
    # 1 伸出取片口 → 叉端显示晶圆（夹片）→ 收回
    seq.append(("eout", "port"))
    seq.append(("v", ("WAFER_MOVE", True)))
    seq.append(("ein", None))
    # 2 转 PA → 伸出把片放到预对准台（叉端隐、PA 显）→ 收回
    seq.append(("r", "ARM_PA_ANGLE"))
    seq.append(("eout", "pa"))
    seq.append(("v", ("WAFER_PA", True)))
    seq.append(("v", ("WAFER_MOVE", False)))
    seq.append(("ein", None))
    # 3 再伸 PA 取回对准后的片（PA 隐、叉端显）→ 收回
    seq.append(("eout", "pa"))
    seq.append(("v", ("WAFER_PA", False)))
    seq.append(("v", ("WAFER_MOVE", True)))
    seq.append(("ein", None))
    # 4 转目标工艺腔 → 伸出穿过 slit 放片（叉端隐、CH 显、CH_run 绿层）→ 收回 → HOME
    seq.append(("r", "ARM_CH_ANGLE"))
    seq.append(("eout", "ch"))
    seq.append(("v", ("{WAFER_CH}", True)))
    seq.append(("v", ("WAFER_MOVE", False)))
    seq.append(("v", ("{CH_RUN}", True)))
    seq.append(("ein", None))
    seq.append(("r", "ARM_HOME"))
    core = phases_for(*seq)
    # 端口门控 + 目标腔体用 {CH_RUN}/{WAFER_CH} 模板（deriver 已解析为具体腔）
    for r in core:
        r["when"] = f"params.PORT == '{_p}'"
    replace_rules("WAFERLOADED", core)

# ================= WAFERUNLOADED：从工艺腔取片 → PA → 送回取片口 =================
for _p in (1, 2):
    seq = []
    seq.append(("ein", None))
    # 1 转工艺腔，伸入取出加工完的片（CH 隐、CH_run 灭、叉端显）→ 收回
    seq.append(("r", "ARM_CH_ANGLE"))
    seq.append(("eout", "ch"))
    seq.append(("v", ("{WAFER_CH}", False)))
    seq.append(("v", ("{CH_RUN}", False)))
    seq.append(("v", ("WAFER_MOVE", True)))
    seq.append(("ein", None))
    # 2 转 PA 放片（短暂预对准）→ 收回 → 再取回
    seq.append(("r", "ARM_PA_ANGLE"))
    seq.append(("eout", "pa"))
    seq.append(("v", ("WAFER_PA", True)))
    seq.append(("v", ("WAFER_MOVE", False)))
    seq.append(("ein", None))
    seq.append(("eout", "pa"))
    seq.append(("v", ("WAFER_PA", False)))
    seq.append(("v", ("WAFER_MOVE", True)))
    seq.append(("ein", None))
    # 3 转取片口，伸入放回晶舟（叉端隐）→ 收回 → HOME
    seq.append(("r", "ARM_PORT_ANGLE"))
    seq.append(("eout", "port"))
    seq.append(("v", ("WAFER_MOVE", False)))
    seq.append(("ein", None))
    seq.append(("r", "ARM_HOME"))
    core = phases_for(*seq)
    for r in core:
        r["when"] = f"params.PORT == '{_p}'"
    replace_rules("WAFERUNLOADED", core)

# ---- 面板三态/文案规则（端口门控，追加到上面核心编排之后）----
for p in (1, 2):
    P = str(p)
    add_rule("WAFERLOADED", text_on(f"LOTSTAT_P{P}", "PROCESSING", "#16a34a", 8.5,
                                    when=f"params.PORT == '{P}'"))
    for n in SLOTS:
        add_rule("WAFERLOADED", vis(f"WM_P{P}_S{n}_W", False,
                                    when=f"params.PORT == '{P}' && params.SLOT == '{n}'"))
        add_rule("WAFERLOADED", vis(f"WM_P{P}_S{n}_R", True,
                                    when=f"params.PORT == '{P}' && params.SLOT == '{n}'"))
        add_rule("WAFERLOADED", vis(f"WM_P{P}_S{n}_D", False,
                                    when=f"params.PORT == '{P}' && params.SLOT == '{n}'"))
        add_rule("WAFERLOADED", vis(f"WAFER_P{P}_S{n}", False,
                                    when=f"params.PORT == '{P}' && params.SLOT == '{n}'"))

# ================= WAFERUNLOADED：本槽 R→D + DONE 计数 + 状态 =================
for p in (1, 2):
    P = str(p)
    add_rule("WAFERUNLOADED", text_on(f"LOTSTAT_P{P}", "PROCESSING", "#16a34a", 8.5,
                                      when=f"params.PORT == '{P}'"))
    add_rule("WAFERUNLOADED", text_on(f"DONE_P{P}", "{DONE_COUNT}", "#ca8a04", 8.5,
                                      when=f"params.PORT == '{P}'"))
    for n in SLOTS:
        add_rule("WAFERUNLOADED", vis(f"WM_P{P}_S{n}_R", False,
                                      when=f"params.PORT == '{P}' && params.SLOT == '{n}'"))
        add_rule("WAFERUNLOADED", vis(f"WM_P{P}_S{n}_D", True,
                                      when=f"params.PORT == '{P}' && params.SLOT == '{n}'"))
        add_rule("WAFERUNLOADED", vis(f"WAFER_P{P}_S{n}", True,
                                      when=f"params.PORT == '{P}' && params.SLOT == '{n}'"))

# ================= PE / READYTOUNLOAD / UNLOAD_CYCLE：状态文案 =================
for p in (1, 2):
    add_rule("PE", text_on(f"LOTSTAT_P{p}", "PROCESS END", "#1f2933", 8.5,
                           when=f"params.PORT == '{p}'"))
    add_rule("READYTOUNLOAD", text_on(f"LOTSTAT_P{p}", "READY UNLOAD", "#ca8a04", 8.5,
                                      when=f"params.PORT == '{p}'"))
    add_rule("UNLOAD_CYCLE_COMPLETED", text_on(f"LOTSTAT_P{p}", "UNLOAD OK", "#1f2933", 8.5,
                                               when=f"params.PORT == '{p}'"))

# ================= ALARM_REPORT：计数 + 3 行（端口由 deriver 按归属决定） =================
for p in (1, 2):
    P = str(p)
    add_rule("ALARM_REPORT", text_on(f"ALARM_P{P}_CNT", "{ALARM_COUNT}", "#fecaca", 8.5,
                                     when=f"params.ALARM_PORT == '{P}'"))
    add_rule("ALARM_REPORT", text_on(f"ALARM_P{P}_L1", "{AL1}", "#991b1b", 7.5,
                                     when=f"params.ALARM_PORT == '{P}'"))
    add_rule("ALARM_REPORT", text_on(f"ALARM_P{P}_L2", "{AL2}", "#991b1b", 7.5,
                                     when=f"params.ALARM_PORT == '{P}'"))
    add_rule("ALARM_REPORT", text_on(f"ALARM_P{P}_L3", "{AL3}", "#991b1b", 7.5,
                                     when=f"params.ALARM_PORT == '{P}'"))
    add_rule("ALARM_REPORT", text_on(f"LOTSTAT_P{P}", "ALARM", "#dc2626", 8.5,
                                     when=f"params.ALARM_PORT == '{P}'"))

# ================= POD_REMOVED：面板与片条全复位 =================
for p in (1, 2):
    P = str(p)
    add_rule("POD_REMOVED", vis(f"WM_P{P}_LAYER", False, when=f"params.PORT == '{P}'"))
    for n in SLOTS:
        for s in "WRD":
            add_rule("POD_REMOVED", vis(f"WM_P{P}_S{n}_{s}", False,
                                        when=f"params.PORT == '{P}'"))
        add_rule("POD_REMOVED", vis(f"WAFER_P{P}_S{n}", False,
                                    when=f"params.PORT == '{P}'"))
    add_rule("POD_REMOVED", text_on(f"LOTLBL_P{P}", "-", "#94a3b8", 8.5,
                                    when=f"params.PORT == '{P}'"))
    add_rule("POD_REMOVED", text_on(f"LOTSTAT_P{P}", "IDLE", "#94a3b8", 8.5,
                                    when=f"params.PORT == '{P}'"))
    add_rule("POD_REMOVED", text_on(f"DONE_P{P}", "-", "#94a3b8", 8.5,
                                    when=f"params.PORT == '{P}'"))
    add_rule("POD_REMOVED", text_on(f"ALARM_P{P}_CNT", "0", "#fecaca", 8.5,
                                    when=f"params.PORT == '{P}'"))
    for k in (1, 2, 3):
        add_rule("POD_REMOVED", text_clear(f"ALARM_P{P}_L{k}"))

# ---- 校验 step 覆盖 & 写出 ----
steps = [m["step"] for m in d["motions"]]
assert "WAFER_MAPPING" in steps
out = json.dumps(d, ensure_ascii=False, indent=2)
SRC.write_text(out + "\n", encoding="utf-8")
total = sum(len(m["rules"]) for m in d["motions"])
print(f"[OK] 写出 {SRC.name}：{len(steps)} steps / {total} rules")
for m in d["motions"]:
    print(f"  {m['step']}: {len(m['rules'])} rules")
