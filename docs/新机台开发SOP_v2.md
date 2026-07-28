# FabTwin Pro 新机台开发 SOP（v2.0）

> 适用项目：fab-twin-pro v2.0
> 更新日期：2026-07-27
> 前置条件：前后端服务已启动（前端 http://localhost:5173，后端 http://localhost:8002）

---

## 一、总览：5步建好一台新机台

```
第1步  创建机型  →  在数据库注册一个新机型（2分钟）
第2步  画2D图    →  用Inkscape画SVG 或 上传HTML自动解析（30分钟~2小时）
第3步  建3D模型  →  用体素编辑器拼装箱体（30分钟~1小时）
第4步  配动画    →  在动画配置Tab绑定事件→阶段→动画→部件（1~2小时）
第5步  测试验证  →  在动画调试Tab逐个触发事件验证（30分钟）
```

**核心思路**：v2.0把所有配置都存在数据库里，不需要改代码、不需要改JSON文件，全部通过网页操作完成。

---

## 二、第1步：创建机型（2分钟）

### 2.1 操作步骤

1. 浏览器打开 `http://localhost:5173/#/model-editor`
2. 确认当前Tab是 **📦 模型管理**
3. 滚动到下方「新建机台型号」表单
4. 填写信息：

| 字段 | 说明 | 示例 |
|------|------|------|
| 型号ID | 唯一标识，大写 | `DEMO-TEST-01` |
| 型号名称 | 中文名 | `测试机型01` |
| 厂商 | 设备厂商 | `TEST` |
| 工艺类型 | 下拉选择 | ETCH / LITHO / CVD / PVD / CMP / WET / METAL / INSPECT |
| 视图模式 | 下拉选择 | threejs（3D）/ vpo（2D）/ hybrid（2D+3D） |
| 描述 | 可选 | `用于测试的演示机型` |

5. 点击「创建」按钮
6. 上方模型列表会出现新创建的机型卡片
7. 点击该卡片选中它

### 2.2 验证

- 模型卡片高亮显示 = 选中成功
- 数据库 `MACHINE_MODEL_CONFIGS` 表中可查到该记录

---

## 三、第2步：画2D图（30分钟~2小时）

### 方案A：用Inkscape画SVG（推荐，适合从零开始）

#### 3.1 画图

1. 打开 Inkscape，新建文档（800×600px）
2. 用矩形工具画出机台的各个部件
3. **关键：给每个可动部件设置id**

#### 3.2 部件命名规则

| 部件类型 | id命名规则 | 示例 |
|---------|-----------|------|
| 外壳/底座 | `{name}2dLayer` | `pod2dLayer` |
| 锁扣/旋转件 | `{name}2d` | `latch2d` |
| 晶舟/显隐件 | `{name}2d` | `cassette2d` |
| 信号灯 | `{name}2d` | `signal2d` |
| 机械臂 | `{name}2d` | `leftHand2d` |

#### 3.3 设置id的方法

1. 选中部件 → 右键 → 「对象属性」（Shift+Ctrl+O）
2. 在「ID」字段填入名称（如 `pod2dLayer`）
3. 点击「设置」按钮

#### 3.4 导出并上传

1. 文件 → 另存为 → SVG格式
2. 回到网页模型管理Tab，选中机型后
3. 在下方「模型文件上传」区域上传SVG文件
4. 系统自动记录到数据库

### 方案B：上传HTML自动解析（适合已有HTML原型的）

如果你同事有现成的HTML文件（如 `OXE_2D.html`）：

1. 回到模型管理Tab，选中目标机型
2. 在「模型文件上传」区域上传 `.html` 文件
3. 系统自动调用 `/api/uploads/parse-html` 接口
4. 自动提取HTML中的 UNITS 定义，生成 `parts_config_json`
5. 提取结果包含：部件名称、坐标、尺寸

### 方案C：导出SVG后在Inkscape精修

1. 在模型管理Tab选中已有部件配置的机型
2. 点击「导出SVG」按钮（调用 `/api/uploads/export-svg/{model_id}`）
3. 系统根据数据库中的部件配置生成SVG文件
4. 下载后在 Inkscape 中打开精修
5. 修好后重新上传

---

## 四、第3步：建3D模型（30分钟~1小时）

### 4.1 打开体素编辑器

1. 在模型编辑器页面点击 **🧊 体素建模** Tab
2. 左侧是部件列表，右侧是属性编辑区

### 4.2 添加部件

1. 点击「添加盒子」或「添加圆柱」按钮
2. 新部件自动出现在列表中并被选中

### 4.3 编辑部件属性

选中一个部件后，在右侧表单编辑：

| 属性 | 说明 | 示例 |
|------|------|------|
| 名称 | 必须与动画配置中的 view_3d 一致 | `podShellGroup` |
| 类型 | box 或 cylinder | box |
| 位置 X/Y/Z | 三维空间坐标 | 0, 0, 0 |
| 尺寸（盒子） | 宽/高/深 | 2, 1, 1.5 |
| 尺寸（圆柱） | 半径/高度 | 0.5, 2 |
| 颜色 | 十六进制颜色 | #4a90e2 |

### 4.4 3D部件命名规则

| 部件类型 | 命名规则 | 示例 |
|---------|---------|------|
| 外壳/容器 | `{name}Group` | `podShellGroup` |
| 锁扣 | `{name}Group` | `latchGroup` |
| 晶舟 | `{name}Group` | `cassetteGroup` |
| 信号灯 | `{name}Group` | `signalGroup` |
| 机械臂 | `{name}Group` | `leftHandGroup` |

### 4.5 导出配置

1. 点击「导出JSON」按钮
2. 文件下载到本地（如 `voxel-model-1234567.json`）
3. 这个JSON可以后续导入Blender精修，或直接作为 parts_config 使用

### 4.6 进阶：用Blender精修（可选）

如果体素编辑器不够用：
1. 用Blender打开导出的JSON（需安装glTF插件）
2. 精修后导出 `.glb` 文件
3. 在模型管理Tab上传GLB文件
4. 确保Blender中的Group命名与上方规则一致

---

## 五、第4步：配动画（1~2小时）

### 5.1 打开动画配置

1. 点击 **⚙️ 动画配置** Tab
2. 选中一个机型后，系统从数据库加载该机型的动画配置
3. 界面分为：左侧部件清单 + 右侧事件动作

### 5.2 理解三层映射关系

```
事件（EVENT_NAME）
  → 阶段（phase）
    → 动画原语（anim）
      → 部件（target）
```

**举例**：
```
事件：POD_PLACED
  → 阶段：POD_PLACE
    → 动画：pod.enter
      → 部件：podShell
        → 动作：translate，Y轴，从-400到0
```

### 5.3 配置部件绑定（targets）

在左侧「部件清单」区域，确认每个部件的 2D/3D 绑定：

```json
{
  "podShell": {
    "view_2d": "pod2dLayer",    // 与SVG中的id一致
    "view_3d": "podShellGroup", // 与体素编辑器中的名称一致
    "desc": "POD外壳"
  }
}
```

如果部件清单为空，需要通过API或数据库添加targets配置。

### 5.4 配置动画原语（animations）

在右侧区域编辑动画原语。8种可用动作：

| 动作 | 说明 | 必填字段 |
|------|------|---------|
| translate | 平移 | axis, from, to |
| rotate | 旋转 | axis, from, to |
| scale | 缩放 | axis, from, to |
| flash | 闪烁 | color, duration_ms |
| visibility | 显隐 | from(0/1), to(0/1) |
| color | 变色 | color |
| scan | 扫描 | axis, from, to, color |
| signal | 信号波动 | color, duration_ms |

### 5.5 配置事件映射（flows → event_to_phase）

定义流程（PACKING/UNPACKING）中的事件→阶段映射：

```json
{
  "PACKING": {
    "phases": [
      { "key": "POD_PLACE", "label": "空POD放置", "duration_ms": 1600 }
    ],
    "event_to_phase": {
      "POD_PLACED": { "phase": "POD_PLACE", "anim": "pod.enter" }
    }
  }
}
```

### 5.6 保存配置

v2.0中所有动画配置存储在 `machine_model_configs.animation_config_json` 字段：
1. 修改后点击「保存」按钮
2. 配置即时写入数据库
3. 前端刷新后自动加载最新配置（热更新，无需重新构建）

---

## 六、第5步：测试验证（30分钟）

### 6.1 打开动画调试

1. 点击 **🔍 动画调试** Tab
2. 选择要调试的机型

### 6.2 逐个事件测试

1. 在调试面板中找到事件触发按钮
2. 逐个点击事件按钮（如 POD_PLACED）
3. 观察2D/3D视图中对应部件是否执行动画
4. 检查动画方向、速度、颜色是否正确

### 6.3 常见问题排查

| 现象 | 原因 | 解决 |
|------|------|------|
| 点击事件无反应 | targets.view_2d 与 SVG id 不匹配 | 检查命名 |
| 动画方向反了 | from/to 写反 | 互换值 |
| 动画太快/太慢 | duration_ms 不合适 | 调整数值（≥100） |
| 部件找不到 | 3D Group名不匹配 | 检查体素编辑器中的名称 |
| 配置不生效 | 缓存未刷新 | 刷新页面或重启后端 |

### 6.4 端到端验证

1. 用 WinForm 模拟器或直接写DB插入测试事件
2. 前端应自动收到事件并触发对应动画
3. 检查「事件列表」中期望阶段与实际阶段是否一致

---

## 七、完整流程示例：创建一个简单测试机型

### 7.1 准备

确保前后端已启动，数据库已连接。

### 7.2 执行

```
1. 打开 http://localhost:5173/#/model-editor
2. 在「新建机台型号」中创建：
   - 型号ID：DEMO-01
   - 型号名称：演示机型
   - 视图模式：threejs
3. 点击创建，选中新建的机型卡片

4. 切换到「🧊 体素建模」Tab
5. 添加3个部件：
   - box: 名称 baseGroup, 位置 0,-1,0, 尺寸 3,0.5,2, 颜色 #555555
   - box: 名称 armGroup, 位置 0,0,0, 尺寸 0.3,2,0.3, 颜色 #4a90e2
   - cylinder: 名称 signalGroup, 位置 1.5,1,0, 半径 0.2, 高 0.5, 颜色 #ef4444
6. 点击「导出JSON」保存到本地

7. 切换到「⚙️ 动画配置」Tab
8. 配置3个部件的targets：
   - base:    view_2d="base2dLayer",  view_3d="baseGroup"
   - arm:     view_2d="arm2d",        view_3d="armGroup"
   - signal:  view_2d="signal2d",     view_3d="signalGroup"
9. 配置2个动画原语：
   - arm.move:  target=arm, action=translate, axis=y, from=0, to=1
   - signal.on: target=signal, action=flash, color=#ef4444, duration_ms=800
10. 配置事件映射：
    - START: phase=START, anim=arm.move
    - DONE:  phase=DONE,  anim=signal.on
11. 保存配置

12. 切换到「🔍 动画调试」Tab
13. 点击 START 事件 → arm应向上移动
14. 点击 DONE 事件 → signal应闪烁
```

### 7.3 验证结果

- 动画正常触发 = 配置链路通畅
- 无报错 = 数据库读写正常

---

## 八、相关文件和接口

| 功能 | 文件/接口 | 说明 |
|------|----------|------|
| 模型管理 | `frontend/src/views/ModelEditor.vue` | 4个Tab的主界面 |
| 文件上传 | `backend/routers/uploads.py` | SVG/GLB/HTML上传 |
| HTML解析 | `backend/services/html_parser.py` | 提取UNITS定义 |
| SVG导出 | `backend/routers/uploads.py` `/export-svg/{model_id}` | 生成SVG文件 |
| 模型API | `backend/routers/models.py` | CRUD机型配置 |
| 动画配置 | `frontend/src/composables/useAnimationConfig.js` | 从API加载配置 |
| 数据库表 | `MACHINE_MODEL_CONFIGS` | 含animation_config_json字段 |

---

## 九、旧SOP差异说明

与v1.0 SOP相比的主要变化：

| 项目 | v1.0 | v2.0 |
|------|------|------|
| 动画配置存储 | 静态JSON文件 `configs/machine-animations/*.json` | 数据库 `animation_config_json` 字段 |
| 2D图创建 | 仅Inkscape | Inkscape + HTML解析 + SVG导出 |
| 3D建模 | 箱体拼装器（简陋） | 体素编辑器（box/cylinder/导出JSON） |
| 配置热更新 | 需要重新构建前端 | 修改后即时生效 |
| 开发指南Tab | 有（占界面空间） | 已移除 |
| 事件代码Tab | 有（占界面空间） | 已移除 |

---

## 十、获取帮助

1. 浏览器F12控制台查看错误信息
2. 后端日志查看API调用情况
3. 参考 PODOPENER-1 的配置作为完整案例
4. 参考《变更更改版记录.md》了解v2.0变更详情
