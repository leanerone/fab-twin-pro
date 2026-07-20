"""用户/角色/权限管理API（admin专用）"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from database import get_db
from models import User, Role, Permission, RolePermission
from routers.auth import get_current_user, check_permission

router = APIRouter(prefix="/api", tags=["users"])


def require_user_manage(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """要求当前用户拥有 user_manage 权限"""
    if not check_permission(user, "user_manage", db):
        raise HTTPException(status_code=403, detail="无权限：需要 user_manage 权限")
    return user


def _user_to_dict(user: User, db: Session = None) -> dict:
    """将User对象转为字典"""
    result = {
        "id": user.id,
        "username": user.username,
        "display_name": user.display_name,
        "email": user.email or "",
        "department": user.department or "",
        "role": user.role,
        "windows_sid": user.windows_sid or "",
        "last_login_at": user.last_login_at or "",
        "created_at": user.created_at or "",
        "updated_at": user.updated_at or "",
    }
    if db:
        perms = get_user_permissions_safe(user, db)
        result["permissions"] = perms
    return result


def get_user_permissions_safe(user: User, db: Session) -> list:
    """获取用户权限（基于角色）"""
    if user.role == "admin":
        return ["*"]
    try:
        role_perms = db.query(RolePermission).filter(RolePermission.role_id == user.role).all()
        return [rp.permission_id for rp in role_perms]
    except Exception:
        return []


# ============================================
# 用户管理
# ============================================

class UserCreateRequest(BaseModel):
    username: str
    display_name: str
    email: str = ""
    department: str = ""
    role: str = "user"
    password: str = ""  # 可选，默认 username + "123"


class UserUpdateRequest(BaseModel):
    display_name: str | None = None
    email: str | None = None
    department: str | None = None
    role: str | None = None


class PasswordResetRequest(BaseModel):
    new_password: str


@router.get("/users")
def list_users(
    keyword: str = Query("", description="搜索用户名/显示名/邮箱"),
    role: str = Query("", description="按角色筛选"),
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """获取用户列表（支持关键字和角色筛选）"""
    q = db.query(User)
    if keyword:
        kw = f"%{keyword}%"
        q = q.filter(
            (User.username.like(kw)) |
            (User.display_name.like(kw)) |
            (User.email.like(kw))
        )
    if role:
        q = q.filter(User.role == role)
    users = q.order_by(User.created_at.desc()).all()
    return {"users": [_user_to_dict(u, db) for u in users], "total": len(users)}


@router.post("/users")
def create_user(
    data: UserCreateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_user_manage),
):
    """新增用户"""
    if db.query(User).filter(User.username == data.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    if data.role not in ("admin", "engineer", "user"):
        raise HTTPException(status_code=400, detail="角色必须是 admin/engineer/user 之一")

    now = datetime.now().isoformat()
    user = User(
        id=str(uuid.uuid4()),
        username=data.username,
        display_name=data.display_name,
        email=data.email,
        department=data.department,
        role=data.role,
        windows_sid="",
        last_login_at="",
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user": _user_to_dict(user, db), "message": "用户创建成功"}


@router.get("/users/{user_id}")
def get_user_detail(
    user_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """获取用户详情"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return {"user": _user_to_dict(user, db)}


@router.put("/users/{user_id}")
def update_user(
    user_id: str,
    data: UserUpdateRequest,
    db: Session = Depends(get_db),
    current: User = Depends(require_user_manage),
):
    """编辑用户（不含密码）"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if data.role is not None and data.role not in ("admin", "engineer", "user"):
        raise HTTPException(status_code=400, detail="角色必须是 admin/engineer/user 之一")

    if data.display_name is not None:
        user.display_name = data.display_name
    if data.email is not None:
        user.email = data.email
    if data.department is not None:
        user.department = data.department
    if data.role is not None:
        user.role = data.role
    user.updated_at = datetime.now().isoformat()

    db.commit()
    db.refresh(user)
    return {"user": _user_to_dict(user, db), "message": "更新成功"}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: str,
    db: Session = Depends(get_db),
    current: User = Depends(require_user_manage),
):
    """删除用户（禁止删除自己和admin用户）"""
    if current.id == user_id:
        raise HTTPException(status_code=400, detail="不能删除当前登录用户")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    if user.username == "admin":
        raise HTTPException(status_code=400, detail="不能删除内置 admin 用户")

    db.delete(user)
    db.commit()
    return {"message": f"用户 {user.username} 已删除"}


@router.put("/users/{user_id}/password")
def reset_password(
    user_id: str,
    data: PasswordResetRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """重置用户密码

    说明：当前系统密码规则为 username + "123"，自定义密码暂未启用 hash
    生产环境建议引入 passlib + bcrypt
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # TODO: 引入 password_hash 字段后，存储 hash 而非明文
    # 当前仅记录操作，密码规则保持原样
    user.updated_at = datetime.now().isoformat()
    db.commit()
    return {"message": f"用户 {user.username} 密码已重置（新密码规则：用户名+123）"}


# ============================================
# 角色管理
# ============================================

class RoleCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ""


class RoleUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None


class RolePermissionsRequest(BaseModel):
    permission_ids: list[str]


@router.get("/roles")
def list_roles(
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """获取所有角色"""
    roles = db.query(Role).all()
    result = []
    for r in roles:
        perm_count = db.query(RolePermission).filter(RolePermission.role_id == r.id).count()
        result.append({
            "id": r.id,
            "name": r.name,
            "description": r.description or "",
            "permission_count": perm_count,
        })
    return {"roles": result}


@router.post("/roles")
def create_role(
    data: RoleCreateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """新增角色"""
    if db.query(Role).filter(Role.id == data.id).first():
        raise HTTPException(status_code=400, detail="角色ID已存在")
    role = Role(id=data.id, name=data.name, description=data.description)
    db.add(role)
    db.commit()
    db.refresh(role)
    return {"role": {"id": role.id, "name": role.name, "description": role.description}}


@router.put("/roles/{role_id}")
def update_role(
    role_id: str,
    data: RoleUpdateRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """编辑角色"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if data.name is not None:
        role.name = data.name
    if data.description is not None:
        role.description = data.description
    db.commit()
    db.refresh(role)
    return {"role": {"id": role.id, "name": role.name, "description": role.description}}


@router.delete("/roles/{role_id}")
def delete_role(
    role_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """删除角色（admin/engineer/user 三个内置角色禁删）"""
    if role_id in ("admin", "engineer", "user"):
        raise HTTPException(status_code=400, detail="不能删除内置角色")

    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    user_count = db.query(User).filter(User.role == role_id).count()
    if user_count > 0:
        raise HTTPException(status_code=400, detail=f"该角色下还有 {user_count} 个用户，无法删除")

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    db.delete(role)
    db.commit()
    return {"message": f"角色 {role.name} 已删除"}


@router.get("/roles/{role_id}/permissions")
def get_role_permissions(
    role_id: str,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """获取角色拥有的权限列表"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    perms = db.query(RolePermission).filter(RolePermission.role_id == role_id).all()
    perm_ids = [rp.permission_id for rp in perms]
    return {"role_id": role_id, "permission_ids": perm_ids}


@router.put("/roles/{role_id}/permissions")
def update_role_permissions(
    role_id: str,
    data: RolePermissionsRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """批量更新角色权限（覆盖式）"""
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    if role_id == "admin":
        raise HTTPException(status_code=400, detail="admin 角色拥有全部权限，不可修改")

    db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
    for perm_id in data.permission_ids:
        if db.query(Permission).filter(Permission.id == perm_id).first():
            db.add(RolePermission(role_id=role_id, permission_id=perm_id))
    db.commit()
    return {"role_id": role_id, "permission_ids": data.permission_ids, "message": "权限更新成功"}


# ============================================
# 权限管理
# ============================================

class PermissionCreateRequest(BaseModel):
    id: str
    name: str
    description: str = ""
    resource: str = ""
    action: str = ""


@router.get("/permissions")
def list_permissions_all(
    db: Session = Depends(get_db),
    _: User = Depends(require_user_manage),
):
    """获取所有权限列表（含角色分配情况）"""
    perms = db.query(Permission).all()
    result = []
    for p in perms:
        role_count = db.query(RolePermission).filter(RolePermission.permission_id == p.id).count()
        result.append({
            "id": p.id,
            "name": p.name,
            "description": p.description or "",
            "resource": p.resource or "",
            "action": p.action or "",
            "role_count": role_count,
        })
    return {"permissions": result}
