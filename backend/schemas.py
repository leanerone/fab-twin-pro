"""Pydantic 请求/响应模型"""
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


class MachineOut(BaseModel):
    """机台响应模型"""
    model_config = ConfigDict(from_attributes=True)

    id: str
    model: str
    name: str
    line: int
    chamber_count: int
    process_type: str
    state: str
    temp: float
    pressure: float
    gas_flow: float
    rf_power: float
    wafer_count: int
    alarm_count: int
    process_step: int
    has_smif: bool
    updated_at: str


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
    """AI 查询请求"""
    question: str
    machine_id: Optional[str] = None


class AIQueryResponse(BaseModel):
    """AI 查询响应"""
    answer: str
    sql: str
    jump_timestamp: Optional[str] = None
