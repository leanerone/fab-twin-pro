# -*- coding: utf-8 -*-
"""跨域 FastAPI 依赖：收拢原 machines/models/uploads 三处相同的 require_model_edit。"""
from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from models import User
from routers.auth import get_current_user, check_permission


def require_model_edit(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """要求当前用户拥有 model_edit 权限（管理员）"""
    if not check_permission(user, "model_edit", db):
        raise HTTPException(status_code=403, detail="无权限：需要 model_edit 权限")
    return user
