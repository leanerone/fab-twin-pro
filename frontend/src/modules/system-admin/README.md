# 模块④ 系统管理（system-admin）

- **负责人**：洪佳琪（过渡期）；后续归属待拍板
- **功能边界**：登录认证、用户与权限管理。

## 目录

```
frontend/
  pages/ LoginPage（/login）、UserManagementPage（/users）
```

后端对应（当前真实目录）：`backend/modules/system_admin/routes/auth.py`、
`backend/modules/system_admin/routes/users.py`；共享认证安全底座是 `backend/core/services/security.py`。
系统管理目前只有这两个模块路由文件，不要虚构模块 `services/`。
表 `users、roles、role_permissions、perm_data`。旧平铺 routers/services 与兼容 shim 已移除。

## 公开接口

- `/api/auth/login`、`/api/auth/login-password`、`/api/auth/me`、权限校验依赖 `get_current_user`
- `get_current_user` 被全部受保护路由依赖，物理上靠近内核，改签名影响全仓，须内核 review

## 自测

`npm run build`；登录（NT/账密两条路）、用户增删改、未授权 401/403 回归。
