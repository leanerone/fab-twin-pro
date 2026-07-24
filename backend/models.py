"""数据模型（SQLAlchemy ORM）- 整合用户现有4张表 + 扩展新表"""
from sqlalchemy import Column, Integer, String, Float, Boolean, Text, DateTime, Identity

from database import Base



# ========== 用户现有4张表（与Oracle保持一致）==========

class DT_EVENT_RAW(Base):
    """原始事件表：RV原始报文（用户现有表）"""
    __tablename__ = "dt_event_raw"

    raw_id = Column(String(255), primary_key=True)
    tool_id = Column(String(255), nullable=False, index=True)
    source_system = Column(String(255), nullable=False)
    source_message_id = Column(String(255), nullable=False)
    received_ts_utc = Column(String(255), index=True)
    event_ts_utc = Column(String(255), nullable=True)
    payload_json = Column(Text)
    parse_status = Column(String(255), default="NEW")
    error_message = Column(String(255), nullable=True)


class DT_EVENT_RAW_CUR(Base):
    """当前状态表：只记录每台机台最新的RV消息"""
    __tablename__ = "dt_event_raw_cur"

    tool_id = Column(String(255), primary_key=True)
    raw_id = Column(String(255))
    source_system = Column(String(255), nullable=False)
    source_message_id = Column(String(255), nullable=False)
    received_ts_utc = Column(String(255), index=True)
    event_ts_utc = Column(String(255), nullable=True)
    payload_json = Column(Text)
    parse_status = Column(String(255), default="NEW")
    error_message = Column(String(255), nullable=True)


class DT_EVENT_STD(Base):
    """标准化事件表（用户现有表）"""
    __tablename__ = "dt_event_std"

    event_id = Column(String(255), primary_key=True)
    raw_id = Column(String(255), index=True)
    tool_id = Column(String(255), nullable=False, index=True)
    event_type = Column(String(255), nullable=False)
    machine_state = Column(String(255))
    lot_id = Column(String(255), nullable=True, index=True)
    recipe_id = Column(String(255), nullable=True)
    pod_position = Column(String(255), nullable=True)
    normalized_json = Column(Text)
    created_ts_utc = Column(String(255), default="SYSTIMESTAMP")


class DT_STATE_SNAPSHOT(Base):
    """状态快照表（用户现有表）"""
    __tablename__ = "dt_state_snapshot"

    snapshot_id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    tool_id = Column(String(255), nullable=False, index=True)
    snapshot_ts_utc = Column(String(255), nullable=False, index=True)
    machine_state = Column(String(255))
    machine_mode = Column(String(255))
    current_alarm_code = Column(String(255), nullable=True)
    current_lot_id = Column(String(255), nullable=True)
    pod_position = Column(String(255), nullable=True)
    snapshot_json = Column(Text)


class DT_ALARM_EVENT(Base):
    """告警事件表（用户现有表）"""
    __tablename__ = "dt_alarm_event"

    alarm_event_id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    tool_id = Column(String(255), nullable=False, index=True)
    alarm_code = Column(String(255), nullable=False)
    alarm_severity = Column(String(255), nullable=False)
    start_ts_utc = Column(String(255), nullable=False, index=True)
    end_ts_utc = Column(String(255), nullable=True)
    duration_sec = Column(Float, nullable=True)
    cycle_id = Column(String(255), nullable=True)
    lot_id = Column(String(255), nullable=True, index=True)
    source_event_start_id = Column(String(255), nullable=True)
    source_event_end_id = Column(String(255), nullable=True)
    alarm_context_json = Column(Text)


# ========== 扩展新表（数字孪生项目需要）==========

class Machine(Base):
    """机台主数据表"""
    __tablename__ = "machines"

    id = Column(String(255), primary_key=True)              # ETCH-101
    model = Column(String(255), default="TEL DRM UNITY")    # 机台型号
    name = Column(String(255))                              # 机台名称
    line = Column(Integer)                             # 产线 1 / 2
    floor = Column(Integer)                            # 楼层 1/2/3/4
    chamber_count = Column(Integer, default=4)         # 腔体数量
    process_type = Column(String(255), default="ETCH")      # 工艺类型（ETCH/LITHO/CMP/PVD等）
    state = Column(String(255), default="idle")             # run/idle/error/maint/setup
    temp = Column(Float, default=25.0)                 # 当前温度 (°C)
    pressure = Column(Float, default=1.0)              # 当前压力 (Pa)
    gas_flow = Column(Float, default=0.0)              # 气体流量 (sccm)
    rf_power = Column(Float, default=0.0)              # RF 功率 (W)
    wafer_count = Column(Integer, default=0)           # 累计加工晶圆数
    alarm_count = Column(Integer, default=0)           # 累计告警数
    process_step = Column(Integer, default=0)          # 当前工艺步骤 0-6
    has_smif = Column(Boolean, default=False)          # 是否有 SMIF 接口
    updated_at = Column(String(255))                        # 最后更新时间（ISO 字符串）
    x_pos = Column(Float, default=0)                   # 在产线布局中的X坐标（3D视图）
    y_pos = Column(Float, default=0)                   # 在产线布局中的Y坐标（3D视图）
    floor_x = Column(Float, default=0)                 # 楼层平面图X坐标（百分比）
    floor_y = Column(Float, default=0)                 # 楼层平面图Y坐标（百分比）


class Lot(Base):
    """批次主数据表"""
    __tablename__ = "lots"

    id = Column(String(255), primary_key=True)              # LOTxxxxx
    machine_id = Column(String(255), index=True)
    product = Column(String(255))                           # 产品型号（DRAM-1X/NAND-3D等）
    wafer_count = Column(Integer, default=25)          # 晶圆数量
    status = Column(String(255), default="pending")         # run/done/pending/hold
    start_time = Column(String(255))                        # 开始时间（ISO 字符串）
    end_time = Column(String(255))                          # 结束时间（ISO 字符串）
    recipe_id = Column(String(255), nullable=True)


class Recipe(Base):
    """工艺配方表"""
    __tablename__ = "recipes"

    id = Column(String(255), primary_key=True)              # 配方ID
    name = Column(String(255))                              # 配方名称
    machine_id = Column(String(255), index=True)
    process_type = Column(String(255))                      # 工艺类型
    temperature = Column(Float)                        # 目标温度 (°C)
    pressure = Column(Float)                           # 目标压力 (Pa)
    rf_power = Column(Float)                           # 目标RF功率 (W)
    gas_flow = Column(Float)                           # 气体流量 (sccm)
    process_time = Column(Float)                       # 工艺时间 (秒)
    updated_at = Column(String(255))


class ChamberSnapshot(Base):
    """腔体级状态快照（4个腔体独立参数）"""
    __tablename__ = "chamber_snapshots"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    machine_id = Column(String(255), index=True)
    chamber_id = Column(String(255), index=True)            # PM-1/PM-2/PM-3/PM-4
    timestamp = Column(String(255), index=True)
    temperature = Column(Float)                        # 腔体温度 (°C)
    pressure = Column(Float)                           # 腔体压力 (Pa)
    rf_power = Column(Float)                           # RF功率 (W)
    gas_flow = Column(Float)                           # 气体流量 (sccm)
    is_running = Column(Boolean, default=False)        # 是否正在加工


class OHTPosition(Base):
    """OHT天车位置（Line 2 SMIF系统）"""
    __tablename__ = "oht_positions"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    oht_id = Column(String(255), index=True)                # OHT天车ID
    lot_id = Column(String(255), nullable=True)             # 当前搬运的Lot
    x_pos = Column(Float)                              # X坐标
    y_pos = Column(Float)                              # Y坐标（高度）
    z_pos = Column(Float)                              # Z坐标
    status = Column(String(255))                            # moving/idle/loading/unloading
    target_machine_id = Column(String(255), nullable=True)  # 目标机台
    timestamp = Column(String(255), index=True)


class AIInsight(Base):
    """AI分析结果表"""
    __tablename__ = "ai_insights"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    machine_id = Column(String(255), index=True)
    lot_id = Column(String(255), nullable=True)
    insight_type = Column(String(255))                      # anomaly_detection/prediction/recommendation
    confidence = Column(Float)                         # 置信度 0-1
    summary = Column(Text)                             # 分析摘要
    details = Column(Text)                             # 详细分析（JSON）
    created_at = Column(String(255))


class MachineEvent(Base):
    """机台事件：状态切换 / 传感器采样 / 告警 / 晶圆转移"""
    __tablename__ = "machine_events"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    machine_id = Column(String(255), index=True)
    timestamp = Column(String(255), index=True)             # ISO 时间字符串
    event_type = Column(String(255))                        # STATE/SENSOR/ALARM/TRANSFER
    event_code = Column(String(255))                        # 事件代码
    description = Column(Text)                         # 事件描述
    level = Column("LEVEL", String(255), default="info")    # warn/crit/info (Oracle reserved word)
    metric = Column(String(255), nullable=True)             # temperature/pressure/gasflow/rf
    value = Column(Float, nullable=True)               # 传感器数值
    lot_id = Column(String(255), nullable=True)             # 关联的 Lot


class Alarm(Base):
    """告警记录"""
    __tablename__ = "alarms"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    machine_id = Column(String(255), index=True)
    timestamp = Column(String(255), index=True)
    alarm_code = Column(String(255))                        # TEMP_OVER/RF_DRIFT/PRESS_UNSTABLE/GAS_LEAK
    description = Column(Text)
    level = Column("LEVEL", String(255), default="warn")    # crit/warn (Oracle reserved word)
    resolved = Column(Boolean, default=False)          # 是否已解决
    lot_id = Column(String(255), nullable=True)


class DashboardKPI(Base):
    """看板预计算KPI指标"""
    __tablename__ = "dashboard_kpi"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    machine_id = Column(String(255), index=True)
    date = Column(String(255), index=True)                  # 日期 YYYY-MM-DD
    category = Column(String(255))                          # metric类型
    value = Column(Float)                              # KPI数值
    updated_at = Column(String(255))


class Floor(Base):
    """楼层信息表"""
    __tablename__ = "floors"

    id = Column(Integer, primary_key=True)             # 楼层编号 1/2/3/4
    name = Column(String(255))                              # 楼层名称（1F/2F/3F/4F）
    description = Column(String(255), nullable=True)        # 楼层描述
    width = Column(Float, default=100)                 # 楼层宽度（米）
    height = Column(Float, default=100)                # 楼层高度（米）
    svg_map = Column(Text, nullable=True)              # 楼层SVG平面图
    created_at = Column(String(255))
    updated_at = Column(String(255))


class FloorArea(Base):
    """楼层区域表（设备区/过道/电梯/逃生门等）"""
    __tablename__ = "floor_areas"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    floor_id = Column(Integer, index=True)             # 所属楼层
    name = Column(String(255))                              # 区域名称（CST清洗/PMP/设备区等）
    area_type = Column(String(255))                         # 区域类型（equipment/pump/walkway/elevator/exit）
    x_pos = Column(Float)                              # 区域左上角X坐标（百分比）
    y_pos = Column(Float)                              # 区域左上角Y坐标（百分比）
    width = Column(Float)                              # 区域宽度（百分比）
    height = Column(Float)                             # 区域高度（百分比）
    color = Column(String(255), default="#1e293b")          # 区域颜色
    description = Column(String(255), nullable=True)


class Track(Base):
    """天车轨迹表（2D平面图上绘制，3D中显示）"""
    __tablename__ = "tracks"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    floor_id = Column(Integer, index=True)             # 所属楼层
    name = Column(String(255))                              # 轨迹名称
    track_type = Column(String(255), default="oht")         # 轨迹类型（oht/agv/rail）
    points_json = Column(Text)                         # 轨迹点JSON [[x,y],...]
    color = Column(String(255), default="#00d4ff")          # 轨迹颜色
    speed = Column(Float, default=1.0)                 # 天车运行速度
    created_at = Column(String(255))


class Vehicle(Base):
    """天车/搬运车表"""
    __tablename__ = "vehicles"

    id = Column(String(255), primary_key=True)              # 天车ID
    name = Column(String(255))                              # 天车名称
    vehicle_type = Column(String(255), default="oht")       # 类型（oht/agv）
    floor_id = Column(Integer, index=True)             # 所属楼层
    track_id = Column(Integer, nullable=True)          # 绑定的轨迹ID
    state = Column(String(255), default="idle")             # idle/moving/loading/unloading
    progress = Column(Float, default=0.0)              # 在轨迹上的进度 0-1
    lot_id = Column(String(255), nullable=True)             # 当前搬运的Lot
    target_machine_id = Column(String(255), nullable=True)  # 目标机台
    speed = Column(Float, default=1.0)                 # 运行速度
    updated_at = Column(String(255))


# ========== 用户与权限表 ==========

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(String(255), primary_key=True)
    username = Column(String(255), nullable=False, unique=True)
    display_name = Column(String(255), nullable=False)
    email = Column(String(255))
    department = Column(String(255))
    role = Column(String(255), default="user")
    windows_sid = Column(String(255), nullable=True, unique=True)
    last_login_at = Column(String(255))
    created_at = Column(String(255))
    updated_at = Column(String(255))


class Role(Base):
    """角色表"""
    __tablename__ = "roles"

    id = Column(String(255), primary_key=True)
    name = Column(String(255), nullable=False)
    description = Column(String(255))


class Permission(Base):
    """权限表"""
    __tablename__ = "perm_data"

    id = Column(String(255), primary_key=True)
    name = Column("perm_name", String(255), nullable=False)
    description = Column("perm_desc", String(255))
    resource = Column("res_col", String(255))
    action = Column("act_col", String(255))


class RolePermission(Base):
    """角色权限关联表"""
    __tablename__ = "role_permissions"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    role_id = Column(String(255), index=True)
    permission_id = Column(String(255), index=True)


class MachineToolMapping(Base):
    """机台ID与Tool ID映射表"""
    __tablename__ = "machine_tool_mappings"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    machine_id = Column(String(255), nullable=False, index=True)
    tool_id = Column(String(255), nullable=False, index=True)
    description = Column(String(255))
    is_primary = Column(Boolean, default=True)


# ========== 机台型号配置表（核心：建模规范 + 动作匹配）==========

class MachineModelConfig(Base):
    """机台型号配置：定义一种机型的2D/3D视图、部件、事件动作映射
    新机台型号接入无需改代码，通过配置完成
    """
    __tablename__ = "machine_model_configs"

    model_id = Column(String(255), primary_key=True)
    model_name = Column(String(255), nullable=False)
    vendor = Column(String(255), default="")
    process_type = Column(String(255), default="ETCH")
    version = Column(String(255), default="1.0")
    view_mode = Column(String(255), default="threejs")
    description = Column(Text, default="")

    views_config_json = Column(Text, default="{}")
    parts_config_json = Column(Text, default="[]")
    state_mapping_json = Column(Text, default="[]")
    hotspots_config_json = Column(Text, default="[]")

    created_at = Column(String(255))
    updated_at = Column(String(255))


class EventActionMapping(Base):
    """事件动作映射：半导体事件 → 部件动作序列
    配置化实现事件驱动的可视化动画
    """
    __tablename__ = "event_action_mappings"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    model_id = Column(String(255), nullable=False, index=True)
    mapping_id = Column(String(255), nullable=False)
    description = Column(String(255), default="")

    trigger_event_type = Column(String(255), default="STATE_CHANGE")
    trigger_event_code = Column(String(255), default="")
    trigger_condition_json = Column(Text, default="{}")

    action_sequence_json = Column(Text, default="[]")
    rollback_event_type = Column(String(255), default="")
    rollback_event_code = Column(String(255), default="")

    created_at = Column(String(255))
    updated_at = Column(String(255))


# ========== AI 配置持久化表 ==========

class AIConfig(Base):
    """AI配置持久化：存储AI模型、API、Provider等配置
    重启后从DB加载，不再依赖环境变量丢失
    """
    __tablename__ = "ai_configs"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    config_key = Column(String(255), nullable=False, unique=True, index=True)
    config_value = Column(Text, default="")
    description = Column(String(255), default="")
    updated_at = Column(String(255))
    updated_by = Column(String(255), default="system")


class AIProviderConfig(Base):
    """AI Provider多配置管理：支持保存多个LLM配置，切换使用
    例如：智谱GLM生产环境、OpenAI测试环境、DeepSeek备用等
    """
    __tablename__ = "ai_provider_configs"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    name = Column(String(255), nullable=False)           # 配置名称（如"智谱GLM-生产"）
    provider = Column(String(255), nullable=False, index=True)  # zhipu/openai/deepseek/qwen/custom/local
    base_url = Column(String(512), default="")           # API地址
    api_key = Column(String(512), default="")            # API密钥（加密存储）
    model = Column(String(255), default="")              # 模型名称
    temperature = Column(Float, default=0.7)             # 生成温度
    max_tokens = Column(Integer, default=2048)           # 最大token数
    is_enabled = Column(Boolean, default=True)           # 是否启用
    is_default = Column(Boolean, default=False)          # 是否为默认配置
    sort_order = Column(Integer, default=0)              # 排序
    description = Column(String(512), default="")        # 配置说明
    created_at = Column(String(255))
    updated_at = Column(String(255))


class AIUsageLog(Base):
    """AI Token使用量统计：记录每次调用的token消耗"""
    __tablename__ = "ai_usage_logs"

    id = Column(Integer, Identity(start=1, increment=1), primary_key=True)
    session_id = Column(String(255), index=True)          # 会话ID
    config_id = Column(Integer, nullable=True, index=True) # 使用的配置ID
    provider = Column(String(255), index=True)            # 实际使用的provider
    model = Column(String(255))                           # 实际使用的模型
    prompt_tokens = Column(Integer, default=0)            # 输入token数
    completion_tokens = Column(Integer, default=0)        # 输出token数
    total_tokens = Column(Integer, default=0)             # 总token数
    question_preview = Column(String(512), default="")    # 用户问题前200字符
    success = Column(Boolean, default=True)               # 是否成功
    error_msg = Column(String(512), nullable=True)        # 错误信息
    created_at = Column(String(255), index=True)
