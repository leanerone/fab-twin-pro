# -*- coding: utf-8 -*-
"""Cluster 机型共享 Motion JSON 构建（LAM2300 / Centris Sym3 / TEL Synapse）。

三台机台事件词表完全一致（OXE 26 步标准集），差异只在机型名/默认腔体，
故 motion 构建收口在这里，避免三份生成器漂移。部件 id 约定：
- Load Port：{LPn}_CST / {LPn}_DOOR
- 工艺腔：{PMn} + {PMn}_run/_alarm/_unload（chamber primitives 产出）
- 双臂：ATM_ARM / VTM_ARM；搬运晶圆：WAFER_MOVE / WAFER_VTM
- 寻边：ALIGNER / ALIGNER_WAFER；塔灯：TOWER_run/_alarm
"""
from __future__ import annotations

import motion as M


def build_cluster_motion(*, machine_type: str, name: str, src: str, deriver: str,
                         description: str, version: str = "1.0",
                         default_port: str = "LP1", default_ch: str = "PM1") -> dict:
    b = M.MotionBuilder(
        machine_type=machine_type,
        name=name,
        src=src,
        deriver=deriver,
        version=version,
        description=description,
    )
    b.param_defaults(PORT=default_port, CH=default_ch, SLOT=1, STATE="RUN")
    b.part_aliases(POD="{PORT}_CST", DOOR="{PORT}_DOOR", ARM="ATM_ARM")

    V = "VTM_ARM"

    b.add("POD_PLACED", [
        M.rule("{PORT}_CST", [M.visibility(True, 0)]),
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ], description="晶舟放到 Load Port")
    b.add("COMPLETED_PORT_LOCK", [
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ], description="端口锁定完成")
    b.add("LOCK_PORT_COMPLETED", [
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ])
    b.add("UNLOCK_PORT_COMPLETED", [
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ])
    b.add("MVIN", [
        M.rule("WAFER_MOVE", [M.visibility(True, 0), M.snap("{PORT}_CST", 0)]),
    ], description="晶圆从晶舟取出，进入大气端")
    b.add("DOOR_OPEN", [
        M.rule("{PORT}_DOOR", [M.offset(0, -8, 300)]),
    ])
    b.add("DOOR_CLOSE", [
        M.rule("{PORT}_DOOR", [M.offset(0, 0, 300)]),
    ])
    b.add("LOAD_CYCLE_STARTED", [
        M.rule("ATM_ARM", [M.rotate(0, 300)]),
        M.rule("WAFER_MOVE", [M.visibility(True, 0)]),
    ], description="ATM 机械臂开始取片循环")
    b.add("LOAD_CYCLE_COMPLETED", [
        M.rule("ALIGNER_WAFER", [M.visibility(True, 0)]),
    ], description="取片完成，晶圆到 Aligner")
    b.add("UNLOAD_CYCLE_COMPLETED", [
        M.rule("WAFER_MOVE", [M.visibility(False, 200)]),
    ])
    b.add("STARTMAPPING", [
        M.rule("ALIGNER", [M.rotate(0, 200)]),
    ], description="开始寻边，Aligner 卡盘回零")
    b.add("WAFER_MAPPING", [
        M.rule("ALIGNER", [M.rotate(180, 900)]),
        M.rule("ALIGNER_WAFER", [M.visibility(True, 0), M.rotate(180, 900)]),
    ], description="晶圆寻边：卡盘带动晶圆旋转")
    b.add("ENDMAPPING", [
        M.rule("ALIGNER", [M.rotate(0, 200)]),
    ])
    b.add("BATCH_INFO_FROM_ECUI", [
        M.rule("TITLE", [M.visibility(True, 0)]),
    ])
    b.add("WAFERLOADED", [
        M.rule("WAFER_MOVE", [M.visibility(True, 0)]),
        M.rule("ATM_ARM", [M.rotate(0, 350)]),
        M.rule("WAFER_VTM", [M.visibility(False, 0)]),
        M.rule("{CH}", [M.opacity(1.0, 200)]),
        M.rule("{CH}_run", [M.visibility(True, 0)]),
    ], description="晶圆经 ATM 臂送入 Airlock，VTM 臂接手送进工艺腔")
    b.add("WAFERUNLOADED", [
        M.rule("WAFER_VTM", [M.visibility(True, 0), M.snap("{CH}", 350)]),
        M.rule(V, [M.rotate(0, 350)]),
        M.rule("{CH}_run", [M.visibility(False, 0)]),
        M.rule("{CH}_unload", [M.visibility(True, 0)]),
    ], description="加工完成，晶圆由 VTM 臂取回")
    b.add("START", [
        M.rule("{CH}_run", [M.visibility(True, 0)]),
        M.rule("{CH}", [M.opacity(1.0, 200)]),
    ], description="工艺腔开始加工")
    b.add("PS", [
        M.rule("{CH}_run", [M.visibility(True, 0)]),
    ], description="工艺进行中")
    b.add("PE", [
        M.rule("{CH}_run", [M.visibility(False, 0)]),
        M.rule("{CH}_unload", [M.visibility(True, 0)]),
    ], description="工艺结束，转入取片态")
    b.add("MVOU", [
        M.rule("WAFER_VTM", [M.visibility(True, 0)]),
        M.rule(V, [M.rotate(0, 350)]),
    ], description="晶圆移出工艺腔")
    b.add("READYTOUNLOAD", [
        M.rule("{CH}_unload", [M.visibility(True, 0)]),
    ])
    # 塔灯与腔体灯均由 visibility 控制（基态隐藏），不用 opacity（对隐藏部件无效）
    b.add("ALARM_REPORT", [
        M.rule("TOWER_alarm", [M.visibility(True, 0)]),
        M.rule("{CH}_alarm", [M.visibility(True, 0)]),
    ], description="告警：塔灯红灯点亮 + 对应腔体告警灯")
    b.add("STATE", [
        M.rule("TOWER_run", [M.visibility(True, 0)]),
    ])
    b.add("TRANSFER", [
        M.rule(V, [M.rotate(0, 400)]),
        M.rule("ATM_ARM", [M.rotate(0, 400)]),
    ], description="双臂联动传输")
    b.add("FDC_CLEARCONTEXT", [
        M.rule("WAFER_MOVE", [M.visibility(False, 0)]),
        M.rule("WAFER_VTM", [M.visibility(False, 0)]),
    ])
    b.add("POD_REMOVED", [
        M.rule("{PORT}_CST", [M.visibility(False, 0)]),
        M.rule("{PORT}_DOOR", [M.visibility(True, 0)]),
    ], description="晶舟移走")

    return b.build()
