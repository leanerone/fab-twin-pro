# Windows Server IIS + Windows 认证部署指南

> **注意**：本文档为早期方案设计文档。实际部署方案已改为 **ASP 桥接模式**，详见 [deploy-sop.md](deploy-sop.md) 第 6.1 节。
> 当前方案使用 `deploy_iis_nt_final.bat` 一键部署，核心文件为 `get_user.asp` + `web.config`。

## 问题说明

IIS 反向代理无法直接将 Windows 认证信息传递给独立运行的 Python 后端进程。
早期方案使用 `$env:USERNAME` 获取的是服务器运行账号，而非客户端访问者账号。

## 最终方案：ASP 桥接

```
用户浏览器 (同事电脑)
      │
      ▼ 访问 /get_user.asp
┌─────────────────────────────────────┐
│         IIS (端口 80)                │
│  - get_user.asp: 仅 Windows 认证     │
│  - 其他文件: 匿名访问                │
│  - 返回: {"username":"DOMAIN\\工号"} │
└─────────────────────────────────────┘
      │
      ▼ 前端拿到用户名
┌─────────────────────────────────────┐
│  前端 Login.vue                      │
│  - 调用 /api/auth/login-windows      │
│  - 传入 ASP 返回的用户名              │
└─────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│  后端 auth.py /login-windows         │
│  - 创建/更新用户会话                  │
│  - 返回 token + 权限                  │
└─────────────────────────────────────┘
```

### 核心文件

1. **get_user.asp** - ASP 桥接文件，读取 `LOGON_USER` 返回 JSON
2. **web.config** - IIS 配置（仅 rewrite rules，不含 authentication）
3. **deploy_iis_nt_final.bat** - 部署脚本，用 appcmd 配置文件级别认证
4. **frontend/src/views/Login.vue** - 前端登录逻辑
5. **backend/routers/auth.py** - 后端 `/login-windows` 接口

## 解决方案：IIS 反向代理 + Windows 认证

### 架构图

```
用户浏览器 (同事电脑)
      │
      ▼ NTLM/Kerberos 认证
┌─────────────────────────────────────┐
│         IIS (端口 80/443)            │
│  - Windows Authentication 启用      │
│  - 注入请求头: REMOTE_USER           │
│  - 反向代理到 http://localhost:8002 │
└─────────────────────────────────────┘
      │
      ▼
┌─────────────────────────────────────┐
│    Uvicorn/FastAPI (端口 8000)       │
│  - 读取 X-Forwarded-User 头部       │
│  - 不处理认证，信任 IIS             │
└─────────────────────────────────────┘
```

### 步骤 1：安装 IIS 和相关模块

```powershell
# 以管理员身份运行

# 安装 IIS
Install-WindowsFeature -name Web-Server -IncludeManagementTools

# 安装 URL Rewrite 模块（用于反向代理）
# 下载：https://www.iis.net/downloads/microsoft/url-rewrite
# 或使用 Web Platform Installer

# 安装 Application Request Routing (ARR)
# 下载：https://www.iis.net/downloads/microsoft/application-request-routing-version-2
```

### 步骤 2：配置 IIS 站点

```xml
<!-- C:\inetpub\wwwroot\FabTwin\web.config -->
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
  <system.webServer>
    <security>
      <authentication>
        <!-- 禁用匿名访问，启用 Windows 认证 -->
        <anonymousAuthentication enabled="false" />
        <windowsAuthentication enabled="true">
          <providers>
            <add value="Negotiate" />
            <add value="NTLM" />
          </providers>
        </windowsAuthentication>
      </authentication>
    </security>
    
    <!-- URL Rewrite 规则：代理到后端 -->
    <rewrite>
      <rules>
        <rule name="ReverseProxyInboundRule" stopProcessing="true">
          <match url="(.*)" />
          <action type="Rewrite" url="http://localhost:8002/{R:1}" />
          <serverVariables>
            <!-- 将认证用户传递给后端 -->
            <set name="HTTP_X_FORWARDED_USER" value="{REMOTE_USER}" />
          </serverVariables>
        </rule>
      </rules>
    </rewrite>
  </system.webServer>
</configuration>
```

### 步骤 3：修改后端认证逻辑

```python
# backend/routers/auth.py

from fastapi import Header, HTTPException
from typing import Optional

# 禁用原来的 NT 认证检测，改为读取 IIS 传递的头部
def get_current_user(
    x_forwarded_user: Optional[str] = Header(None, alias="X-Forwarded-User"),
    authorization: Optional[str] = Header(None),
) -> dict:
    """
    从 IIS 传递的头部获取用户身份
    
    IIS Windows Authentication 会注入:
    - X-Forwarded-User: DOMAIN\username (来自 REMOTE_USER)
    """
    
    # 优先使用 IIS Windows 认证
    if x_forwarded_user:
        # 格式: DOMAIN\username 或 username@domain.com
        parts = x_forwarded_user.split('\\')
        if len(parts) == 2:
            domain, username = parts
        else:
            username = x_forwarded_user
            domain = "DEFAULT"
        
        return {
            "username": username,
            "domain": domain,
            "auth_method": "windows",
            "roles": get_user_roles(username),  # 从 DB 查询角色
        }
    
    # 回退：Bearer Token 认证（用于 API 调用）
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        return verify_jwt_token(token)
    
    # 回退：管理员登录（账号密码）
    # 已有逻辑...
    
    # 未认证
    raise HTTPException(status_code=401, detail="未登录")


def get_user_roles(username: str) -> list:
    """从数据库查询用户角色"""
    # 这里需要查询 USER_ROLES 表或 AD 组
    # 示例：
    if username.lower() == "admin":
        return ["admin", "engineer", "user"]
    elif username in ENGINEER_USERS:
        return ["engineer", "user"]
    else:
        return ["user"]
```

### 步骤 4：Active Directory 集成（可选）

如果要根据 AD 组分配角色：

```python
import ldap3

def get_ad_groups(username: str, password: str = None) -> list:
    """查询用户所属的 AD 组"""
    
    # AD 服务器配置
    AD_SERVER = "ldap://your-ad-server"
    AD_DOMAIN = "YOURDOMAIN"
    AD_BASE_DN = "DC=yourcompany,DC=com"
    
    # 连接 AD
    server = ldap3.Server(AD_SERVER)
    conn = ldap3.Connection(server)
    
    if not conn.bind():
        return []
    
    # 搜索用户
    search_filter = f"(sAMAccountName={username})"
    conn.search(
        search_base=AD_BASE_DN,
        search_filter=search_filter,
        attributes=["memberOf"]
    )
    
    if not conn.entries:
        return []
    
    # 解析组名
    groups = []
    for entry in conn.entries:
        for group_dn in entry.memberOf.values:
            # 提取组名: CN=FabTwinAdmins,OU=Groups,DC=...
            group_name = group_dn.split(',')[0].replace('CN=', '')
            groups.append(group_name)
    
    return groups
```

### 步骤 5：前端自动登录

```javascript
// frontend/src/stores/auth.js

export const useAuthStore = defineStore('auth', {
  state: () => ({
    user: null,
    token: null,
  }),
  
  actions: {
    async checkWindowsAuth() {
      try {
        // 访问需要 Windows 认证的端点
        // IIS 会自动处理 NTLM 握手
        const res = await fetch('/api/auth/windows', {
          credentials: 'include',  // 发送 Windows 凭据
        })
        
        if (res.ok) {
          const data = await res.json()
          this.user = data.user
          this.token = data.token
          return true
        }
      } catch (e) {
        console.error('Windows auth failed:', e)
      }
      return false
    },
    
    async login(username, password) {
      // 管理员登录（账号密码模式）
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password }),
      })
      
      if (res.ok) {
        const data = await res.json()
        this.user = data.user
        this.token = data.token
        return true
      }
      return false
    }
  }
})
```

### 步骤 6：部署后启动

```powershell
# 1. 启动后端（不需要修改）
cd E:\HJQ\deploy\fab-twin-pro
.\start_prod.bat

# 2. IIS 会自动监听 80 端口，代理到 8002

# 3. 用户访问
http://your-server/FabTwin

# 4. 浏览器自动弹出 Windows 凭据框（或静默使用当前登录用户）
```

### 故障排查

```powershell
# 检查 IIS 认证配置
Get-WebConfigurationProperty -Filter /system.webServer/security/authentication/windowsAuthentication -Name enabled -Location "Default Web Site/FabTwin"

# 查看日志
Get-Content C:\inetpub\logs\LogFiles\W3SVC1\*.log -Tail 50

# 测试认证
Invoke-WebRequest -Uri "http://localhost/FabTwin/api/auth/me" -UseDefaultCredentials
```

## 替代方案：无 IIS 的 NTLM 认证

如果不想使用 IIS，可以在后端直接处理 NTLM：

```python
# 需要安装: pip install python-ntlm

from ntlm import ntlm

# 但这种方式更复杂，且需要浏览器支持 NTLM 握手
# 推荐使用 IIS 方案
```