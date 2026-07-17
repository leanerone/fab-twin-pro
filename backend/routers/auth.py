"""认证API：Windows NT认证、角色权限"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import json
import uuid

from database import get_db
from models import User, Role, Permission, RolePermission, MachineToolMapping

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()

class LoginPasswordRequest(BaseModel):
    username: str
    password: str


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """获取当前用户"""
    token = credentials.credentials
    user = db.query(User).filter(User.id == token).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user


def get_user_permissions(user: User, db: Session) -> list:
    """获取用户所有权限"""
    if user.role == "admin":
        return ["*"]  # admin 拥有全部权限
    
    try:
        permissions = db.query(Permission).all()
        if permissions:
            return [p.id for p in permissions]
    except Exception:
        pass
    
    try:
        role_permissions = db.query(RolePermission).filter(RolePermission.role_id == user.role).all()
        permission_ids = [rp.permission_id for rp in role_permissions]
        return permission_ids
    except Exception:
        return []


def check_permission(user: User, permission_id: str, db: Session) -> bool:
    """检查用户是否有指定权限"""
    if user.role == "admin":
        return True
    permissions = get_user_permissions(user, db)
    return permission_id in permissions


@router.post("/login")
def login(request: Request, db: Session = Depends(get_db)):
    """Windows NT自动登录（获取客户端Windows用户名）"""
    try:
        client_ip = request.client.host
        from subprocess import check_output, CalledProcessError
        try:
            result = check_output(["powershell", "-Command", 
                f"([System.Net.Dns]::GetHostEntry('{client_ip}')).HostName"], 
                timeout=5).decode('utf-8').strip()
            hostname = result.split('.')[0]
        except (CalledProcessError, TimeoutError):
            hostname = "UNKNOWN"
        
        try:
            result = check_output(["powershell", "-Command", 
                "$env:USERNAME"], timeout=5).decode('utf-8').strip()
            windows_user = result
        except (CalledProcessError, TimeoutError):
            windows_user = "guest"
        
        username = f"{hostname}\\{windows_user}"
        
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = db.query(User).filter(User.username == windows_user).first()
        
        if not user:
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                display_name=windows_user,
                email="",
                department="",
                role="user",
                windows_sid="",
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )
            db.add(user)
            db.commit()
            db.refresh(user)
        
        user.last_login_at = datetime.now().isoformat()
        db.commit()
        
        permissions = get_user_permissions(user, db)
        
        return {
            "token": user.id,
            "user": {
                "id": user.id,
                "username": user.username,
                "display_name": user.display_name,
                "role": user.role,
                "department": user.department,
            },
            "permissions": permissions,
        }
    except Exception as e:
        user = db.query(User).filter(User.username == "default").first()
        if user:
            permissions = get_user_permissions(user, db)
            return {
                "token": user.id,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "display_name": user.display_name,
                    "role": user.role,
                    "department": user.department,
                },
                "permissions": permissions,
            }
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/user")
def get_user_info(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """获取当前用户信息"""
    permissions = get_user_permissions(user, db)
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "department": user.department,
        },
        "permissions": permissions,
    }


@router.get("/permissions")
def list_permissions(db: Session = Depends(get_db)):
    """获取所有权限列表"""
    permissions = db.query(Permission).all()
    return {"permissions": [{"id": p.id, "name": p.name, "description": p.description, 
                            "resource": p.resource, "action": p.action} for p in permissions]}


@router.get("/check/{permission_id}")
def check_user_permission(permission_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """检查用户权限"""
    has_perm = check_permission(user, permission_id, db)
    return {"permission_id": permission_id, "allowed": has_perm}


@router.post("/login-password")
def login_with_password(data: LoginPasswordRequest, db: Session = Depends(get_db)):
    """用户名密码登录"""
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    # 简单密码验证（生产环境应使用哈希）
    expected_password = data.username + "123"
    if data.password != expected_password:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    
    user.last_login_at = datetime.now().isoformat()
    db.commit()
    
    permissions = get_user_permissions(user, db)
    
    return {
        "token": user.id,
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "department": user.department,
        },
        "permissions": permissions,
    }


@router.get("/machine/{machine_id}")
def get_machine_by_tool_id(machine_id: str, db: Session = Depends(get_db)):
    """通过machine_id或tool_id获取机台信息（支持PODOPENER映射）"""
    machine = db.query(User).filter(User.id == machine_id).first()
    if machine:
        return {"machine_id": machine.id, "tool_id": machine_id}
    
    mapping = db.query(MachineToolMapping).filter(
        (MachineToolMapping.machine_id == machine_id) | 
        (MachineToolMapping.tool_id == machine_id)
    ).first()
    
    if mapping:
        if mapping.machine_id == machine_id:
            return {"machine_id": machine_id, "tool_id": mapping.tool_id}
        else:
            return {"machine_id": mapping.machine_id, "tool_id": machine_id}
    
    return {"machine_id": machine_id, "tool_id": machine_id}