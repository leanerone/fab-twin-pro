"""FabTwin 一键代理服务器

功能：
1. 静态文件服务（前端 dist 目录）
2. API/WebSocket 反向代理到后端
3. 支持前端账号密码登录

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

PROXY_PORT = int(os.environ.get('PROXY_PORT', '8080'))
BACKEND_URL = "http://127.0.0.1:8002"
FRONTEND_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")


class ProxyHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        path = self.path

        if path.startswith('/api/') or path.startswith('/ws/'):
            self._proxy_to_backend()
            return

        self.serve_static(path)

    def do_POST(self):
        path = self.path

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
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def _proxy_to_backend(self):
        url = BACKEND_URL + self.path

        body = None
        content_length = self.headers.get('Content-Length')
        if content_length:
            body = self.rfile.read(int(content_length))

        headers = {}
        for key, value in self.headers.items():
            if key.lower() not in ('host', 'content-length'):
                headers[key] = value

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
                content = resp.read()
                self.send_header('Content-Length', len(content))
                self.end_headers()
                self.wfile.write(content)
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            for key, value in e.headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(e.read())
        except Exception as e:
            print(f"[PROXY] Error: {e}")
            self.send_error(502, f"Backend connection failed: {e}")

    def serve_static(self, path):
        if path == '/' or path == '/index.html':
            filepath = os.path.join(FRONTEND_DIR, 'index.html')
        else:
            filepath = os.path.join(FRONTEND_DIR, path.lstrip('/'))

        if os.path.exists(filepath) and os.path.isfile(filepath):
            self.send_response(200)
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
            index_path = os.path.join(FRONTEND_DIR, 'index.html')
            if os.path.exists(index_path):
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                with open(index_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, f"File not found: {path}")

    def log_message(self, format, *args):
        print(f"[PROXY] {self.address_string()} - {format % args}")


class ThreadedHTTPServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    print("=" * 60)
    print("FabTwin One-Click Proxy Server")
    print("=" * 60)
    print(f"Proxy Port: {PROXY_PORT}")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Frontend Dir: {FRONTEND_DIR}")
    print(f"Access URL: http://server-ip:{PROXY_PORT}")
    print("=" * 60)

    if not os.path.exists(FRONTEND_DIR):
        print(f"[ERROR] Frontend directory not found: {FRONTEND_DIR}")
        print("[INFO] Please run 'npm run build' in frontend folder first")
        sys.exit(1)

    try:
        server = ThreadedHTTPServer(('0.0.0.0', PROXY_PORT), ProxyHandler)
    except PermissionError as e:
        print(f"[ERROR] Cannot bind port {PROXY_PORT}: {e}")
        print(f"[INFO] Port 80 requires admin privileges, or set PROXY_PORT=8080")
        sys.exit(1)

    print("[START] Proxy server running...")
    print("[INFO] Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Shutting down proxy server...")
        server.shutdown()


if __name__ == '__main__':
    main()