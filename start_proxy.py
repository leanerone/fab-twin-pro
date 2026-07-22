"""FabTwin 一键代理服务器

功能：
1. 静态文件服务（前端 dist 目录）
2. API/WebSocket 反向代理到后端
3. 简单工号登录（替代 Windows NT 认证）

无需 IIS/Nginx，纯 Python 实现。

运行：
    backend\venv\Scripts\python.exe start_proxy.py
    或双击 start_proxy.bat
"""
import os
import sys
import json
import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
import threading
import time
from datetime import datetime, timedelta

# ============ 配置 ============
# Windows 普通用户无法绑定 80 端口，默认使用 8080
# 如需使用 80 端口，请以管理员身份运行，或设置环境变量 PROXY_PORT=80
PROXY_PORT = int(os.environ.get('PROXY_PORT', '8080'))
BACKEND_URL = "http://127.0.0.1:8002"   # 后端地址
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
COOKIE_NAME = "fabtwin_user"
COOKIE_MAX_AGE = 86400 * 7   # 7天

# 模拟用户数据库（实际应从 Oracle DB 读取）
# key: 工号, value: {name, roles}
USER_DB = {
    "admin": {"name": "管理员", "roles": ["admin", "engineer", "user"]},
    "engineer": {"name": "工程师", "roles": ["engineer", "user"]},
    "user": {"name": "普通用户", "roles": ["user"]},
}

def get_user_from_cookie(headers):
    """从 Cookie 解析用户"""
    cookie = headers.get('Cookie', '')
    for part in cookie.split(';'):
        part = part.strip()
        if part.startswith(f'{COOKIE_NAME}='):
            try:
                user_data = json.loads(urllib.parse.unquote(part.split('=', 1)[1]))
                return user_data
            except:
                pass
    return None

def set_user_cookie(user_id, user_info):
    """生成用户 Cookie"""
    data = json.dumps({
        "id": user_id,
        "name": user_info["name"],
        "roles": user_info["roles"],
    })
    return f"{COOKIE_NAME}={urllib.parse.quote(data)}; Path=/; Max-Age={COOKIE_MAX_AGE}; HttpOnly"

# ============ 登录页面 HTML ============
LOGIN_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>FabTwin - 工号登录</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: 'Segoe UI', system-ui, sans-serif;
  background: #0a0e1a;
  color: #e0e6ed;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
}
.login-box {
  background: #141a2a;
  border: 1px solid #2a3142;
  border-radius: 12px;
  padding: 40px 36px;
  width: 100%;
  max-width: 380px;
  text-align: center;
}
.logo { font-size: 28px; font-weight: 700; color: #00d4ff; margin-bottom: 8px; }
.subtitle { font-size: 13px; color: #64748b; margin-bottom: 28px; }
.input-group { margin-bottom: 16px; text-align: left; }
.input-group label { display: block; font-size: 12px; color: #94a3b8; margin-bottom: 6px; }
.input-group input {
  width: 100%;
  background: #0f1419;
  border: 1px solid #2a3142;
  color: #e0e6ed;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 14px;
  outline: none;
}
.input-group input:focus { border-color: #00d4ff; }
.btn {
  width: 100%;
  background: #00d4ff;
  color: #000;
  border: none;
  padding: 12px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  margin-top: 8px;
}
.btn:hover { opacity: 0.85; }
.error { color: #ef4444; font-size: 12px; margin-top: 12px; }
.hint { color: #475569; font-size: 11px; margin-top: 16px; }
</style>
</head>
<body>
<div class="login-box">
  <div class="logo">FabTwin</div>
  <div class="subtitle">晶圆厂数字孪生平台</div>
  <form method="POST" action="/api/auth/login">
    <div class="input-group">
      <label>工号 / 账号</label>
      <input type="text" name="username" placeholder="请输入工号" required autofocus>
    </div>
    <div class="input-group">
      <label>密码</label>
      <input type="password" name="password" placeholder="默认密码同账号" value="">
    </div>
    <button type="submit" class="btn">登录</button>
    <div class="hint">默认账号: admin / engineer / user，密码同账号</div>
  </form>
</div>
</body>
</html>"""

# ============ 代理 Handler ============
class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    """处理请求：静态文件或反向代理到后端"""

    def do_GET(self):
        path = self.path

        # API/WebSocket 请求转发到后端
        if path.startswith('/api/') or path.startswith('/ws/'):
            self._proxy_to_backend()
            return

        # 静态文件服务
        self.serve_static(path)

    def do_POST(self):
        path = self.path

        # 处理登录请求
        if path == '/api/auth/login':
            self._handle_login()
            return

        # 其他 POST 请求转发到后端
        if path.startswith('/api/') or path.startswith('/ws/'):
            self._proxy_to_backend()
            return

        self.send_error(404)

    def do_PUT(self):
        if self.path.startswith('/api/') or self.path.startswith('/ws/'):
            self._proxy_to_backend()
            return
        self.send_error(404)

    def do_DELETE(self):
        if self.path.startswith('/api/') or self.path.startswith('/ws/'):
            self._proxy_to_backend()
            return
        self.send_error(404)

    def do_OPTIONS(self):
        if self.path.startswith('/api/') or self.path.startswith('/ws/'):
            self._proxy_to_backend()
            return
        self.send_error(404)

    def _handle_login(self):
        """处理工号登录"""
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length).decode('utf-8')
        params = urllib.parse.parse_qs(post_data)

        username = params.get('username', [''])[0].strip()
        password = params.get('password', [''])[0].strip()

        # 简单认证：检查工号是否存在，密码默认同工号（或 admin123）
        if username in USER_DB:
            # 允许默认密码：同账号 或 admin123
            if password == username or password == 'admin123' or password == '':
                user_info = USER_DB[username]
                cookie = set_user_cookie(username, user_info)
                self.send_response(302)
                self.send_header('Location', '/')
                self.send_header('Set-Cookie', cookie)
                self.end_headers()
                return

        # 登录失败
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        html = LOGIN_HTML.replace(
            '<div class="hint">',
            '<div class="error">工号或密码错误</div><div class="hint">'
        )
        self.wfile.write(html.encode('utf-8'))

    def _proxy_to_backend(self):
        """反向代理到后端"""
        url = BACKEND_URL + self.path

        # 读取请求体
        body = None
        content_length = self.headers.get('Content-Length')
        if content_length:
            body = self.rfile.read(int(content_length))

        # 构建请求头
        headers = {}
        for key, value in self.headers.items():
            if key.lower() not in ('host', 'content-length'):
                headers[key] = value

        # 添加用户认证头（从 Cookie 读取）
        user = get_user_from_cookie(self.headers)
        if user:
            headers['X-User-Id'] = user.get('id', '')
            headers['X-User-Name'] = urllib.parse.quote(user.get('name', ''))
            headers['X-User-Roles'] = ','.join(user.get('roles', []))

        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers=headers,
                method=self.command,
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                self.send_response(resp.status)
                for key, value in resp.headers.items():
                    if key.lower() not in ('transfer-encoding', 'content-length', 'connection'):
                        self.send_header(key, value)
                self.send_header('Content-Length', len(resp.read()))
                self.end_headers()
                self.wfile.write(resp.read())
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, value in e.headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            print(f"[PROXY] 错误: {e}")
            self.send_error(502, f"后端连接失败: {e}")

    def serve_static(self, path):
        """提供静态文件"""
        # 检查是否已登录（除登录页外）
        user = get_user_from_cookie(self.headers)
        if not user and path not in ('/login', '/favicon.ico'):
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(LOGIN_HTML.encode('utf-8'))
            return

        # 默认 index.html
        if path == '/' or path == '/index.html':
            filepath = os.path.join(FRONTEND_DIR, 'index.html')
        else:
            # 去除开头的 /
            filepath = os.path.join(FRONTEND_DIR, path.lstrip('/'))

        if os.path.exists(filepath) and os.path.isfile(filepath):
            self.send_response(200)
            # 根据扩展名设置 Content-Type
            ext = os.path.splitext(filepath)[1].lower()
            mime_types = {
                '.html': 'text/html',
                '.js': 'application/javascript',
                '.css': 'text/css',
                '.json': 'application/json',
                '.png': 'image/png',
                '.jpg': 'image/jpeg',
                '.jpeg': 'image/jpeg',
                '.gif': 'image/gif',
                '.svg': 'image/svg+xml',
                '.ico': 'image/x-icon',
                '.woff': 'font/woff',
                '.woff2': 'font/woff2',
            }
            self.send_header('Content-Type', mime_types.get(ext, 'application/octet-stream'))
            self.end_headers()
            with open(filepath, 'rb') as f:
                self.wfile.write(f.read())
        else:
            # SPA 路由回退：返回 index.html
            index_path = os.path.join(FRONTEND_DIR, 'index.html')
            if os.path.exists(index_path):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                with open(index_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, f"文件不存在: {path}")

    def log_message(self, format, *args):
        """自定义日志"""
        print(f"[PROXY] {self.address_string()} - {format % args}")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """多线程 HTTP 服务器"""
    allow_reuse_address = True
    daemon_threads = True


def main():
    print("=" * 60)
    print("FabTwin 一键代理服务器")
    print("=" * 60)
    print(f"代理端口: {PROXY_PORT}")
    print(f"后端地址: {BACKEND_URL}")
    print(f"前端目录: {FRONTEND_DIR}")
    print(f"访问地址: http://服务器IP:{PROXY_PORT}")
    print("=" * 60)

    if not os.path.exists(FRONTEND_DIR):
        print(f"[错误] 前端目录不存在: {FRONTEND_DIR}")
        print("[提示] 请先运行 'npm run build' 构建前端")
        sys.exit(1)

    try:
        server = ThreadedHTTPServer(('0.0.0.0', PROXY_PORT), ProxyHandler)
    except PermissionError as e:
        print(f"[错误] 无法绑定端口 {PROXY_PORT}：{e}")
        print("[提示] 80 端口需要管理员权限，或修改环境变量 PROXY_PORT=8080")
        sys.exit(1)
    print("[启动] 代理服务器运行中...")
    print("[提示] 按 Ctrl+C 停止")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[停止] 关闭代理服务器...")
        server.shutdown()


if __name__ == '__main__':
    main()