# GitHub Copilot 高效开发方案

## 一、Copilot Agent 与 TRAE 对比

| 特性 | GitHub Copilot Agent | TRAE |
|------|---------------------|------|
| 多文件编辑 | 支持，但需要逐个确认 | 支持批量编辑 |
| 文件创建 | 支持 | 支持 |
| 终端命令 | 支持，但交互有限 | 支持完整终端操作 |
| 调试能力 | 基础断点调试 | 完整调试流程 |
| 项目理解 | 依赖代码扫描 | 深度项目分析 |
| 任务规划 | 简单规划 | TodoList详细计划 |
| 工具调用 | 有限工具 | 丰富工具链 |
| 内网环境 | 需要GitHub账号 | 本地部署 |

---

## 二、Copilot Agent 使用技巧

### 2.1 项目上下文配置

创建 `.github/copilot/instructions.md` 文件，让Copilot了解项目结构：

```markdown
# FabTwin Pro 项目说明

## 项目结构
- backend/: FastAPI后端，端口8001
- frontend/: Vue3前端，端口5173
- deploy.bat: 一键部署脚本

## 技术栈
- 后端: Python 3.10+, FastAPI, SQLAlchemy, SQLite/Oracle, Redis(可选)
- 前端: Vue3, Vite5, Three.js, Pinia, Vue Router
- 通信: REST API + WebSocket

## 数据库
- 当前使用SQLite: fabtwin.db
- 生产使用Oracle 19c

## 关键文件
- backend/main.py: 应用入口
- backend/config.py: 配置中心
- frontend/src/api/index.js: API封装
- frontend/src/stores/app.js: Pinia状态管理

## 运行方式
```bash
# 后端
cd backend && python main.py

# 前端
cd frontend && npm run dev
```

## 注意事项
- 不要修改package.json中的依赖版本
- 修改数据库配置需同步更新config.py
- 前端API调用通过api/index.js统一封装
```

### 2.2 高效提问技巧

#### 技巧1：指定文件范围
```
请修改 backend/routers/machines.py 中的 get_machines 函数，添加分页参数
```

#### 技巧2：提供代码上下文
```
我想在前端添加一个新的KPI卡片，参考现有的KpiCards.vue组件，添加一个"平均停机时间"的统计卡片
```

#### 技巧3：明确修改目标
```
请修改 frontend/src/components/FloorPlan.vue 中的天车标记样式，让选中的天车显示蓝色边框
```

#### 技巧4：分步骤提问
对于复杂任务，分成多个小问题：
1. 先问如何实现某个功能
2. 再问具体代码实现
3. 最后问调试方法

---

## 三、调试方案

### 3.1 后端调试

#### 方法一：VS Code Python调试

1. 打开 `.vscode/launch.json`，添加配置：
```json
{
  "version": "0.2.0",
  "configurations": [
    {
      "name": "FastAPI: main",
      "type": "python",
      "request": "launch",
      "module": "uvicorn",
      "args": [
        "main:app",
        "--host", "0.0.0.0",
        "--port", "8001",
        "--reload"
      ],
      "cwd": "${workspaceFolder}/backend",
      "env": {
        "PYTHONPATH": "${workspaceFolder}/backend"
      },
      "justMyCode": false
    }
  ]
}
```

2. 在代码中设置断点（点击行号左侧）
3. 按F5启动调试

#### 方法二：日志调试

在关键代码处添加日志：
```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# 在关键位置添加
logger.debug(f"机台状态: {machine.state}, 温度: {machine.temp}")
```

#### 方法三：API测试

使用curl或Postman测试API：
```bash
# 获取机台列表
curl http://localhost:8001/api/machines

# 获取机台详情
curl http://localhost:8001/api/machines/T01

# 添加天车
curl -X POST http://localhost:8001/api/floors/3/vehicles \
  -H "Content-Type: application/json" \
  -d '{"id":"OHT-01","name":"天车1号","track_id":1}'
```

### 3.2 前端调试

#### 方法一：浏览器开发者工具

1. 按F12打开开发者工具
2. **Console**：查看JavaScript错误和console.log输出
3. **Network**：查看API请求和WebSocket连接
4. **Elements**：查看DOM结构和CSS样式
5. **Sources**：设置断点调试JavaScript

#### 方法二：Vue DevTools扩展

1. 在Chrome/Firefox安装Vue DevTools扩展
2. 打开后可以：
   - 查看组件树
   - 查看组件状态（data/props/computed）
   - 调试Pinia状态管理
   - 时间旅行调试

#### 方法三：Vite开发服务器

Vite提供热更新功能，修改代码后自动刷新页面：
```bash
cd frontend
npm run dev
```

### 3.3 WebSocket调试

#### 方法一：浏览器开发者工具

1. 打开开发者工具 → Network标签
2. 筛选WebSocket连接
3. 点击连接可以查看发送和接收的消息

#### 方法二：命令行测试

```bash
# 使用wscat测试WebSocket
npm install -g wscat
wscat -c ws://localhost:8001/ws/realtime
```

### 3.4 3D调试

#### 方法一：Three.js Inspector

1. 在浏览器控制台输入：
```javascript
// 安装Three.js Inspector
const script = document.createElement('script');
script.src = 'https://cdn.jsdelivr.net/npm/threejs-inspector@latest';
document.head.appendChild(script);
```

2. 打开后可以：
   - 查看场景对象树
   - 修改对象属性（位置、旋转、缩放）
   - 查看材质和几何体
   - 调试光照

#### 方法二：添加辅助对象

```javascript
// 在FloorView3D.vue中添加
const axesHelper = new THREE.AxesHelper(10);
scene.add(axesHelper);

// 显示网格
const gridHelper = new THREE.GridHelper(60, 60);
scene.add(gridHelper);
```

---

## 四、与现有项目对接

### 4.1 开发流程

```
1. 需求分析 → 创建Issue
2. 创建Feature分支
3. 开发实现（使用Copilot）
4. 本地测试（前后端联调）
5. 提交代码 → 创建PR
6. 代码审查 → 合并到develop
7. 部署测试环境验证
8. 合并到main → 生产部署
```

### 4.2 Copilot使用场景

#### 场景1：新功能开发

```
请帮我在后端添加一个新的API端点，用于查询指定时间段内的机台事件统计
```

#### 场景2：Bug修复

```
前端页面加载时显示空白，请帮我排查问题。当前错误信息是：Uncaught SyntaxError: Unexpected token
```

#### 场景3：代码优化

```
请帮我优化 frontend/src/components/FloorView3D.vue 中的3D渲染性能，当前加载100台机台时帧率较低
```

#### 场景4：文档生成

```
请帮我为 backend/routers/floors.py 中的API端点生成API文档
```

#### 场景5：代码重构

```
请帮我重构 frontend/src/api/index.js，将API调用按模块分组
```

### 4.3 注意事项

#### 事项1：依赖版本

Copilot可能会建议安装新依赖，需确认：
- 是否与现有项目兼容
- 是否有安全风险
- 是否符合公司规范

#### 事项2：代码风格

保持项目现有代码风格一致：
- 使用项目已有的代码规范
- 遵循命名约定
- 保持注释风格统一

#### 事项3：测试验证

Copilot生成的代码可能存在问题，需验证：
- 功能是否正确实现
- 是否有语法错误
- 是否有运行时错误
- 是否有性能问题

---

## 五、最佳实践

### 5.1 代码审查清单

| 检查项 | 说明 |
|--------|------|
| 安全性 | 是否有SQL注入、XSS等安全漏洞 |
| 性能 | 是否有性能瓶颈 |
| 可维护性 | 代码结构是否清晰 |
| 测试 | 是否有单元测试 |
| 文档 | 是否有足够的注释 |

### 5.2 开发规范

```markdown
# 开发规范

## 分支管理
- main: 稳定版本
- develop: 开发版本
- feature/{feature-name}: 功能分支
- bugfix/{bug-name}: 修复分支

## 提交规范
- feat: 新功能
- fix: 修复bug
- refactor: 代码重构
- docs: 文档更新
- test: 测试代码
- style: 代码格式

## 代码规范
- Python: PEP8
- JavaScript: ESLint + Prettier
- Vue: Vue官方风格指南

## 测试要求
- 新增功能需编写单元测试
- 修复bug需添加回归测试
- 代码覆盖率>=80%

## 文档要求
- 关键函数需有文档字符串
- API端点需有注释说明
- 复杂业务逻辑需有流程图
```

### 5.3 常见问题解决方案

| 问题 | 解决方案 |
|------|----------|
| Copilot理解不了项目结构 | 创建.github/copilot/instructions.md |
| Copilot生成的代码有错误 | 提供更多上下文，分步骤提问 |
| 前后端联调失败 | 检查API路径、参数格式、跨域设置 |
| 3D模型加载失败 | 检查模型格式、路径、命名规范 |
| WebSocket连接失败 | 检查端口、网络、CORS配置 |

---

## 六、Copilot配置建议

### 6.1 VS Code设置

```json
{
  "github.copilot.enable": true,
  "github.copilot.advanced": {
    "inlineSuggestions": true,
    "codeLens": true
  },
  "editor.inlineSuggest.enabled": true,
  "editor.suggestSelection": "first"
}
```

### 6.2 快捷键

| 快捷键 | 功能 |
|--------|------|
| Ctrl+Enter | 接受Copilot建议 |
| Tab | 接受当前行建议 |
| Esc | 拒绝建议 |
| Ctrl+Alt+N | 新建文件 |
| Ctrl+Alt+F | 格式化代码 |

---

## 七、总结

### 7.1 Copilot优势
- 代码补全能力强
- 理解上下文好
- 支持多种语言
- 集成VS Code

### 7.2 应对Copilot限制的策略
1. **项目文档化**：创建详细的instructions.md
2. **分步骤提问**：复杂任务拆分成小问题
3. **提供上下文**：明确指定文件和代码片段
4. **本地调试**：利用VS Code强大的调试能力
5. **代码审查**：Copilot生成的代码需要人工审查

### 7.3 建议流程
```
1. 使用Copilot生成代码框架
2. 手动完善细节和业务逻辑
3. 本地测试验证
4. 代码审查
5. 提交代码
```

通过以上方案，可以在VS Code中高效使用GitHub Copilot进行开发，充分发挥其代码补全和理解能力，同时通过完善的文档和调试流程弥补其Agent能力的不足。
