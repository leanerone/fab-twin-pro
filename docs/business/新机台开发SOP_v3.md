# 新机台开发 SOP（v3.0）

> 版本：v3.0
> 更新时间：2026-07-28
> 核心原则：**文件驱动，模块化，网站上调教动画**

---

## 一、架构总览

### 1.1 设计原则

- **文件驱动**：2D 交付 SVG 文件，3D 交付 GLB 文件，不写代码
- **模块化**：每个机型独立目录，互不影响
- **网站调教**：动画在网站上可视化配置，不手写 JSON
- **配置入库**：所有配置存数据库，不改代码即可新增机型

### 1.2 三方协作模型

```
┌──────────────┐     交付 SVG + GLB      ┌──────────────┐
│  模型开发人员  │ ──────────────────────→ │  FabTwin 管理  │
│  (画图/建模)   │                         │  (上传/配置)   │
└──────────────┘                         └──────┬───────┘
                                                │
                                    网站动画编辑器配置动画
                                                │
                                                ▼
                                         ┌──────────────┐
                                         │  FabTwin 平台  │
                                         │  (加载/渲染)   │
                                         └──────────────┘
```

### 1.3 文件目录结构

```
frontend/public/models/machines/
├── vpo-2200/                    ← 每个机型一个目录
│   ├── 2d.svg                   ← 模型开发人员交付的 2D 图
│   ├── 3d.glb                   ← 模型开发人员交付的 3D 模型
│   └── thumbnail.png            ← 缩略图（可选）
├── oxe-tel-drm/
│   ├── 2d.svg
│   └── 3d.glb
└── new-machine-xxx/
    ├── 2d.svg
    └── 3d.glb
```

### 1.4 数据库配置（machine_model_configs 表）

| 字段 | 存什么 | 示例 |
|------|--------|------|
| `model_id` | 机型唯一 ID | `VPO-2200` |
| `model_name` | 机型名称 | `PODOPENER 开盖机` |
| `view_mode` | 视图模式 | `vpo3d`（3D）/ `hybrid`（2D+3D） |
| `views_config_json` | 文件路径 + 相机参数 | 见下方 |
| `animation_config_json` | 动画配置（由动画编辑器生成） | 见下方 |
| `parts_config_json` | 部件元信息（由动画编辑器生成） | 见下方 |

`views_config_json` 示例：
```json
{
  "view_2d": {
    "type": "svg",
    "svg_source": "/models/machines/vpo-2200/2d.svg",
    "view_label": "正视图"
  },
  "view_3d": {
    "type": "glb",
    "model_source": "/models/machines/vpo-2200/3d.glb",
    "default_camera": {
      "position": [3.5, -1.5, 2.0],
      "target": [0, 0, 0.5]
    }
  }
}
```

---

## 二、完整开发流程（6 步）

### 步骤 1：模型开发人员制作 2D SVG

#### 1.1 工具选择

推荐工具（任选其一）：
- **Adobe Illustrator**：专业矢量图工具
- **Figma**：免费在线工具，导出 SVG 方便
- **Inkscape**：免费开源 SVG 编辑器
- **VS Code + SVG 插件**：直接编辑 SVG 代码

#### 1.2 绘图要求

1. **画布尺寸**：宽高比约 1:2（前视图，宽窄高长），推荐 `viewBox="0 0 540 1030"`
2. **颜色风格**：深色主题，背景透明，主色用灰色系（`#4b535c`、`#2a2e33`），强调色用青色（`#00d4ff`）
3. **绘制内容**：机台外观前视图，包括底座、立柱、腔体、操作面板等

#### 1.3 动画部件命名（最关键）

SVG 中**所有需要动画的元素必须包裹在 `<g>` 标签里，并设置 `id`**。

**必须命名的部件**（PODOPENER 类机型）：

| SVG 中的 `id` | 部件说明 | 动画类型 |
|---|---|---|
| `podShell` | POD 外壳 | 平移（放入/取出） |
| `latch` | 锁扣 | 旋转（锁定/解锁） |
| `cassette` | 花篮/晶舟 | 显示/隐藏 |
| `scanLine` | 扫描线 | 平移（上下扫描） |
| `signal` | 信号灯 | 闪烁/变色 |
| `leftHand` | 左机械手 | 平移/旋转 |
| `rightHand` | 右机械手 | 平移/旋转 |
| `uiPanel` | UI 操作面板 | 闪烁 |

**命名规范**：
- 用驼峰命名法：`podShell`，不要 `pod_shell` 或 `PodShell`
- id 不能有空格、中文、特殊字符
- 静态部件（底座、立柱等）不需要 id

**SVG 文件示例**：

```xml
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 540 1030">
  <!-- 静态部分：底座（不需要 id，不会动画） -->
  <rect x="10" y="950" width="520" height="80" fill="#4b535c"/>
  <rect x="50" y="100" width="440" height="850" rx="4" fill="#2a2e33"/>

  <!-- 动态部分：必须带 id，包裹在 <g> 里 -->
  <g id="podShell">
    <rect x="200" y="200" width="140" height="400" rx="2" fill="#888"/>
  </g>

  <g id="latch">
    <rect x="170" y="280" width="30" height="30" rx="2" fill="#ccc"/>
  </g>

  <g id="cassette">
    <rect x="210" y="220" width="120" height="160" fill="#aaa"/>
  </g>

  <g id="scanLine">
    <line x1="200" y1="200" x2="340" y2="200" stroke="#00d4ff" stroke-width="2"/>
  </g>

  <g id="signal">
    <circle cx="270" cy="50" r="10" fill="#888"/>
  </g>
</svg>
```

#### 1.4 导出检查清单

- [ ] 文件格式为 `.svg`（不是 `.png`、`.ai`、`.fig`）
- [ ] `viewBox` 已设置
- [ ] 动画部件都有 `<g id="xxx">` 包裹
- [ ] id 命名符合规范（驼峰，无空格）
- [ ] 背景透明
- [ ] 文件大小 < 500KB

---

### 步骤 2：模型开发人员制作 3D GLB

#### 2.1 工具选择

推荐使用 **Blender**（免费开源，导出 GLB 支持最好）。

#### 2.2 建模要求

1. **单位设置**：Blender 场景单位设为 **毫米**（`Scene Properties → Units → Millimeters`）
2. **坐标系**：Y 轴朝上（Blender 默认），原点在机台底部中心
3. **面数控制**：单机台总面数建议 < 50,000（保证浏览器流畅）
4. **材质**：使用 Principled BSDF，颜色直接赋值（不需要贴图）

#### 2.3 动画部件命名（最关键）

Blender 中**所有需要动画的 Mesh/Object 必须命名**，导出 GLB 后 Three.js 按 `name` 查找。

**必须命名的部件**（PODOPENER 类机型）：

| Blender 中的 Object 名 | 部件说明 | 动画类型 |
|---|---|---|
| `podShellGroup` | POD 外壳 | 平移 |
| `latchGroup` | 锁扣 | 旋转 |
| `cassetteGroup` | 花篮/晶舟 | 显示/隐藏 |
| `scanLineGroup` | 扫描线 | 平移 |
| `signalGroup` | 信号灯 | 闪烁/变色 |
| `leftHandGroup` | 左机械手 | 平移/旋转 |
| `rightHandGroup` | 右机械手 | 平移/旋转 |
| `uiPanel` | UI 操作面板 | 闪烁 |

**命名规范**：
- 动画部件以 `Group` 结尾（如 `podShellGroup`），与 2D 的 `podShell` 区分
- 静态部件随便命名，不影响

**Blender 操作步骤**：

1. 建模完成后，在 Outliner 面板中右键每个动画部件 → Rename
2. 确认名称与上表一致
3. 选中整个机台 → `File → Export → glTF 2.0 (.glb/.gltf)`
4. 导出设置：
   - Format: **Binary GLB**
   - Include: ✅ Custom Properties, ✅ Cameras（可选）, ✅ Lights（可选）
   - Mesh: ✅ Apply Modifiers
   - Object: ✅ Transform → Y Up

#### 2.4 导出检查清单

- [ ] 文件格式为 `.glb`
- [ ] 动画部件 Object 名称正确
- [ ] 坐标系 Y-Up
- [ ] 场景单位为毫米
- [ ] 文件大小 < 10MB
- [ ] 在 [gltf.viewer](https://gltf-viewer.donmccurdy.com/) 中能正常打开

---

### 步骤 3：模型开发人员提供事件映射表

#### 3.1 格式

Excel 或 Markdown 均可，必须包含以下列：

| 物理事件描述 | 事件码（VFEI） | 触发阶段 | 影响部件 | 动画动作 | 颜色 |
|---|---|---|---|---|---|
| 空POD放入 | `POD_PLACED` | POD放入 | podShell | 从下方平移到工作位 | - |
| POD锁定完成 | `COMPLETED_PORT_LOCK` | POD锁定 | latch | 旋转到锁定位 | 红 |
| 扫描RFID标签 | `READ_TAG` | 扫描标签 | scanLine | 扫描线上下移动 | 红 |
| 批次确认 | `BATCH_INFO_FROM_ECUI` | 信号确认 | signal | 闪烁 | 红 |
| POD门打开/上升 | `OPEN_POD` | POD上升 | podShell | 沿Z轴上升到顶端 | - |
| POD到达顶端 | `REACH_STAGE` | POD到顶 | podShell | 保持在顶端 | - |
| POD门关闭/下降 | `CLOSE_POD` | POD下降 | podShell | 沿Z轴下降到底端 | - |
| POD解锁完成 | `COMPLETED_PORT_UNLOCK` | POD解锁 | latch | 旋转到解锁位 | 绿 |
| 满POD移走 | `POD_REMOVED` | POD移走 | podShell | 从工作位平移到下方 | - |
| 报警 | `ALARM` | 报警 | signal | 闪烁 | 红 |

#### 3.2 说明

- **事件码**：必须与 VFEI 事件流里的 `event_code` 完全一致
- **两个 Flow**：PODOPENER 有 `PACKING`（穿入）和 `UNPACKING`（脱出）两个流程，需分别列出
- 如果新机台的事件码与 PODOPENER 不同，只需按实际填写即可

---

### 步骤 4：FabTwin 管理员上传模型文件

#### 4.1 创建机型目录

```
frontend/public/models/machines/vpo-2200/
```

#### 4.2 复制文件

把模型开发人员交付的文件放入：

```
frontend/public/models/machines/vpo-2200/
├── 2d.svg      ← 步骤 1 交付
└── 3d.glb      ← 步骤 2 交付
```

#### 4.3 在数据库中添加机型配置

```sql
INSERT INTO machine_model_configs (
  model_id, model_name, vendor, process_type, view_mode,
  views_config_json, animation_config_json, created_at, updated_at
) VALUES (
  'VPO-2200',
  'PODOPENER 开盖机',
  'TEL',
  'PODOPENER',
  'hybrid',
  '{"view_2d":{"type":"svg","svg_source":"/models/machines/vpo-2200/2d.svg","view_label":"正视图"},"view_3d":{"type":"glb","model_source":"/models/machines/vpo-2200/3d.glb","default_camera":{"position":[3.5,-1.5,2.0],"target":[0,0,0.5]}}}',
  '{}',
  TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD"T"HH24:MI:SS"Z"'),
  TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD"T"HH24:MI:SS"Z"')
);
```

#### 4.4 添加机台实例

```sql
INSERT INTO machines (id, name, model, line, floor, process_type, state)
VALUES ('VPO-01', 'PODOPENER-1', 'VPO-2200', 1, 2, 'PODOPENER', 'idle');
```

#### 4.5 验证文件可访问

启动前端后，浏览器打开以下 URL 确认文件可加载：
- `http://localhost:5173/models/machines/vpo-2200/2d.svg`
- `http://localhost:5173/models/machines/vpo-2200/3d.glb`

---

### 步骤 5：在网站上用动画编辑器配置动画

> **这是最关键的一步**：模型文件上传后，动画不需要手写 JSON，而是在网站的可视化编辑器中调教。

#### 5.1 动画编辑器入口

进入 **机台管理 → 机型配置 → 选择机型 → 动画编辑** Tab。

#### 5.2 编辑器界面设计（待开发）

```
┌──────────────────────────────────────────────────────────────┐
│  动画编辑器 - VPO-2200 PODOPENER 开盖机                       │
├────────────────────────┬─────────────────────────────────────┤
│                        │  动画配置面板                         │
│   2D / 3D 预览区域      │                                     │
│                        │  [+] 添加流程                        │
│   (点击部件即可选中)     │  ┌─────────────────────────────────┐│
│                        │  │ PACKING（穿入流程）              ││
│   ┌───┐                │  │                                 ││
│   │ ● │ podShell ← 选中 │  │ 阶段列表：                      ││
│   └───┘                │  │ 1. POD_PLACE    空POD放置  [▶]  ││
│                        │  │ 2. POD_LOCK     POD锁定   [▶]  ││
│                        │  │ 3. READ_TAG     扫描标签  [▶]  ││
│                        │  │ ...                             ││
│                        │  │                                 ││
│                        │  │ 事件→阶段映射：                   ││
│                        │  │ POD_PLACED → POD_PLACE          ││
│                        │  │ COMPLETED_PORT_LOCK → POD_LOCK  ││
│                        │  │ ...                             ││
│                        │  └─────────────────────────────────┘│
│                        │                                     │
│                        │  ┌─────────────────────────────────┐│
│                        │  │ 选中部件：podShell              ││
│                        │  │                                 ││
│                        │  │ 动画类型：[translate ▼]         ││
│                        │  │ 轴：[z ▼]                      ││
│                        │  │ 起始值：[148]    结束值：[680]  ││
│                        │  │ 时长(ms)：[2240]               ││
│                        │  │ 缓动：[mechanical ▼]           ││
│                        │  │                                 ││
│                        │  │ [▶ 预览动画]  [✓ 保存]         ││
│                        │  └─────────────────────────────────┘│
├────────────────────────┴─────────────────────────────────────┤
│  [▶ 播放全部流程]  [⏸ 暂停]  [🔄 重置]  [💾 保存全部配置]    │
└──────────────────────────────────────────────────────────────┘
```

#### 5.3 编辑器操作流程

**5.3.1 添加流程（Flow）**

1. 点击 **[+] 添加流程**
2. 输入流程名：`PACKING`（穿入）或 `UNPACKING`（脱出）
3. 系统自动创建空流程

**5.3.2 添加阶段（Phase）**

1. 在流程下点击 **[+] 添加阶段**
2. 填写：
   - 阶段 key：`POD_PLACE`（英文大写+下划线）
   - 阶段标签：`空POD放置`（中文，用于显示）
   - 时长(ms)：`1600`
   - 缓动：`mechanical` / `linear`
3. 重复直到所有阶段添加完毕

**5.3.3 配置事件映射**

1. 在 **事件→阶段映射** 区域点击 **[+] 添加映射**
2. 填写：
   - 事件码：`POD_PLACED`（必须与 VFEI 一致）
   - 映射到阶段：下拉选择 `POD_PLACE`
   - 备注：`空POD放入`

**5.3.4 选中部件并配置动画（核心操作）**

1. 在左侧 2D/3D 预览区域，**点击**某个部件（如 POD 外壳）
2. 右侧面板自动切换到该部件的动画配置
3. 配置动画参数：
   - **动画类型**：translate / rotate / scale / flash / visibility / color / scan / signal
   - **轴**（translate/rotate/scale 时）：x / y / z
   - **起始值**：动画开始时的位置/角度/缩放
   - **结束值**：动画结束时的位置/角度/缩放
   - **时长(ms)**：动画持续时间
   - **颜色**（flash/signal/color 时）：十六进制颜色
   - **缓动**：linear / mechanical / ease-in / ease-out
4. 点击 **[▶ 预览动画]**：预览区域播放该部件的动画
5. 调整参数直到动画效果正确
6. 点击 **[✓ 保存]** 保存该动画

**5.3.5 预览完整流程**

1. 点击底部 **[▶ 播放全部流程]**
2. 预览区域按阶段顺序播放所有动画
3. 如有不对，回到 5.3.4 调整

**5.3.6 保存到数据库**

1. 点击 **[💾 保存全部配置]**
2. 系统将整个动画配置序列化为 JSON 存入 `animation_config_json` 字段
3. 保存后立即生效，无需重启

#### 5.4 动画类型详解

| 动画类型 | 用途 | 参数 | 适用部件 |
|---|---|---|---|
| `translate` | 平移（POD 放入/取出/上升/下降） | axis, from, to, duration_ms, easing | podShell, cassette, leftHand, rightHand |
| `rotate` | 旋转（锁扣锁定/解锁） | axis, from, to, duration_ms, easing, color | latch |
| `scale` | 缩放 | axis, from, to, duration_ms, easing | 任意 |
| `flash` | 闪烁（信号确认、UI 确认） | color, duration_ms | signal, uiPanel |
| `visibility` | 显示/隐藏（花篮出现/消失） | from(0/1), to(0/1) | cassette |
| `color` | 变色 | color, duration_ms | signal, latch |
| `scan` | 扫描线移动 | axis, from, to, color, duration_ms | scanLine |
| `signal` | 信号条波动 | color, duration_ms | signalGroup |

#### 5.5 编辑器生成的配置格式

编辑器保存后，数据库 `animation_config_json` 中存储的格式如下（与现有 podopener.json 完全一致）：

```json
{
  "machine_type": "VPO-2200",
  "version": "1.0.0",
  "flows": {
    "PACKING": {
      "phases": [
        { "key": "POD_PLACE", "label": "空POD放置", "duration_ms": 1600, "easing": "mechanical" }
      ],
      "event_to_phase": {
        "POD_PLACED": { "phase": "POD_PLACE", "anim": "pod.enter", "note": "空POD放入" }
      }
    }
  },
  "animations": {
    "pod.enter": {
      "target": "podShell",
      "action": "translate",
      "axis": "y",
      "from": -400,
      "to": 0,
      "easing": "mechanical",
      "note": "POD从入口移动到工作位"
    }
  },
  "targets": {
    "podShell": { "view_2d": "podShell", "view_3d": "podShellGroup", "desc": "POD外壳" },
    "latch": { "view_2d": "latch", "view_3d": "latchGroup", "desc": "锁扣" }
  }
}
```

---

### 步骤 6：验证

#### 6.1 文件加载验证

1. 打开机台详情页
2. 切换 2D 视图：确认 SVG 正确加载并显示
3. 切换 3D 视图：确认 GLB 正确加载并渲染
4. 确认动画部件（podShell、latch 等）在 2D 和 3D 视图中都可见

#### 6.2 动画验证

1. 在事件列表中模拟一条 VFEI 事件（如 `POD_PLACED`）
2. 确认对应动画被触发（podShell 平移到工作位）
3. 依次测试所有事件码
4. 测试 PACKING 和 UNPACKING 两个流程

#### 6.3 跳转验证

1. 通过 AI 对话框查询 Lot
2. 点击表格中的跳转按钮
3. 确认跳转到 MachineDetail 页面并定位到正确时间点

---

## 三、交接清单汇总

### 模型开发人员 → FabTwin 管理员

| 序号 | 交付物 | 格式 | 要求 |
|------|--------|------|------|
| 1 | 2D 模型 | `.svg` | 动画部件用 `<g id="xxx">` 包裹，id 符合命名规范 |
| 2 | 3D 模型 | `.glb` | 动画部件 Object 命名符合规范，Y-Up，单位 mm |
| 3 | 事件映射表 | Excel/Markdown | 列出事件码→阶段→部件→动作→颜色 |

### FabTwin 管理员 → 模型开发人员

| 序号 | 参考物 | 内容 |
|------|--------|------|
| 1 | SVG 命名规范 | 本文档 2.3 节的 id 列表 |
| 2 | GLB 命名规范 | 本文档 3.3 节的 Object 名列表 |
| 3 | 事件码参考 | 现有 PODOPENER 的事件码列表（从 podopener.json 的 event_to_phase 提取） |

---

## 四、需要开发的改造项

> 以下为 FabTwin 平台侧需要改造的内容，实现后才能支撑上述流程。

### 4.1 组件改造：程序化绘制 → 文件加载

| 组件 | 当前方式 | 改造为 |
|------|----------|--------|
| MachineVpoView.vue | `draw2DBase()` 程序化画 SVG | `fetch(svg_url)` 加载 SVG，插入 DOM，按 id 操作动画元素 |
| MachineVpo3DView.vue | `buildMachineFromJson()` 拼 box/cylinder | `GLTFLoader.load(glb_url)` 加载 GLB，按 `name` 查找 Group |

**MachineVpoView.vue 改造要点**：
1. 读取 `views_config.view_2d.svg_source`
2. 如果 `svg_source` 是 URL 路径（如 `/models/machines/vpo-2200/2d.svg`），则 `fetch()` 加载
3. 如果 `svg_source === "procedural"`，则 fallback 到现有的 `draw2DBase()`（兼容旧机型）
4. 加载后通过 `innerHTML` 插入 SVG 容器
5. 动画仍通过 `document.getElementById(target.view_2d)` 操作 SVG 元素

**MachineVpo3DView.vue 改造要点**：
1. 读取 `views_config.view_3d.model_source`
2. 如果 URL 以 `.glb` 结尾，用 `GLTFLoader.load()` 加载
3. 如果 URL 以 `.json` 结尾，fallback 到现有的 `buildMachineFromJson()`（兼容旧机型）
4. 加载后通过 `scene.getObjectByName(target.view_3d)` 查找动画 Group
5. 动画逻辑（translate/rotate/scale/flash/visibility/color/scan/signal）保持不变

### 4.2 动画编辑器（新页面/新组件）

**位置**：`frontend/src/views/AnimationEditor.vue` 或嵌入 MachineDetail 管理页

**功能**：
1. 加载当前机型的 SVG/GLB 预览
2. 点击部件 → 高亮选中 → 显示部件 id/name
3. 配置动画参数表单（action/axis/from/to/duration/easing/color）
4. 预览单个动画
5. 按流程顺序预览全部动画
6. 保存配置到 `animation_config_json` 字段
7. 从已有事件映射表快速生成 event_to_phase

**技术方案**：
- 左侧预览区：复用 MachineVpoView/MachineVpo3DView 组件，增加点击选择模式
- 右侧配置区：Vue 表单组件
- 保存：`PUT /api/models/{model_id}` 更新 `animation_config_json`

**后端 API**（已有，无需新增）：
- `GET /api/models/{model_id}` - 获取当前配置
- `PUT /api/models/{model_id}` - 保存配置
- `POST /api/models/{model_id}/duplicate` - 复制配置

### 4.3 文件上传 API（新增）

| API | 方法 | 说明 |
|-----|------|------|
| `/api/models/{model_id}/upload/2d` | POST | 上传 SVG 文件 |
| `/api/models/{model_id}/upload/3d` | POST | 上传 GLB 文件 |
| `/api/models/{model_id}/files` | GET | 获取已上传文件列表 |
| `/api/models/{model_id}/files/{filename}` | DELETE | 删除文件 |

上传后自动保存到 `frontend/public/models/machines/{model_id}/` 目录。

### 4.4 NPM 依赖（新增）

```bash
npm install three @types/three    # Three.js（已安装）
# GLTFLoader 已内置在 three/addons/ 中，无需额外安装
```

---

## 五、开发优先级

| 优先级 | 改造项 | 效果 |
|--------|--------|------|
| **P0** | MachineVpo3DView.vue 支持 GLB 加载 | 模型开发人员交付的 GLB 可以直接在平台上看到 |
| **P0** | MachineVpoView.vue 支持 SVG 文件加载 | 模型开发人员交付的 SVG 可以直接在平台上看到 |
| **P1** | 动画编辑器 | 在网站上可视化调教动画，不手写 JSON |
| **P1** | 文件上传 API | 管理员可在网站上传 SVG/GLB，不靠手动复制文件 |
| **P2** | 文件管理 UI | 在机型配置页展示已上传文件列表，支持替换/删除 |

---

## 六、当前 PODOPENER 现有参考文件

| 文件 | 说明 |
|------|------|
| [podopener-2200-3d.json](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/public/models/podopener-2200-3d.json) | 现有 3D 模型（JSON 格式，改造后将替换为 GLB） |
| [podopener.json](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/configs/machine-animations/podopener.json) | 现有动画配置（238 行，改造后由动画编辑器生成） |
| [MachineVpoView.vue](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/components/MachineVpoView.vue) | 2D 组件（改造：程序化 → SVG 文件加载） |
| [MachineVpo3DView.vue](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/components/MachineVpo3DView.vue) | 3D 组件（改造：JSON 拼装 → GLB 加载） |
| [MachineDetail.vue](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/frontend/src/views/MachineDetail.vue) | 机台详情页（组件选择逻辑） |
| [models.py](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/backend/models.py) | ORM 模型定义（machine_model_configs 表） |
| [models.py (router)](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/backend/routers/models.py) | 机型 CRUD API |
| [seed_data.py](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/backend/seed_data.py) | 种子数据（含现有 PODOPENER 配置） |

---

## 七、常见问题

### Q1: 旧机型（JSON 程序化绘制的）怎么办？
改造时保留 fallback：如果 `views_config.view_2d.svg_source === "procedural"`，仍走 `draw2DBase()`；如果 `views_config.view_3d.model_source` 以 `.json` 结尾，仍走 `buildMachineFromJson()`。新旧机型互不影响。

### Q2: GLB 文件太大怎么办？
- Blender 导出时勾选 **Compress** 选项
- 控制面数 < 50,000
- 不使用贴图，只用纯色材质
- 如果仍太大，可在后端用 `gltf-transform` 压缩

### Q3: SVG 里的 id 和 GLB 里的 name 不一致怎么办？
`animation_config_json` 的 `targets` 字段分别定义了 `view_2d`（SVG id）和 `view_3d`（GLB name）的映射，两者可以不同名。但建议统一，减少混乱。

### Q4: 动画编辑器没开发完，怎么先配动画？
可以手动编写 `animation_config_json`（参考 podopener.json 格式），直接在数据库中 UPDATE。动画编辑器开发完成后，可在网站上可视化编辑。

### Q5: 模型开发人员没有 Blender 怎么办？
也可以用其他 3D 建模工具（3ds Max、Maya、Cinema 4D 等），只要能导出 `.glb` 格式即可。但 Blender 免费且 GLB 导出支持最好，推荐使用。

### Q6: 后续新增 N8N 工作流，AI 工具怎么自动识别？
在 `mcp_registry.py` 的 `MCP_REGISTRY` 字典中追加一条注册项即可。GPT-4o 会根据工具的 `description` 自动决定是否调用。详见 [AI_Architecture_Design.md](file:///C:/Users/A/AppData/Roaming/TRAE%20SOLO%20CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro/docs/AI_Architecture_Design.md)。
