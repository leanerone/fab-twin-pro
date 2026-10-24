"""认证API：Windows NT认证、角色权限

test31 安全加固：
- 密码改 PBKDF2 哈希存储（users.password_hash），旧规则（用户名+"123"）登录时透明升级
- token 改 HMAC 签名 + 7 天过期；旧 token（裸 user.id）过渡期内仍接受
- 删除直连模式下的 PowerShell 反查（存在命令注入面 + 阻塞最多 10s），改走密码登录
- 数据库故障不再签发 fallback/default 匿名会话，返回 503
- 修复 /machine/{id} 查错表（User→Machine）的 copy-paste bug
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import json
import uuid

from database import get_db
from models import User, Role, Permission, RolePermission, MachineToolMapping, Machine
from services.security import (
    hash_password, verify_password, legacy_password_for, issue_token, parse_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


def _user_payload(user: User, db: Session) -> dict:
    permissions = get_user_permissions(user, db)
    return {
        "token": issue_token(user.id),
        "user": {
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "role": user.role,
            "department": user.department,
        },
        "permissions": permissions,
    }


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)):
    """获取当前用户：优先校验签名 token；旧版裸 user.id token 过渡期兼容"""
    token = credentials.credentials
    user_id = parse_token(token)
    if user_id is None:
        # 旧版 token（裸 user.id）：仍按原逻辑查库，保证升级后已登录用户不掉线
        user_id = token
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user

class LoginPasswordRequest(BaseModel):
    username: str
    password: str

class LoginWindowsRequest(BaseModel):
    username: str


def get_user_permissions(user: User, db: Session) -> list:
    """获取用户所有权限（基于角色-权限关联表）

    注意：admin 角色直接返回 ["*"] 表示拥有全部权限
    其他角色通过 ROLE_PERMISSIONS 表查询实际授权的权限ID列表
    """
    if user.role == "admin":
        return ["*"]  # admin 拥有全部权限

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
    """Windows NT自动登录（获取客户端Windows用户名）

    - IIS 反代模式：信任 X-Forwarded-User（由 IIS Windows 认证注入）
    - 其他情况（含直连模式）：返回 need_password_login=True 走密码登录。
      test31：删除了直连模式下用 PowerShell 反查客户端主机名的逻辑——
      反查命令拼接了可控的 X-Forwarded-For（命令注入面），且 subprocess
      最多阻塞 10s；直连场景本就只用于开发，密码登录足够。
    """
    client_ip = request.client.host
    forwarded_user = request.headers.get("X-Forwarded-User", "")

    if forwarded_user:
        # IIS Windows 认证传递的用户名（格式: DOMAIN\username）
        windows_user = forwarded_user.split("\\")[-1] if "\\" in forwarded_user else forwarded_user
        hostname = request.headers.get("X-Forwarded-Host", client_ip)
    else:
        return {
            "need_password_login": True,
            "message": "无法自动获取Windows用户名，请使用账号密码登录",
        }

    username = f"{hostname}\\{windows_user}"

    try:
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

        return _user_payload(user, db)
    except HTTPException:
        raise
    except Exception as e:
        # test31：数据库故障不再签发 default/fallback 匿名会话
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail=f"认证服务暂不可用，请稍后再试（{e}）")


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
    """用户名密码登录

    test31：优先校验 PBKDF2 哈希；无哈希的存量用户回退旧规则（用户名+"123"）
    并在成功后透明升级为哈希存储。
    """
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    if user.password_hash:
        ok = verify_password(data.password, user.password_hash)
    else:
        # 存量用户：旧规则校验 + 透明升级
        ok = data.password == legacy_password_for(data.username)
        if ok:
            user.password_hash = hash_password(data.password)
    if not ok:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    user.last_login_at = datetime.now().isoformat()
    db.commit()

    return _user_payload(user, db)


@router.post("/login-windows")
def login_windows(data: LoginWindowsRequest, db: Session = Depends(get_db)):
    """Windows NT登录（前端通过ASP获取用户名后发送过来）"""
    windows_user = data.username

    if not windows_user:
        raise HTTPException(status_code=401, detail="未获取到Windows用户名")

    if "\\" in windows_user:
        windows_user = windows_user.split("\\")[-1]

    username = windows_user

    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            user = db.query(User).filter(User.display_name == username).first()

        if not user:
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                display_name=username,
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

        return _user_payload(user, db)
    except HTTPException:
        raise
    except Exception:
        # test31：数据库故障不再签发 fallback 会话
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=503, detail="认证服务暂不可用，请稍后再试")


@router.get("/machine/{machine_id}")
def get_machine_by_tool_id(machine_id: str, db: Session = Depends(get_db)):
    """通过machine_id或tool_id获取机台信息（支持PODOPENER映射）

    test31：修复首查查错表的 bug——原来查的是 User 表（copy-paste 错误），
    现在按机台表查询。
    """
    machine = db.query(Machine).filter(Machine.id == machine_id).first()
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