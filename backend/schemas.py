"""Pydantic 请求/响应模型"""
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, ConfigDict


class MachineOut(BaseModel):
    """机台响应模型"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: Optional[str] = ""
    name: Optional[str] = ""
    line: Optional[int] = 0
    chamber_count: Optional[int] = 4
    process_type: Optional[str] = ""
    state: Optional[str] = "idle"
    temp: Optional[float] = 25.0
    pressure: Optional[float] = 1.0
    gas_flow: Optional[float] = 0.0
    rf_power: Optional[float] = 0.0
    wafer_count: Optional[int] = 0
    alarm_count: Optional[int] = 0
    process_step: Optional[int] = 0
    has_smif: Optional[bool] = False
    updated_at: Optional[str] = ""
    x_pos: Optional[float] = 0.0
    y_pos: Optional[float] = 0.0
    floor_x: Optional[float] = 0.0
    floor_y: Optional[float] = 0.0


class EventOut(BaseModel):
    """事件响应模型"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_id: str
    timestamp: str
    event_type: str
    event_code: str
    description: str
    level: str
    metric: Optional[str] = None
    value: Optional[float] = None
    lot_id: Optional[str] = None


class LotOut(BaseModel):
    """批次响应模型"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    machine_id: str
    product: str
    wafer_count: int
    status: str
    start_time: str
    end_time: Optional[str] = None


class AlarmOut(BaseModel):
    """告警响应模型"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    machine_id: str
    timestamp: str
    alarm_code: str
    description: str
    level: str
    resolved: bool
    lot_id: Optional[str] = None


class AIQueryRequest(BaseModel):
    """AI 查询请求（旧版兼容）"""
    question: str
    machine_id: Optional[str] = None


class AIQueryResponse(BaseModel):
    """AI 查询响应（旧版兼容）"""
    answer: str
    sql: str
    jump_timestamp: Optional[str] = None


# ========== 新版统一AI接口 ==========

class AIChatRequest(BaseModel):
    """AI 聊天请求（统一接口）"""
    question: str
    session_id: Optional[str] = None
    machine_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None
    user_role: Optional[str] = "user"  # user / admin
    stream: Optional[bool] = False
    config_id: Optional[int] = None  # 指定使用的AI配置ID（None则使用默认配置）


class AITableData(BaseModel):
    """表格数据结构"""
    headers: List[str] = []
    rows: List[List[Any]] = []


class AIToolCall(BaseModel):
    """工具调用记录"""
    tool: str
    workflow: Optional[str] = None
    status: str  # success / failed / pending
    error: Optional[str] = None


class AISource(BaseModel):
    """参考来源"""
    type: str  # llm / dify / n8n / db
    model: Optional[str] = None
    app_id: Optional[str] = None
    workflow: Optional[str] = None


class AIChatResponse(BaseModel):
    """AI 聊天响应（统一接口）"""
    answer: str
    sql: Optional[str] = ""
    jump_timestamp: Optional[str] = None
    table_data: Optional[AITableData] = None
    tool_calls: Optional[List[AIToolCall]] = []
    sources: Optional[List[AISource]] = []
    session_id: Optional[str] = None
    provider: Optional[str] = None
    provider_name: Optional[str] = None
    model: Optional[str] = None
    config_id: Optional[int] = None
    usage: Optional[Dict[str, Any]] = None


class AIConfigUpdate(BaseModel):
    """AI 配置更新请求"""
    provider: Optional[str] = None  # local / openai / dify / hybrid / zhipu / deepseek / qwen / custom
    provider_name: Optional[str] = None  # 显示名称（如智谱GLM、OpenAI官方）
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    dify_enabled: Optional[bool] = None
    dify_base_url: Optional[str] = None
    dify_api_key: Optional[str] = None
    dify_app_id: Optional[str] = None
    n8n_enabled: Optional[bool] = None
    n8n_base_url: Optional[str] = None
    n8n_webhook_secret: Optional[str] = None


class AIConfigOut(BaseModel):
    """AI 配置输出（脱敏）"""
    provider: str
    provider_name: str
    model: str
    base_url_masked: str
    has_api_key: bool
    temperature: float
    max_tokens: int
    dify_enabled: bool
    dify_base_url_masked: str
    dify_app_id_masked: str
    n8n_enabled: bool
    n8n_base_url_masked: str


class AIConnectionTest(BaseModel):
    """连接测试请求"""
    provider_type: str  # openai / dify / n8n
    config: Dict[str, Any]


# ========== AI Provider 多配置管理 ==========

class AIProviderConfigIn(BaseModel):
    """AI Provider配置创建/更新请求"""
    name: str
    provider: str  # zhipu / openai / deepseek / qwen / custom / local
    base_url: Optional[str] = ""
    api_key: Optional[str] = ""
    model: Optional[str] = ""
    temperature: Optional[float] = 0.7
    max_tokens: Optional[int] = 2048
    is_enabled: Optional[bool] = True
    is_default: Optional[bool] = False
    description: Optional[str] = ""
    sort_order: Optional[int] = 0


class AIProviderConfigOut(BaseModel):
    """AI Provider配置响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    provider: str
    base_url: str
    has_api_key: bool  # 是否已设置api_key（不脱敏返回完整key）
    model: str
    temperature: float
    max_tokens: int
    is_enabled: bool
    is_default: bool
    sort_order: int
    description: str
    created_at: Optional[str] = ""
    updated_at: Optional[str] = ""


class AIProviderConfigUpdate(BaseModel):
    """AI Provider配置部分更新"""
    name: Optional[str] = None
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    is_enabled: Optional[bool] = None
    is_default: Optional[bool] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None


class AIUsageStats(BaseModel):
    """AI使用统计"""
    total_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    provider_breakdown: Dict[str, Dict[str, Any]]
    daily_stats: List[Dict[str, Any]]


class AIUsageLogOut(BaseModel):
    """AI使用日志响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: Optional[str] = ""
    config_id: Optional[int] = None
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    question_preview: str
    success: bool
    error_msg: Optional[str] = None
    created_at: str
