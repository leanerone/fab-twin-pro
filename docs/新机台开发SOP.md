# FabTwin Pro 新机台开发 SOP

> 目标读者：初学者同事（不会画图、不会建模、不熟悉代码）  
> 适用项目：fab-twin-pro-ver1  
> 完整案例：VPO-2200 PODOPENER 开盖机  
> 文档版本：1.0  
> 更新日期：2026-07-19

---

## 目录

- [一、SOP 总览](#一sop-总览)
- [二、阶段 0：准备](#二阶段-0准备)
- [三、阶段 1：2D 绘图（Inkscape）](#三阶段-12d-绘图inkscape)
- [四、阶段 2：3D 建模（箱体拼装器优先）](#四阶段-23d-建模箱体拼装器优先)
- [五、阶段 3：动画设置](#五阶段-3动画设置)
- [六、阶段 4：配置注册](#六阶段-4配置注册)
- [七、阶段 5：事件绑定](#七阶段-5事件绑定)
- [八、阶段 6：上线](#八阶段-6上线)
- [九、给初学者的 7 天培训大纲](#九给初学者的-7-天培训大纲)
- [十、扩展性设计](#十扩展性设计应对部件越来越多的机型)
- [附录 A：完整 podopener.json 配置示例](#附录-a完整-podopenopenerjson-配置示例)
- [附录 B：14 个事件清单](#附录-b14-个事件清单packing--unpacking-各-14-个)
- [附录 C：配置 Schema 字段说明](#附录-c配置-schema-字段说明)
- [附录 D：常见问题速查](#附录-d常见问题速查)

---

## 一、SOP 总览

### 1.1 这份 SOP 是写给谁的？

如果你符合以下任一情况，这份文档就是为你写的：

- ❓ 不会用 Photoshop / Illustrator / Blender 等专业绘图建模工具
- ❓ 不会写 Vue / Three.js / FastAPI 代码
- ❓ 第一次接触数字孪生项目
- ❓ 接到任务要接入一台新机台，不知道从哪里开始

**没关系**。这份 SOP 会用傻瓜式的步骤，手把手教你把一台新机台接入 FabTwin Pro 平台。我们以 **VPO-2200 PODOPENER 开盖机** 为完整案例，每个步骤都对应 PODOPENER 的真实做法。

### 1.2 7 个阶段全景

```
┌──────────────────────────────────────────────────────────┐
│                                                            │
│   阶段 0  准备                                              │
│   ├─ 软件清单（Inkscape / 箱体拼装器 / VSCode）             │
│   ├─ 资料清单（业务流程 / 事件清单 / 机台照片）              │
│   └─ 目录约定                                              │
│                                                            │
│   阶段 1  2D 绘图（Inkscape）                              │
│   ├─ 操作步骤（新建 / 画部件 / 命名 / 导出 SVG）            │
│   ├─ 命名约定（pod2dLayer / latch2d / cassette2d ...）     │
│   └─ 傻瓜模式降级（不会画就用矩形拼）                       │
│                                                            │
│   阶段 2  3D 建模（箱体拼装器优先）                         │
│   ├─ 方案 A：箱体拼装器（ModelEditor.vue）— 推荐            │
│   ├─ 方案 B：Blender 备选（精度高，学习成本高）             │
│   └─ 命名规范强制（podShellGroup / latchGroup ...）         │
│                                                            │
│   阶段 3  动画设置                                          │
│   ├─ 动画原语库（8 种 action：translate/rotate/...）        │
│   ├─ 配置写法（podopener.json 的 animations 段）            │
│   └─ 调试面板使用（手动触发 / 配置热编辑）                  │
│                                                            │
│   阶段 4  配置注册                                          │
│   ├─ podopener.json 详解                                   │
│   ├─ 后端注册（machine_model_configs 表）                   │
│   └─ 视图路由（按 view_mode 自动选组件）                    │
│                                                            │
│   阶段 5  事件绑定                                          │
│   ├─ 事件清单模板                                          │
│   ├─ 对接方式（WinForm 模拟器 / TIBRV / DB 直写）           │
│   └─ 验证流程（端到端测试）                                 │
│                                                            │
│   阶段 6  上线                                              │
│   ├─ Checklist                                             │
│   └─ 文档模板                                              │
│                                                            │
└──────────────────────────────────────────────────────────┘
```

### 1.3 整体耗时预估

| 阶段 | 新手耗时 | 老手耗时 | 关键产出 |
|------|---------|---------|---------|
| 阶段 0 准备 | 0.5 天 | 0.5 天 | 环境 + 资料齐全 |
| 阶段 1 2D 绘图 | 2 天 | 0.5 天 | `xxx.svg` 文件 |
| 阶段 2 3D 建模 | 3 天 | 1 天 | 箱体拼装配置 / `.glb` 文件 |
| 阶段 3 动画设置 | 2 天 | 0.5 天 | `xxx.json` 配置 |
| 阶段 4 配置注册 | 0.5 天 | 0.2 天 | 后端注册 + 视图路由 |
| 阶段 5 事件绑定 | 1 天 | 0.5 天 | 事件清单 + WinForm 测试 |
| 阶段 6 上线 | 0.5 天 | 0.2 天 | Checklist 通过 |
| **合计** | **9.5 天** | **3.4 天** | **新机台接入完成** |

---

## 二、阶段 0：准备

### 2.1 软件清单

| 软件 | 版本 | 用途 | 下载地址 | 备注 |
|------|------|------|---------|------|
| **Inkscape** | 1.3+ | 2D 矢量绘图（SVG） | https://inkscape.org/ | 离线、免费、中文界面 |
| **箱体拼装器** | 内置 | 3D 箱体拼装（基于 `ModelEditor.vue`） | 项目内 `frontend/src/views/ModelEditor.vue` | **优先使用**，无需 Blender |
| **Blender**（备选） | 3.x+ | 精细 3D 建模 | https://www.blender.org/ | 仅在箱体拼装器不够用时启用 |
| **VSCode** | 最新 | 代码 / JSON 配置编辑 | https://code.visualstudio.com/ | 装 Volar + ESLint 插件 |
| **Node.js** | 16+ | 前端运行 | https://nodejs.org/ | |
| **Python** | 3.10+ | 后端运行 | https://www.python.org/ | |
| **Oracle SQL Developer** | 最新 | 查看 Oracle 数据（可选） | Oracle 官网 | |
| **浏览器** | Chrome / Edge 最新 | 调试前端 | | F12 开发者工具 |

### 2.2 资料清单

接入新机台前，必须收集齐以下资料：

| 资料 | 来源 | 必需 | 示例 |
|------|------|------|------|
| 业务流程文档 | 工艺工程师 | ✅ | `docs/PODOPENER.docx` |
| 事件清单 | EAP 工程师 | ✅ | 14 个 PACKING 事件 + 6 个 UNPACKING 事件 |
| 报警清单 | 工艺工程师 | ✅ | `docs/alarmnew.docx` |
| 机台照片（多角度） | 现场工程师 | ✅ | 正视图 / 侧视图 / 俯视图 / 细节图 |
| 机台型号信息 | 设备厂商 | ✅ | VPO-2200 / TEL DRM UNITY |
| 2D 设计原型 | UI 设计师 | 🟡 建议 | `docs/VPO_2D.docx` / `docs/VPO2D.html` |
| 3D 设计原型 | UI 设计师 | 🟡 建议 | `docs/VPO_3D.HTML` |
| 现有 GLB 模型 | 世庆 | 🟡 可选 | `frontend/public/models/xxx.glb` |
| RV 报文样例 | EAP 工程师 | 🟡 可选 | 用于事件绑定阶段验证 |

### 2.3 目录约定

新机台接入涉及的目录：

```
fab-twin-pro-ver1/
├── frontend/
│   ├── src/
│   │   ├── configs/
│   │   │   └── machine-animations/
│   │   │       ├── podopener.json        ← 你的新机型配置文件放这里
│   │   │       ├── _schema.json          ← Schema（不要改）
│   │   │       └── {你的机型小写}.json    ← 新建
│   │   ├── components/
│   │   │   ├── MachineVpoView.vue        ← 已有组件（参考）
│   │   │   ├── MachineVpo3DView.vue      ← 已有组件（参考）
│   │   │   └── Machine{YourModel}View.vue ← 如果是新视图类型才新建
│   │   └── assets/
│   │       └── machines/
│   │           └── {your-model}/         ← 新机型的 SVG 等资源
│   │               ├── 2d.svg
│   │               └── parts/
│   └── public/
│       └── models/
│           └── {your-model}-v1.glb       ← Blender 导出的 GLB 放这里
├── backend/
│   └── seed_data.py                     ← 注册机台实例
└── docs/
    └── {your-model}.docx                ← 业务参考文档
```

**命名约定**：

| 类型 | 命名规则 | 示例 |
|------|---------|------|
| 配置文件 | 全小写机型名 + `.json` | `podopener.json` / `etch-tel-unity.json` |
| SVG 资源 | 机型小写 + `-2d.svg` | `podopener-2d.svg` |
| GLB 模型 | `{设备类型}-{厂商}-{型号}-v{版本}.glb` | `ETCH-TEL-DRM-UNITY-v1.glb` |
| 视图组件 | `Machine{CamelCase}View.vue` | `MachineVpoView.vue` |
| 数据库 model_id | `{厂商}-{型号}` 大写 | `VPO-2200` / `TEL-DRM-UNIT` |

### 2.4 阶段 0 验收标准

- [ ] Inkscape 已安装并能打开
- [ ] 项目能正常 `npm run dev` 启动
- [ ] 后端能正常 `python main.py` 启动
- [ ] 业务流程文档已读取并理解
- [ ] 事件清单已收集（至少知道事件名称和大致顺序）
- [ ] 机台照片已收集（至少 3 个角度）
- [ ] 已确定机型命名（model_id）

### 2.5 常见问题

**Q1：Inkscape 打开是英文界面？**  
A：菜单 `Edit → Preferences → Interface → Language` 选「简体中文」重启。

**Q2：箱体拼装器在哪里打开？**  
A：项目启动后访问 `http://localhost:5173/#/model-editor`。

**Q3：业务流程文档看不懂怎么办？**  
A：找工艺工程师面对面讲一遍，把流程图画成时序图。PODOPENER 的 14 个事件就是 14 步操作，按时间顺序排列。

**Q4：没有机台照片怎么办？**  
A：让现场工程师拍，多角度（正视/侧视/俯视/细节）各一张，越高分辨率越好。

---

## 三、阶段 1：2D 绘图（Inkscape）

### 3.1 为什么选 Inkscape？

- ✅ 免费、开源、离线可用（内网环境友好）
- ✅ 中文界面，操作类似 PowerPoint
- ✅ 直接导出 SVG（前端原生支持）
- ✅ 支持 id 命名（配置层通过 id 找部件）

### 3.2 操作步骤（以 PODOPENER 2D 为例）

#### 步骤 1：新建文档

1. 打开 Inkscape → 文件 → 新建
2. 文档属性（`Shift+Ctrl+D`）：
   - 宽度：800 px
   - 高度：600 px
   - 单位：px

#### 步骤 2：画机台主体框架

1. 用左侧工具栏的「矩形工具」（`R`）画一个大矩形作为机台底座
2. 颜色：深灰 `#2a2a3a`
3. 位置：居中

#### 步骤 3：画可动部件

PODOPENER 的可动部件包括：

| 部件 | 中文 | Inkscape 操作 |
|------|------|--------------|
| `pod2dLayer` | POD 外壳 | 矩形 + 圆角（POD 是方形带圆角） |
| `latch2d` | 锁扣 | 小矩形 + 旋转（用「选择工具」拖动手柄） |
| `cassette2d` | 晶舟 | 多个小矩形拼装（晶圆片叠加） |
| `scanLine2d` | 扫描线 | 一条线段 + 红色 |
| `signal2d` | 信号灯 | 圆形（用「椭圆工具」`E`） |
| `uiPanel2d` | UI 操作面板 | 矩形 + 文字 |
| `leftHand2d` | 左手模型 | 矩形 + 圆角 |
| `rightHand2d` | 右手模型 | 矩形 + 圆角 |

#### 步骤 4：命名每个部件（关键！）

**这是最重要的步骤**，配置层通过 id 查找部件：

1. 选中一个部件（如 POD 外壳矩形）
2. 右键 → 「对象属性」（`Shift+Ctrl+O`）
3. 在「Label」字段填入：`pod2dLayer`
4. 在「ID」字段填入：`pod2dLayer`（与 Label 一致）
5. 点击「设置」

重复此步骤，给每个可动部件命名。命名必须与 `podopener.json` 中 `targets.xxx.view_2d` 字段完全一致。

#### 步骤 5：分组（可选）

把属于同一组合的部件用「Ctrl+G」分组，便于管理。

#### 步骤 6：导出 SVG

1. 文件 → 另存为
2. 文件名：`podopener-2d.svg`
3. 保存类型：SVG（默认）
4. 保存到：`frontend/src/assets/machines/podopener/2d.svg`

### 3.3 命名约定

| 部件类型 | 命名规则 | 示例 |
|---------|---------|------|
| POD / 容器 | `{name}2dLayer` | `pod2dLayer` |
| 锁扣 / 旋转件 | `{name}2d` | `latch2d` |
| 晶舟 / 显隐件 | `{name}2d` | `cassette2d` |
| 扫描线 / 动态线 | `{name}2d` | `scanLine2d` |
| 信号灯 | `{name}2d` | `signal2d` |
| UI 面板 | `{name}2d` | `uiPanel2d` |
| 手 / 机械臂 | `{name}2d` | `leftHand2d` / `rightHand2d` |

**关键原则**：`view_2d` 字段的值 = SVG 元素的 `id` 属性。

### 3.4 傻瓜模式降级

如果你完全不会画图，按这个傻瓜模式降级：

1. **全部用矩形**：不要尝试画曲线、圆角、复杂形状
2. **统一颜色**：底座 `#2a2a3a`，可动部件 `#3b82f6`，状态灯 `#10b981`
3. **文字标注**：每个部件上方用「文字工具」（`T`）写中文说明
4. **截图替代**：如果机台照片够清晰，可以直接把照片贴进 SVG 作为底图，再在上方画可动部件
5. **从 PODOPENER 复制**：打开 `podopener-2d.svg`，复制结构改名

### 3.5 阶段 1 验收标准

- [ ] SVG 文件已导出，能用浏览器打开正常显示
- [ ] 每个可动部件都有唯一的 `id` 属性
- [ ] `id` 命名与 `podopener.json` 的 `targets.xxx.view_2d` 一一对应
- [ ] 视觉上能看出是机台（不是一堆乱码矩形）

### 3.6 常见问题

**Q1：保存的 SVG 在浏览器里显示变形？**  
A：检查 Inkscape 文档属性的单位是否为 `px`，viewBox 是否正确。

**Q2：id 属性不生效？**  
A：Inkscape 的「对象属性」面板里要点击「设置」按钮才生效，光填字段不行。

**Q3：怎么知道前端能不能找到部件？**  
A：浏览器 F12 → Elements 面板 → 搜索你的 id，能搜到就说明前端加载到了。

**Q4：能不能用 PowerPoint 画？**  
A：不建议。PowerPoint 导出的 SVG 会包含大量垃圾元素，id 也会丢失。Inkscape 是最佳选择。

**Q5：能不能直接用 HTML 画？**  
A：可以，参考 `docs/VPO2D.html`（PODOPENER 2D HTML 原型），但维护成本比 SVG 高。

---

## 四、阶段 2：3D 建模（箱体拼装器优先）

### 4.1 两种方案对比

| 方案 | 学习成本 | 精度 | 适用场景 | 推荐度 |
|------|---------|------|---------|--------|
| **A. 箱体拼装器** | 1 天 | 中（够用） | 部件规则、动作简单（PODOPENER 类） | ⭐⭐⭐⭐⭐ |
| **B. Blender** | 1 周+ | 高 | 部件复杂、需要精细纹理 | ⭐⭐ |

**强烈建议**：新手先用箱体拼装器，90% 的机型够用。Blender 仅在箱体拼装器无法表达时启用。

### 4.2 方案 A：箱体拼装器（ModelEditor.vue）

#### 4.2.1 打开箱体拼装器

1. 启动项目（`npm run dev`）
2. 浏览器访问：`http://localhost:5173/#/model-editor`
3. 你会看到 3D 场景 + 右侧编辑面板

#### 4.2.2 操作步骤

**步骤 1：创建新机型项目**

1. 右侧面板点击「新建机型」
2. 输入机型 ID：`ETCH-TEL-UNITY`（举例）
3. 输入机型名称：`TEL UNITY 刻蚀机`
4. 选择视图模式：`threejs`

**步骤 2：添加部件**

每个部件由一个或多个「箱体」拼装：

1. 点击「添加部件」
2. 部件命名：`podShellGroup`（必须与 `targets.xxx.view_3d` 一致）
3. 在 3D 场景中拖拽箱体到合适位置
4. 调整尺寸：宽 / 高 / 深 / 颜色

**PODOPENER 的部件清单**：

| 部件名（view_3d） | 中文 | 形状 | 颜色 |
|------------------|------|------|------|
| `podShellGroup` | POD 外壳 | 长方体 | 浅灰 `#cccccc` |
| `latchGroup` | 锁扣 | 小长方体（旋转） | 红 `#ef4444` / 绿 `#10b981` |
| `cassetteGroup` | 晶舟 | 多个薄片叠加 | 银色 `#a0a0a0` |
| `scanLine` | 扫描线 | 细长方体 | 红 `#ef4444` |
| `signalGroup` | 信号灯组 | 圆柱 | 红 `#ef4444` |
| `uiPanel` | UI 面板 | 薄板 | 蓝 `#3b82f6` |
| `leftHandGroup` | 左手 | 长方体 | 灰 `#808080` |
| `rightHandGroup` | 右手 | 长方体 | 灰 `#808080` |

**步骤 3：命名部件（关键！）**

每个部件的 `userData.name` 必须与 `targets.xxx.view_3d` 完全一致。这是配置层查找部件的唯一依据。

**步骤 4：调整相机角度**

1. 鼠标拖拽：旋转视角
2. 滚轮：缩放
3. 右键拖拽：平移
4. 找到一个能看清所有部件的角度
5. 点击「保存相机位置」

**步骤 5：保存配置**

1. 点击「导出 JSON」
2. 文件会下载到本地
3. 把导出的 JSON 放到 `frontend/src/configs/machine-animations/{your-model}.json` 的 `parts` 字段（待扩展，目前主要用于箱体拼装记录）

### 4.3 方案 B：Blender 备选

#### 4.3.1 何时选 Blender

- 部件形状复杂（圆柱、曲面、不规则）
- 需要精细纹理（金属反光、塑料质感）
- 已有设计师能操作 Blender

#### 4.3.2 操作步骤（简述）

1. **下载并安装 Blender 3.x**：https://www.blender.org/
2. **建模**：参考 Blender 官方教程（YouTube 搜「Blender beginner tutorial」）
3. **命名部件**：在 Outliner 面板给每个 Group 命名，与 `targets.xxx.view_3d` 一致
4. **导出 GLB**：File → Export → glTF 2.0 (.glb)
5. **保存到**：`frontend/public/models/{设备类型}-{厂商}-{型号}-v{版本}.glb`

#### 4.3.3 命名规范（强制）

```
GLB 文件结构：
├── root
│   ├── base                   基座
│   ├── podShellGroup          POD 外壳
│   ├── latchGroup             锁扣
│   ├── cassetteGroup          晶舟
│   ├── scanLine               扫描线
│   ├── signalGroup            信号灯
│   ├── uiPanel                UI 面板
│   ├── leftHandGroup          左手
│   └── rightHandGroup         右手
```

**关键原则**：Blender 里的 Group 名 = `targets.xxx.view_3d` 字段值。

### 4.4 命名规范汇总（2D + 3D）

| 部件 key（targets） | 2D 命名（view_2d） | 3D 命名（view_3d） |
|---------------------|-------------------|-------------------|
| `podShell` | `pod2dLayer` | `podShellGroup` |
| `latch` | `latch2d` | `latchGroup` |
| `cassette` | `cassette2d` | `cassetteGroup` |
| `scanLine` | `scanLine2d` | `scanLine` |
| `signalGroup` | `signal2d` | `signalGroup` |
| `uiPanel` | `uiPanel2d` | `uiPanel` |
| `leftHand` | `leftHand2d` | `leftHandGroup` |
| `rightHand` | `rightHand2d` | `rightHandGroup` |

### 4.5 阶段 2 验收标准

- [ ] 3D 场景能显示所有部件
- [ ] 每个部件都有唯一的 `userData.name`（或 Blender Group 名）
- [ ] 命名与 `targets.xxx.view_3d` 完全一致
- [ ] 相机角度合适（能看清所有部件）
- [ ] （如使用 Blender）GLB 文件已保存到 `frontend/public/models/`

### 4.6 常见问题

**Q1：箱体拼装器找不到？**  
A：访问 `http://localhost:5173/#/model-editor`，或登录后从主页菜单进入。

**Q2：部件位置不对？**  
A：在箱体拼装器里用「移动工具」拖拽，或修改 JSON 配置里的 `position` 字段。

**Q3：Blender 学不会怎么办？**  
A：优先用箱体拼装器。如果必须用 Blender，请设计师帮忙或看 B 站教程。

**Q4：能不能用别人的 3D 模型？**  
A：可以，但需要重命名 Group 与 `targets` 一致。可以用 Blender 打开别人模型，重命名后重新导出。

---

## 五、阶段 3：动画设置

### 5.1 动画原语库

`_schema.json` 定义了 8 种 `action`（动画原语）：

| action | 含义 | 必填字段 | 适用场景 |
|--------|------|---------|---------|
| `translate` | 平移 | `axis` / `from` / `to` | POD 上升/下降、机械臂移动 |
| `rotate` | 旋转 | `axis` / `from` / `to` | 锁扣锁定/解锁 |
| `scale` | 缩放 | `axis` / `from` / `to` | 部件放大/缩小 |
| `flash` | 闪烁 | `color` / `duration_ms` | 信号灯闪烁、UI 确认 |
| `visibility` | 显隐 | `from` / `to`（0/1） | 晶舟显隐 |
| `color` | 变色 | `color` | 状态灯变色 |
| `scan` | 扫描 | `axis` / `from` / `to` / `color` | 扫描线上下移动 |
| `signal` | 信号波动 | `color` / `duration_ms` | 信号条波动 |

**5 种 `easing`（缓动函数）**：

| easing | 含义 | 适用 |
|--------|------|------|
| `linear` | 匀速 | 扫描、保持 |
| `easeInOut` | 先慢后快再慢 | 通用 |
| `mechanical` | 机械感（带停顿） | POD 上升下降、锁扣 |
| `easeOut` | 先快后慢 | 减速到位 |
| `easeIn` | 先慢后快 | 起步加速 |

### 5.2 配置写法

`animations` 段定义所有动画原语。每个原语的格式：

```json
"animations": {
  "pod.enter": {
    "target": "podShell",        // 必填，引用 targets 中的 key
    "action": "translate",        // 必填，8 种之一
    "sub_phase": "enter",         // 可选，阶段内分段
    "axis": "y",                  // translate/rotate/scale 必填
    "from": -400,                 // 起始值
    "to": 0,                      // 结束值
    "easing": "mechanical",       // 缓动
    "color": "#ef4444",           // flash/color/scan/signal 用
    "duration_ms": 1600,          // 持续时间（毫秒）
    "note": "POD 从入口移动到工作位"  // 备注
  }
}
```

**PODOPENER 的 14 个动画原语**（完整示例见附录 A）：

| 动画 key | target | action | 说明 |
|---------|--------|--------|------|
| `pod.enter` | podShell | translate (y) | POD 从入口移入 |
| `pod.exit` | podShell | translate (y) | POD 移出到入口 |
| `pod.up` | podShell | translate (z) | POD 上升罩住腔体 |
| `pod.down` | podShell | translate (z) | POD 下降 |
| `pod.hold_top` | podShell | translate (z) | POD 保持顶端 |
| `pod.hold_bottom` | podShell | translate (z) | POD 保持底端 |
| `latch.lock` | latch | rotate (y) | 锁扣旋转锁定 |
| `latch.unlock` | latch | rotate (y) | 锁扣旋转解锁 |
| `scan.blink` | scanLine | scan | 扫描线移动 |
| `signal.flash` | signalGroup | flash | 信号灯闪烁 |
| `signal.write` | signalGroup | signal | 信号条波动 |
| `cassette.show` | cassette | visibility | 显示晶舟 |
| `cassette.hide` | cassette | visibility | 隐藏晶舟 |
| `ui.blink` | uiPanel | flash | UI 面板闪烁 |

### 5.3 调试面板使用

调试面板（`EventAnimationDebugger.vue`）是动画设置的「试衣间」。

#### 5.3.1 打开调试面板

1. 启动项目
2. 进入任一机台详情页（如 `http://localhost:5173/#/machine/PODOPENER-1`）
3. 右侧 Tab 栏点击「调试」

#### 5.3.2 五个子 Tab 功能

**A. 时间轴**（默认）

- 三条轨道：事件轨 / 阶段轨 / 动画轨
- 事件到来时自动添加 marker
- 颜色含义：
  - 🟡 黄色 = 事件
  - 🔴 红色 = 未映射事件
  - 🟢 绿色 = 手动触发
  - 🟣 紫色 = 阶段
  - 🔵 蓝色 = 动画
- 下方「偏差检测」：期望阶段 ≠ 实际阶段时记录

**B. 事件列表**

- 表格显示最近 100 条事件
- 列：时间 / 事件 / 流程 / 期望阶段 / 实际阶段 / 动画 / 备注
- 红色行 = 偏差

**C. 手动触发**

- 14 个事件按钮（点击立即触发动画）
- 下方阶段跳转按钮（直接跳到指定阶段）
- **这是新手最常用的 Tab**——不用启动 WinForm，直接点按钮验证动画

**D. 配置编辑**

- 「开始编辑」按钮：深拷贝当前配置
- 修改阶段 `duration_ms`（输入框）
- 修改事件→阶段映射（下拉框）
- 「应用变更」：热更新到当前会话（不写文件）
- 「导出 JSON」：下载配置文件，覆盖到 `configs/machine-animations/`

**E. 动画录制**

- 选部件 → 「开始录制」→ 在 2D/3D 视图中拖拽部件 → 「停止录制」
- 自动生成动画原语配置（from / to / duration）
- ⚠️ 此功能为 M3 基础版，完整集成在 ver2.0 完善

#### 5.3.3 典型调试流程

```
1. 打开「手动触发」Tab
2. 点击 POD_PLACED 按钮 → 看 POD 是否从下方移入
3. 如果不动 → 检查 targets.podShell.view_2d 是否匹配 SVG id
4. 如果动了但位置不对 → 打开「配置编辑」修改 from / to
5. 点「应用变更」立即看效果
6. 满意后点「导出 JSON」→ 覆盖配置文件
7. 刷新页面验证
```

### 5.4 阶段 3 验收标准

- [ ] `xxx.json` 的 `animations` 段已定义所有需要的动画原语
- [ ] 每个动画的 `target` 都能在 `targets` 中找到
- [ ] 调试面板「手动触发」每个事件都能产生动画
- [ ] 动画位置 / 速度 / 颜色符合预期
- [ ] 「偏差检测」无未映射事件

### 5.5 常见问题

**Q1：点击事件按钮没反应？**  
A：检查 3 个地方：
1. `targets.xxx.view_2d` 是否与 SVG id 一致
2. `targets.xxx.view_3d` 是否与 Three.js Group 名一致
3. 浏览器 F12 控制台是否有报错

**Q2：动画方向反了？**  
A：把 `from` 和 `to` 互换。例如：
- 错：`from: 0, to: -400`（POD 向下）
- 对：`from: -400, to: 0`（POD 从下方向上移入）

**Q3：动画太快/太慢？**  
A：修改 `flows.PACKING.phases[].duration_ms`（最小 100）。

**Q4：怎么知道用哪个 axis？**  
A：
- `y` = 上下方向（垂直）
- `x` = 左右方向（水平）
- `z` = 前后方向（深度，3D 专用）

**Q5：能不能同时触发多个动画？**  
A：可以。在一个 `phase` 下绑定多个事件，每个事件触发不同的 `anim`，会并行执行。

---

## 六、阶段 4：配置注册

### 6.1 podopener.json 详解

完整配置结构（详见附录 A）：

```json
{
  "machine_type": "PODOPENER",       // 必填，与 machine_model_configs.model_id 前缀一致
  "version": "1.0.0",                // 必填，语义化版本
  "description": "...",              // 可选，描述
  
  "flows": {                         // 必填，流程定义
    "PACKING": {                     // 流程名（PACKING / UNPACKING / 自定义）
      "phases": [                    // 阶段序列
        {
          "key": "POD_PLACE",        // 阶段唯一键
          "label": "空POD放置",      // 中文显示名
          "duration_ms": 1600,       // 持续时间（≥100）
          "easing": "mechanical"     // 缓动函数
        }
        // ... 14 个阶段
      ],
      "event_to_phase": {            // 事件→阶段映射
        "POD_PLACED": {              // 事件名
          "phase": "POD_PLACE",      // 目标阶段 key
          "anim": "pod.enter",       // 触发的动画原语 key
          "note": "空POD放入"        // 备注
        }
        // ... 14 个事件映射
      }
    },
    "UNPACKING": { /* 同结构 */ }
  },
  
  "animations": {                    // 必填，动画原语库
    "pod.enter": {
      "target": "podShell",          // 目标部件 key（引用 targets）
      "action": "translate",         // 动画类型（8 种之一）
      "axis": "y",                   // 轴
      "from": -400,                  // 起始值
      "to": 0,                       // 结束值
      "easing": "mechanical",
      "note": "..."
    }
    // ... 14 个动画原语
  },
  
  "targets": {                       // 必填，部件绑定
    "podShell": {
      "view_2d": "pod2dLayer",       // SVG 元素 id（不带 #）
      "view_3d": "podShellGroup",    // Three.js Group userData 标识
      "desc": "POD外壳（可移动）"
    }
    // ... 8 个部件
  }
}
```

### 6.2 后端注册（machine_model_configs 表）

新机型必须在后端注册，前端才能识别。

#### 6.2.1 通过 API 注册（推荐）

```bash
# 启动后端后，调用 POST /api/models
curl -X POST http://localhost:8002/api/models \
  -H "Content-Type: application/json" \
  -d '{
    "model_id": "ETCH-TEL-UNITY",
    "model_name": "TEL UNITY 刻蚀机",
    "vendor": "TEL",
    "process_type": "ETCH",
    "version": "1.0",
    "view_mode": "threejs",
    "description": "TEL DRM UNITY 刻蚀机精细 3D 模型",
    "views_config_json": "{\"view_3d\":{\"type\":\"threejs\"}}",
    "parts_config_json": "[]",
    "state_mapping_json": "[]",
    "hotspots_config_json": "[]"
  }'
```

#### 6.2.2 通过 seed_data.py 注册

编辑 `backend/seed_data.py`，在 `init_seed_data()` 函数中添加：

```python
# 添加机型配置
db.add(MachineModelConfig(
    model_id="ETCH-TEL-UNITY",
    model_name="TEL UNITY 刻蚀机",
    vendor="TEL",
    process_type="ETCH",
    version="1.0",
    view_mode="threejs",
    views_config_json='{"view_3d":{"type":"threejs"}}',
))

# 添加机台实例
db.add(Machine(
    id="T01",
    model="TEL DRM UNITY",
    name="刻蚀机 T01",
    line=1,
    floor=3,
    process_type="ETCH",
    state="idle",
))
```

#### 6.2.3 view_mode 可选值

| view_mode | 视图组件 | 适用机型 |
|-----------|---------|---------|
| `threejs` | MachineModel3D.vue | 3D 精细模型（DRM UNITY） |
| `isometric` | MachineIsoView.vue | 2.5D 等角（OXE） |
| `vpo` | MachineVpoView.vue | PODOPENER 2D |
| `vpo3d` / `vpo-3d` | MachineVpo3DView.vue | PODOPENER 3D |
| `svg` | MachineModel2D.vue | 通用 2D |
| `hybrid` | 2D + 3D 切换 | 通用 |

### 6.3 视图路由（前端自动）

前端 `MachineDetail.vue` 会根据机台的 `view_mode` 自动选择视图组件：

```javascript
function resolveViewMode(machineModel) {
  const vm = modelStore.getViewMode(machineModel)
  if (vm === 'vpo' || vm === 'svg-vpo' || vm === 'vpo3d' || vm === 'vpo-3d') {
    // PODOPENER 系列
    const cfg = modelStore.getModelById(...)
    if (cfg?.views_config?.view_3d?.type === 'vpo') return 'vpo3d'
    return 'vpo'
  }
  if (vm === 'isometric' || vm === 'iso') return 'iso'
  if (vm === 'hybrid') return '2d'
  if (vm === 'svg') return '2d'
  return '3d'
}
```

**新机型接入时**：

- 如果用现有视图类型（如 `threejs` / `vpo`）→ **不需要改前端代码**
- 如果是新视图类型（如 `conveyor` 传送带）→ 需要新建 `Machine{YourModel}View.vue` 组件，并在 `MachineDetail.vue` 的 `availableViews` computed 中注册

### 6.4 阶段 4 验收标准

- [ ] `xxx.json` 配置文件已保存到 `frontend/src/configs/machine-animations/`
- [ ] `machine_model_configs` 表中有对应记录
- [ ] `machines` 表中有机台实例（model_id 匹配）
- [ ] 前端访问机台详情页能自动选择正确视图
- [ ] 浏览器 F12 控制台无「未找到配置文件」错误

### 6.5 常见问题

**Q1：前端报「未找到机台类型的配置文件」？**  
A：检查 `xxx.json` 文件名是否全小写。`useAnimationConfig.js` 用 `type.toLowerCase()` 查找。

**Q2：机台详情页空白？**  
A：检查 `machine_model_configs.view_mode` 是否为合法值（参考 6.2.3）。

**Q3：怎么测试配置是否生效？**  
A：进入机台详情页 → 右侧「调试」Tab → 「手动触发」→ 点事件按钮，看动画是否触发。

**Q4：能不能不改后端代码注册机型？**  
A：可以，用 `POST /api/models` API 注册，重启后端后失效。若要永久生效，需要改 `seed_data.py`。

---

## 七、阶段 5：事件绑定

### 7.1 事件清单模板

每个机型必须有一份事件清单，格式如下：

```markdown
## {机型名} 事件清单

### 流程 1：{流程名}（如 PACKING）

| 序号 | 事件名 | 类型 | 说明 | 典型耗时 | 对应阶段 | 动画原语 |
|------|--------|------|------|---------|---------|---------|
| 1 | POD_PLACED | VFEI | POD放置到位 | 10s | POD_PLACE | pod.enter |
| 2 | COMPLETED_PORT_LOCK | VFEI | 端口锁定完成 | 8s | POD_LOCK | latch.lock |
| ... | ... | ... | ... | ... | ... | ... |

### 流程 2：{流程名}（如 UNPACKING）

| 序号 | 事件名 | ... |
|------|--------|-----|

### 报警事件

| alarm_id | 报警文本 | 严重度 | 说明 |
|----------|---------|-------|------|
| 9004 | POD NOT FOUND | crit | 未检测到POD |
| ... | ... | ... | ... |
```

PODOPENER 完整事件清单见附录 B。

### 7.2 对接方式

#### 7.2.1 方式一：WinForm 模拟器（开发测试用）

**适用**：开发阶段、Demo、新机型验证

**操作步骤**：

1. 打开 `winform_simulator.py`
2. 修改 `PODOPENER_PACKING_EVENTS` 和 `PODOPENER_UNPACKING_EVENTS` 数组，替换为新机型的事件
3. 修改 `tool_id` 为新机台 ID
4. 运行：`python winform_simulator.py`
5. GUI 界面点击按钮 → 写入 `DT_EVENT_RAW` 表
6. `db_poller.py` 自动轮询并推送前端

**代码示例**（修改 `winform_simulator.py`）：

```python
# 替换为新机型事件
NEW_MODEL_PACKING_EVENTS = [
    {"event_name": "WAFER_IN", "event_type": "VFEI", "note": "晶圆进入"},
    {"event_name": "PROCESS_START", "event_type": "VFEI", "note": "加工开始"},
    # ...
]

# 修改 tool_id
TOOL_ID = "T01"  # 新机台 ID
```

#### 7.2.2 方式二：TIBRV 真实事件（生产用，ver2）

**适用**：生产环境

**流程**：

```
TIBRV 消息总线
   ↓
世庆 EAP 服务接收
   ↓
解析为标准化事件
   ↓
写入 DT_EVENT_RAW 表
   ↓
db_poller.py 轮询
   ↓
WebSocket 推送前端
```

**接入步骤**（ver2 计划）：

1. 与世庆确认 TIBRV 消息格式
2. 部署 TIBRV → Redis/MQTT 桥接服务
3. 配置 `backend/config.py` 启用 TIBRV 监听
4. 关闭 `SIMULATION_ENABLED`
5. 验证真实事件触发动画

#### 7.2.3 方式三：直接写 DB（临时测试用）

**适用**：快速验证

**操作**：

```sql
-- 直接插入一条测试事件
INSERT INTO dt_event_raw (raw_id, tool_id, source_system, source_message_id, 
                          received_ts_utc, event_ts_utc, payload_json, parse_status)
VALUES (
  'test-' || SYS_GUID(),
  'PODOPENER-1',
  'MANUAL',
  'manual-001',
  TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
  TO_CHAR(SYSTIMESTAMP, 'YYYY-MM-DD HH24:MI:SS'),
  '{"event_name": "POD_PLACED", "event_type": "VFEI", "lot_id": "LOT001"}',
  'NEW'
);
COMMIT;
```

写入后 1 秒内前端会收到事件并触发动画。

#### 7.2.4 方式四：API 接收

**适用**：第三方系统对接

调用 `POST /api/rvmessages`：

```bash
curl -X POST http://localhost:8002/api/rvmessages \
  -H "Content-Type: application/json" \
  -d '{
    "tool_id": "PODOPENER-1",
    "event_name": "POD_PLACED",
    "event_type": "VFEI",
    "payload": {"lot_id": "LOT001", "port_id": "1"}
  }'
```

### 7.3 验证流程（端到端测试）

#### 7.3.1 单事件验证

1. 启动后端（`python main.py`）
2. 启动前端（`npm run dev`）
3. 打开机台详情页：`http://localhost:5173/#/machine/PODOPENER-1`
4. 右侧 Tab 切到「调试」→「手动触发」
5. 逐个点击 14 个事件按钮
6. 检查每个事件是否触发对应动画
7. 在「事件列表」Tab 检查「期望阶段」与「实际阶段」是否一致

#### 7.3.2 完整流程验证

1. 启动 WinForm 模拟器：`python winform_simulator.py`
2. 选择流程：PACKING
3. 点击「自动执行」
4. 前端观察 14 个事件按顺序触发，动画连贯
5. 重复 UNPACKING 流程

#### 7.3.3 历史回放验证

1. 生成历史数据：`python backend/gen_podopener_history.py`
2. 前端切换到「回放」模式
3. 选择日期
4. 拖拽时间轴或点击事件
5. 验证动画与历史事件一致

#### 7.3.4 报警事件验证

1. WinForm 模拟器点击「报警模拟」按钮
2. 验证前端：
   - 告警列表出现新告警
   - 机台状态灯变红
   - （如有）报警闪烁动画

### 7.4 阶段 5 验收标准

- [ ] 事件清单文档已编写完成
- [ ] WinForm 模拟器已适配新机型事件
- [ ] 14 个（或对应数量）事件端到端测试通过
- [ ] 「调试」面板「事件列表」无偏差记录
- [ ] 历史回放可正常播放
- [ ] 报警事件能触发告警 UI

### 7.5 常见问题

**Q1：WinForm 写入 DB 报 ORA-00001 唯一约束冲突？**  
A：WinForm 已修复此问题——启动时从 DB 读取最大 raw_id 作为初始值。如果仍报错，清空 `DT_EVENT_RAW` 表后重试。

**Q2：事件到了前端但动画不触发？**  
A：检查 3 个地方：
1. `event_to_phase` 是否包含该事件名（注意大小写）
2. `targets.xxx.view_2d` / `view_3d` 是否匹配
3. 浏览器 F12 控制台是否有报错

**Q3：报警事件怎么绑定？**  
A：报警事件不需要绑定到阶段，`db_poller.py` 会自动识别 `EC_ALARM_REPORT` 事件并分类为 `alarm`，前端告警组件会自动显示。

**Q4：能不能同时触发多个事件？**  
A：可以，但建议按时间顺序触发（间隔 ≥ 500ms），避免动画冲突。

---

## 八、阶段 6：上线

### 8.1 上线 Checklist

#### 8.1.1 功能 Checklist

- [ ] 2D 视图：所有可动部件正确显示，id 命名规范
- [ ] 3D 视图：所有部件正确显示，命名规范
- [ ] 配置文件：`xxx.json` 已保存，通过 Schema 校验
- [ ] 后端注册：`machine_model_configs` 表有记录
- [ ] 机台实例：`machines` 表有记录
- [ ] 事件清单：14+ 个事件全部映射到阶段
- [ ] 动画原语：所有事件对应的动画已定义
- [ ] 手动触发：调试面板 14 个事件按钮可触发动画
- [ ] WinForm 模拟器：可驱动新机型事件
- [ ] 历史回放：可加载历史数据并播放
- [ ] 报警事件：可触发告警 UI

#### 8.1.2 性能 Checklist

- [ ] 前端加载机台详情页 ≤ 2 秒
- [ ] 事件触发动画延迟 ≤ 1 秒
- [ ] 浏览器内存占用稳定（无泄漏）
- [ ] `npm run build` 无错误

#### 8.1.3 部署 Checklist

- [ ] 配置文件已提交到 Git
- [ ] SVG / GLB 资源已提交到 Git
- [ ] `seed_data.py` 已更新（新机型注册）
- [ ] `winform_simulator.py` 已适配（如需）
- [ ] `deploy.bat` 一键部署成功
- [ ] 内网环境验证通过

#### 8.1.4 文档 Checklist

- [ ] 事件清单文档已编写
- [ ] `变更更改版记录.md` 已追加变更记录
- [ ] `开发进度管控.md` 已更新进度
- [ ] 业务流程参考文档已归档到 `docs/`

### 8.2 文档模板

#### 8.2.1 新机型接入完成报告模板

```markdown
# {机型名} 接入完成报告

## 1. 基本信息
- 机型 ID：{model_id}
- 机型名称：{model_name}
- 厂商：{vendor}
- 工艺类型：{process_type}
- 视图模式：{view_mode}
- 接入日期：{date}
- 负责人：{name}

## 2. 完成功能
- [x] 2D 视图（SVG）
- [x] 3D 视图（箱体拼装 / Blender）
- [x] 配置文件（xxx.json）
- [x] 事件映射（N 个事件）
- [x] 动画原语（M 个）
- [x] WinForm 模拟器适配
- [x] 历史数据生成
- [x] 端到端测试通过

## 3. 事件清单
（参考附录 B 格式）

## 4. 已知问题
- 问题 1：...
- 问题 2：...

## 5. 后续优化
- 优化 1：...
- 优化 2：...
```

### 8.3 上线流程

```
1. 完成所有 Checklist 项目
2. 提交代码到 Git（feature/{your-model} 分支）
3. 发起 Code Review
4. 合并到 ver{X} 分支
5. 在测试环境部署验证
6. 通知相关人员进行 UAT
7. UAT 通过后合并到 main 分支
8. 在生产环境部署
9. 编写完成报告
```

---

## 九、给初学者的 7 天培训大纲

### Day 1：环境搭建 + 项目熟悉

**上午**：
- 安装 Python 3.10+ / Node.js 16+ / VSCode / Inkscape
- 克隆项目代码：`git clone <repo>`
- 运行 `deploy.bat` 一键部署
- 浏览项目结构（参考《系统架构说明书.md》）

**下午**：
- 启动后端：`cd backend && python main.py`
- 启动前端：`cd frontend && npm run dev`
- 访问 `http://localhost:5173`，浏览各页面
- 进入 PODOPENER-1 机台详情页，观察 2D/3D 视图
- 启动 WinForm 模拟器，点击按钮观察动画

**作业**：在文档里画出项目目录结构，标注每个目录的作用。

### Day 2：PODOPENER 案例研读

**上午**：
- 阅读 `frontend/src/configs/machine-animations/podopener.json`（完整配置）
- 对照附录 A 理解每个字段含义
- 阅读 `_schema.json` 理解校验规则

**下午**：
- 阅读 `frontend/src/composables/useAnimationConfig.js`（加载器）
- 理解 `getPhaseByEvent` / `getAnimation` / `getTarget` 三个核心方法
- 在浏览器 F12 控制台手动调用这些方法

**作业**：用一句话解释「事件 → 阶段 → 动画」三层映射的关系。

### Day 3：2D 绘图实操

**上午**：
- Inkscape 基础教程（矩形 / 圆形 / 文字 / 选择 / 变换）
- 打开现有 `podopener-2d.svg`，研究结构

**下午**：
- 用 Inkscape 画一个简单机台的 2D 图（如一台传送带）
- 给每个部件命名 id
- 导出 SVG，放到 `frontend/src/assets/machines/`

**作业**：提交一份自己画的 SVG 文件，至少包含 5 个有 id 的部件。

### Day 4：3D 建模实操

**上午**：
- 打开箱体拼装器（`/model-editor`）
- 学习添加部件、调整尺寸、设置颜色
- 研究现有 PODOPENER 3D 视图的部件命名

**下午**：
- 用箱体拼装器搭一个简单机台的 3D 模型
- 给每个部件设置 `userData.name`
- 调整相机角度

**作业**：提交一份箱体拼装配置 JSON。

### Day 5：动画配置实操

**上午**：
- 学习 8 种 action（translate / rotate / scale / flash / visibility / color / scan / signal）
- 学习 5 种 easing
- 在 PODOPENER 配置上手动修改 `from` / `to`，观察效果

**下午**：
- 打开调试面板（「调试」Tab）
- 使用「手动触发」逐个验证事件
- 使用「配置编辑」热修改 `duration_ms`
- 使用「导出 JSON」下载配置

**作业**：为 Day 3/4 的机台编写 `xxx.json` 配置文件，至少定义 3 个动画原语。

### Day 6：事件绑定 + WinForm 适配

**上午**：
- 学习事件清单模板
- 修改 `winform_simulator.py` 适配自己的机型
- 启动 WinForm 模拟器写入 DB

**下午**：
- 端到端测试：WinForm → DB → 轮询 → WS → 前端动画
- 学习历史回放（生成测试数据 + 回放）
- 学习报警事件处理

**作业**：完成自己机型的端到端测试，提交测试报告。

### Day 7：综合实战 + 上线

**上午**：
- 完成所有阶段验收
- 修复发现的问题
- 编写事件清单文档

**下午**：
- 走上线 Checklist
- 编写接入完成报告
- Code Review + 合并代码

**作业**：提交完整的新机型接入 PR，包含：
- 配置文件 `xxx.json`
- SVG / GLB 资源
- `seed_data.py` 修改
- `winform_simulator.py` 修改（如需）
- 事件清单文档
- 接入完成报告

---

## 十、扩展性设计（应对部件越来越多的机型）

### 10.1 问题背景

随着机型增多，部件数量爆炸：

- PODOPENER：8 个部件
- TEL DRM UNITY：~15 个部件（4 腔体 + 机械臂 + SMIF + 控制面板 + 气体面板 + ...）
- 复杂机型：可能 50+ 部件

如果还用扁平的 `targets` 字典，会变得难以维护。

### 10.2 三层解耦设计

```
┌────────────────────────────────────────────────┐
│  层 1：部件命名注册表（targets）                  │
│  统一管理所有部件的 2D/3D 引用                    │
│  { "podShell": { view_2d, view_3d, desc } }     │
└────────────────┬───────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────┐
│  层 2：动画原语库（animations）                   │
│  统一管理所有动画参数                             │
│  { "pod.enter": { target, action, axis, ... } } │
└────────────────┬───────────────────────────────┘
                 │
┌────────────────▼───────────────────────────────┐
│  层 3：事件-阶段-动画映射（flows）                │
│  统一管理业务流程                                 │
│  flows.PACKING.event_to_phase                   │
└────────────────────────────────────────────────┘
```

**优势**：

1. **部件独立**：新增部件只需在 `targets` 加一行，不影响动画和事件
2. **动画复用**：同一个动画原语可被多个事件引用（如 `ui.blink` 被 `UI_CONFIRM` 和 `ACK_UI_DOUBLECHECK` 共用）
3. **流程独立**：同一份动画原语可服务于不同流程（PACKING / UNPACKING / 自定义流程）

### 10.3 部件命名注册表

为应对复杂机型，建议建立「部件命名注册表」（在 `_schema.json` 扩展）：

```json
"target_categories": {
  "motion": {
    "desc": "运动部件",
    "naming_pattern": "{name}Group",
    "examples": ["podShellGroup", "latchGroup", "armGroup"]
  },
  "indicator": {
    "desc": "指示部件（灯/屏幕）",
    "naming_pattern": "{name}Indicator",
    "examples": ["signalIndicator", "statusLight"]
  },
  "structure": {
    "desc": "结构部件（不可动）",
    "naming_pattern": "{name}Base",
    "examples": ["baseGroup", "frameGroup"]
  }
}
```

**注册表规则**：

1. 每个部件必须属于一个类别
2. 同类别部件命名一致（`{name}Group` / `{name}Indicator` / `{name}Base`）
3. 新增部件类别需更新注册表

### 10.4 动画原语可扩展

如果 8 种 action 不够用，可以扩展：

#### 10.4.1 扩展步骤

1. 在 `_schema.json` 的 `action` 枚举中新增值（如 `sequence` 序列动画）
2. 在视图组件中实现对应渲染逻辑（如 `MachineVpoView.vue` 的 `applyAnimation` 函数）
3. 在 `podopener.json` 的 `animations` 中使用新 action

#### 10.4.2 扩展示例

```json
// _schema.json
"action": {
  "type": "string",
  "enum": ["translate", "rotate", "scale", "flash", "visibility", "color", "scan", "signal", "sequence"]
}

// podopener.json
"animations": {
  "pod.complex_move": {
    "target": "podShell",
    "action": "sequence",
    "steps": [
      { "action": "translate", "axis": "y", "from": -400, "to": 0, "duration_ms": 800 },
      { "action": "translate", "axis": "z", "from": 0, "to": 680, "duration_ms": 800 }
    ],
    "note": "POD 先 Y 轴移入再 Z 轴上升"
  }
}
```

#### 10.4.3 视图组件实现

```javascript
// MachineVpoView.vue
function applyAnimation(animDef, target) {
  switch (animDef.action) {
    case 'translate': /* ... */; break
    case 'rotate': /* ... */; break
    // ...
    case 'sequence':
      animDef.steps.forEach(step => applyAnimation(step, target))
      break
  }
}
```

### 10.5 多流程支持

`flows` 字段不限于 `PACKING` / `UNPACKING`，可以自定义：

```json
"flows": {
  "PACKING": { /* 穿入流程 */ },
  "UNPACKING": { /* 脱出流程 */ },
  "MAINTENANCE": { /* 维护流程 */ },
  "CLEANING": { /* 清洗流程 */ }
}
```

调试面板会自动在下拉框显示所有流程。

### 10.6 配置版本管理

`version` 字段支持语义化版本：

- `1.0.0` → 初始版本
- `1.1.0` → 新增动画原语（向后兼容）
- `1.0.1` → 修复参数（向后兼容）
- `2.0.0` → 破坏性变更（如重命名 targets）

建议配合 Git 进行配置版本管理，每次修改提交 commit。

---

## 附录 A：完整 podopener.json 配置示例

> 来源：`frontend/src/configs/machine-animations/podopener.json`

```json
{
  "machine_type": "PODOPENER",
  "version": "1.0.0",
  "description": "VPO 2200 PODOPENER 穿入/脱出流程统一动画配置（2D/3D 共用）",
  "flows": {
    "PACKING": {
      "phases": [
        { "key": "POD_PLACE",         "label": "空POD放置",   "duration_ms": 1600, "easing": "mechanical" },
        { "key": "POD_LOCK",          "label": "POD锁定",     "duration_ms": 960,  "easing": "mechanical" },
        { "key": "READ_TAG",          "label": "扫描标签",    "duration_ms": 1920, "easing": "linear" },
        { "key": "BATCH_CONFIRM",     "label": "信号确认",    "duration_ms": 1280, "easing": "linear" },
        { "key": "POD_UP",            "label": "POD上升",     "duration_ms": 2240, "easing": "mechanical" },
        { "key": "POD_REACH_STAGE",   "label": "POD到顶",     "duration_ms": 640,  "easing": "linear" },
        { "key": "CST_PLACE",         "label": "放入晶舟",    "duration_ms": 1920, "easing": "mechanical" },
        { "key": "UI_CONFIRM",        "label": "UI确认",      "duration_ms": 800,  "easing": "linear" },
        { "key": "POD_DOWN",          "label": "POD下降",     "duration_ms": 2240, "easing": "mechanical" },
        { "key": "POD_REACH_POS",     "label": "POD到底",     "duration_ms": 640,  "easing": "linear" },
        { "key": "UI_DOUBLECHECK",    "label": "二次确认",    "duration_ms": 800,  "easing": "linear" },
        { "key": "WRITE_TAG",         "label": "写入标签",    "duration_ms": 1600, "easing": "linear" },
        { "key": "POD_UNLOCK",        "label": "POD解锁",     "duration_ms": 960,  "easing": "mechanical" },
        { "key": "POD_REMOVE",        "label": "满POD移走",   "duration_ms": 1600, "easing": "mechanical" }
      ],
      "event_to_phase": {
        "POD_PLACED":            { "phase": "POD_PLACE",        "anim": "pod.enter",         "note": "空POD放入" },
        "COMPLETED_PORT_LOCK":   { "phase": "POD_LOCK",         "anim": "latch.lock",        "note": "POD锁定完成" },
        "READ_BATTERY":          { "phase": "READ_TAG",         "anim": "scan.blink",        "note": "读取RFID电池" },
        "READ_TAG":              { "phase": "READ_TAG",         "anim": "scan.blink",        "note": "扫描标签" },
        "BATCH_INFO_FROM_ECUI":  { "phase": "BATCH_CONFIRM",    "anim": "signal.flash",      "note": "批次信息确认" },
        "OPEN_POD":              { "phase": "POD_UP",           "anim": "pod.up",            "note": "POD门打开，POD上升" },
        "REACH_STAGE":           { "phase": "POD_REACH_STAGE",  "anim": "pod.hold_top",      "note": "POD到达顶端" },
        "UI_CONFIRM":            { "phase": "UI_CONFIRM",       "anim": "ui.blink",          "note": "操作员UI确认" },
        "CLOSE_POD":             { "phase": "POD_DOWN",         "anim": "pod.down",          "note": "POD门关闭，POD下降罩住" },
        "ACK_UI_DOUBLECHECK":    { "phase": "UI_DOUBLECHECK",   "anim": "ui.blink",          "note": "二次确认" },
        "REACH_POS":             { "phase": "POD_REACH_POS",    "anim": "pod.hold_bottom",   "note": "POD到达底端" },
        "WRITE_TAG":             { "phase": "WRITE_TAG",        "anim": "signal.write",      "note": "写入RFID标签" },
        "COMPLETED_PORT_UNLOCK": { "phase": "POD_UNLOCK",       "anim": "latch.unlock",      "note": "POD解锁完成" },
        "POD_REMOVED":           { "phase": "POD_REMOVE",       "anim": "pod.exit",          "note": "满POD移走" }
      }
    },
    "UNPACKING": {
      "phases": [
        { "key": "POD_PLACE",         "label": "满POD放置",   "duration_ms": 1600, "easing": "mechanical" },
        { "key": "POD_LOCK",          "label": "POD锁定",     "duration_ms": 960,  "easing": "mechanical" },
        { "key": "READ_TAG",          "label": "扫描标签",    "duration_ms": 1920, "easing": "linear" },
        { "key": "BATCH_CONFIRM",     "label": "信号确认",    "duration_ms": 1280, "easing": "linear" },
        { "key": "POD_UP",            "label": "POD上升",     "duration_ms": 2240, "easing": "mechanical" },
        { "key": "POD_REACH_STAGE",   "label": "POD到顶",     "duration_ms": 640,  "easing": "linear" },
        { "key": "CST_REMOVE",        "label": "移走晶舟",    "duration_ms": 1920, "easing": "mechanical" },
        { "key": "POD_DOWN",          "label": "POD下降",     "duration_ms": 2240, "easing": "mechanical" },
        { "key": "POD_REACH_POS",     "label": "POD到底",     "duration_ms": 640,  "easing": "linear" },
        { "key": "WRITE_TAG",         "label": "写入标签",    "duration_ms": 1600, "easing": "linear" },
        { "key": "POD_UNLOCK",        "label": "POD解锁",     "duration_ms": 960,  "easing": "mechanical" },
        { "key": "POD_REMOVE",        "label": "空POD移走",   "duration_ms": 1600, "easing": "mechanical" }
      ],
      "event_to_phase": {
        "POD_PLACED":            { "phase": "POD_PLACE",        "anim": "pod.enter",         "note": "满POD放入" },
        "COMPLETED_PORT_LOCK":   { "phase": "POD_LOCK",         "anim": "latch.lock",        "note": "POD锁定完成" },
        "READ_BATTERY":          { "phase": "READ_TAG",         "anim": "scan.blink",        "note": "读取RFID电池" },
        "READ_TAG":              { "phase": "READ_TAG",         "anim": "scan.blink",        "note": "扫描标签" },
        "BATCH_INFO_FROM_ECUI":  { "phase": "BATCH_CONFIRM",    "anim": "signal.flash",      "note": "批次信息确认" },
        "OPEN_POD":              { "phase": "POD_UP",           "anim": "pod.up",            "note": "POD上升" },
        "REACH_STAGE":           { "phase": "POD_REACH_STAGE",  "anim": "pod.hold_top",      "note": "POD到达顶端" },
        "UI_CONFIRM":            { "phase": "CST_REMOVE",       "anim": "cassette.hide",     "note": "移走晶舟" },
        "CLOSE_POD":             { "phase": "POD_DOWN",         "anim": "pod.down",          "note": "POD下降" },
        "ACK_UI_DOUBLECHECK":    { "phase": "POD_REACH_POS",    "anim": "pod.hold_bottom",   "note": "POD到底" },
        "REACH_POS":             { "phase": "POD_REACH_POS",    "anim": "pod.hold_bottom",   "note": "POD到底" },
        "WRITE_TAG":             { "phase": "WRITE_TAG",        "anim": "signal.write",      "note": "写入RFID标签" },
        "COMPLETED_PORT_UNLOCK": { "phase": "POD_UNLOCK",       "anim": "latch.unlock",      "note": "POD解锁完成" },
        "POD_REMOVED":           { "phase": "POD_REMOVE",       "anim": "pod.exit",          "note": "空POD移走" }
      }
    }
  },
  "animations": {
    "pod.enter": {
      "target": "podShell",
      "action": "translate",
      "sub_phase": "enter",
      "axis": "y",
      "from": -400,
      "to": 0,
      "easing": "mechanical",
      "note": "POD从入口移动到工作位（前半段Y轴，后半段Z轴）"
    },
    "pod.exit": {
      "target": "podShell",
      "action": "translate",
      "sub_phase": "exit",
      "axis": "y",
      "from": 0,
      "to": -400,
      "easing": "mechanical",
      "note": "POD从工作位移出到入口"
    },
    "pod.up": {
      "target": "podShell",
      "action": "translate",
      "axis": "z",
      "from": 148,
      "to": 680,
      "easing": "mechanical",
      "note": "POD沿Z轴上升罩住腔体"
    },
    "pod.down": {
      "target": "podShell",
      "action": "translate",
      "axis": "z",
      "from": 680,
      "to": 148,
      "easing": "mechanical",
      "note": "POD沿Z轴下降"
    },
    "pod.hold_top": {
      "target": "podShell",
      "action": "translate",
      "axis": "z",
      "from": 680,
      "to": 680,
      "easing": "linear",
      "note": "POD保持在顶端"
    },
    "pod.hold_bottom": {
      "target": "podShell",
      "action": "translate",
      "axis": "z",
      "from": 148,
      "to": 148,
      "easing": "linear",
      "note": "POD保持在底端"
    },
    "latch.lock": {
      "target": "latch",
      "action": "rotate",
      "axis": "y",
      "from": 35,
      "to": 0,
      "color": "#ef4444",
      "easing": "mechanical",
      "note": "锁扣旋转锁定，颜色变红"
    },
    "latch.unlock": {
      "target": "latch",
      "action": "rotate",
      "axis": "y",
      "from": 0,
      "to": 35,
      "color": "#10b981",
      "easing": "mechanical",
      "note": "锁扣旋转解锁，颜色变绿"
    },
    "scan.blink": {
      "target": "scanLine",
      "action": "scan",
      "axis": "y",
      "from": 20,
      "to": -20,
      "color": "#ef4444",
      "duration_ms": 1920,
      "note": "扫描线在POD标签处上下移动"
    },
    "signal.flash": {
      "target": "signalGroup",
      "action": "flash",
      "color": "#ef4444",
      "duration_ms": 1280,
      "note": "信号灯闪烁（批次确认）"
    },
    "signal.write": {
      "target": "signalGroup",
      "action": "signal",
      "color": "#ef4444",
      "duration_ms": 1600,
      "note": "信号条波动（写入RFID）"
    },
    "cassette.show": {
      "target": "cassette",
      "action": "visibility",
      "from": 0,
      "to": 1,
      "note": "显示晶舟"
    },
    "cassette.hide": {
      "target": "cassette",
      "action": "visibility",
      "from": 1,
      "to": 0,
      "note": "隐藏晶舟"
    },
    "ui.blink": {
      "target": "uiPanel",
      "action": "flash",
      "color": "#3b82f6",
      "duration_ms": 800,
      "note": "UI面板闪烁确认"
    }
  },
  "targets": {
    "podShell": {
      "view_2d": "pod2dLayer",
      "view_3d": "podShellGroup",
      "desc": "POD外壳（可移动）"
    },
    "latch": {
      "view_2d": "latch2d",
      "view_3d": "latchGroup",
      "desc": "锁扣（旋转锁定/解锁）"
    },
    "cassette": {
      "view_2d": "cassette2d",
      "view_3d": "cassetteGroup",
      "desc": "晶舟（显隐）"
    },
    "scanLine": {
      "view_2d": "scanLine2d",
      "view_3d": "scanLine",
      "desc": "扫描线"
    },
    "signalGroup": {
      "view_2d": "signal2d",
      "view_3d": "signalGroup",
      "desc": "信号灯/信号条"
    },
    "uiPanel": {
      "view_2d": "uiPanel2d",
      "view_3d": "uiPanel",
      "desc": "UI操作面板"
    },
    "leftHand": {
      "view_2d": "leftHand2d",
      "view_3d": "leftHandGroup",
      "desc": "左手模型（POD移动时显示）"
    },
    "rightHand": {
      "view_2d": "rightHand2d",
      "view_3d": "rightHandGroup",
      "desc": "右手模型（POD移动时显示）"
    }
  }
}
```

---

## 附录 B：14 个事件清单（PACKING / UNPACKING 各 14 个）

> 注：PODOPENER 实际为 **PACKING 14 个 + UNPACKING 6 个**，共 20 个事件。下表为 PACKING 完整 14 个 + UNPACKING 完整 6 个。任务描述中提到的「14 个事件」指 PACKING 流程。

### B.1 PACKING 穿入流程（14 个事件）

| 序号 | 事件名 | 类型 | 说明 | 典型耗时 | 对应阶段 | 动画原语 |
|------|--------|------|------|---------|---------|---------|
| 1 | POD_PLACED | VFEI | POD放置到位 | 10s | POD_PLACE | pod.enter |
| 2 | COMPLETED_PORT_LOCK | VFEI | 端口锁定完成 | 8s | POD_LOCK | latch.lock |
| 3 | READ_BATTERY | VFEI | 读取电池状态 | 5s | READ_TAG | scan.blink |
| 4 | READ_TAG | VFEI | 读取RFID标签 | 8s | READ_TAG | scan.blink |
| 5 | BATCH_INFO_FROM_ECUI | HOST | 获取批次信息 | 12s | BATCH_CONFIRM | signal.flash |
| 6 | OPEN_POD | VFEI | 打开POD盖 | 10s | POD_UP | pod.up |
| 7 | REACH_STAGE | VFEI | 机械臂到达平台 | 15s | POD_REACH_STAGE | pod.hold_top |
| 8 | UI_CONFIRM | HOST | 操作员确认 | 20s | UI_CONFIRM | ui.blink |
| 9 | CLOSE_POD | VFEI | 关闭POD盖 | 10s | POD_DOWN | pod.down |
| 10 | ACK_UI_DOUBLECHECK | HOST | 二次确认 | 15s | UI_DOUBLECHECK | ui.blink |
| 11 | REACH_POS | VFEI | 机械臂到位 | 12s | POD_REACH_POS | pod.hold_bottom |
| 12 | WRITE_TAG | VFEI | 写入RFID标签 | 8s | WRITE_TAG | signal.write |
| 13 | COMPLETED_PORT_UNLOCK | VFEI | 端口解锁完成 | 6s | POD_UNLOCK | latch.unlock |
| 14 | POD_REMOVED | VFEI | POD移走 | 5s | POD_REMOVE | pod.exit |

### B.2 UNPACKING 脱出流程（6 个事件）

| 序号 | 事件名 | 类型 | 说明 | 典型耗时 | 对应阶段 | 动画原语 |
|------|--------|------|------|---------|---------|---------|
| 1 | UI_CONFIRM | HOST | 操作员确认 | 15s | CST_REMOVE | cassette.hide |
| 2 | CLOSE_POD | VFEI | 关闭POD盖 | 10s | POD_DOWN | pod.down |
| 3 | REACH_POS | VFEI | 机械臂到位 | 12s | POD_REACH_POS | pod.hold_bottom |
| 4 | WRITE_TAG | VFEI | 写入RFID标签 | 8s | WRITE_TAG | signal.write |
| 5 | COMPLETED_PORT_UNLOCK | VFEI | 端口解锁完成 | 6s | POD_UNLOCK | latch.unlock |
| 6 | POD_REMOVED | VFEI | POD移走 | 5s | POD_REMOVE | pod.exit |

> 说明：UNPACKING 配置中 `event_to_phase` 包含全部 14 个事件名（与 PACKING 共用事件名空间），但实际脱出流程只走其中 6 个。

### B.3 报警事件（5 种）

| alarm_id | 报警文本 | 严重程度 | 说明 |
|----------|---------|---------|------|
| 0201 | 电池电压异常 | warn | 电池电压异常 |
| 9003 | 测试机时间快到了 | info | 测试机时间快到了 |
| 9004 | 超过测试限Run批数 | warn | 超过测试限Run批数 |
| 0411 | POD/Cassette清洗到期 | info | POD/Cassette清洗到期 |
| 20011 | DirtyBit不匹配 | warn | DirtyBit不匹配 |

报警事件由 `db_poller.py` 自动识别（`event_name = EC_ALARM_REPORT`），不需要在 `flows` 中配置阶段映射。

---

## 附录 C：配置 Schema 字段说明

> 来源：`frontend/src/configs/machine-animations/_schema.json`

### C.1 顶级字段

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `machine_type` | string | ✅ | 机台类型标识，必须与 `machine_models` 表的 `model_id` 前缀一致 |
| `version` | string | ✅ | 配置版本号，语义化版本（如 `1.0.0`） |
| `description` | string | ❌ | 配置描述 |
| `flows` | object | ✅ | 流程定义，每个流程包含一组阶段和事件映射 |
| `animations` | object | ✅ | 动画原语库，参数化定义 |
| `targets` | object | ✅ | 部件目标绑定，2D 选择器和 3D 对象名共用一个 key |

### C.2 flows 字段

```json
"flows": {
  "{FLOW_NAME}": {              // 流程名，如 PACKING / UNPACKING
    "phases": [                  // 阶段序列（必填，数组）
      {
        "key": "string",         // 阶段唯一键（必填）
        "label": "string",       // 中文显示名（必填）
        "duration_ms": "integer", // 持续时间，最小 100（必填）
        "easing": "enum"         // 缓动函数（可选）
      }
    ],
    "event_to_phase": {          // 事件→阶段映射（必填，对象）
      "{EVENT_NAME}": {
        "phase": "string",       // 目标阶段 key（必填）
        "anim": "string",        // 动画原语 key（可选，引用 animations）
        "note": "string"         // 备注（可选）
      }
    }
  }
}
```

### C.3 animations 字段

```json
"animations": {
  "{ANIM_KEY}": {                // 动画原语 key，如 "pod.enter"
    "target": "string",          // 目标部件 key（必填，引用 targets）
    "action": "enum",            // 动画类型（必填）
    "axis": "enum",              // 轴（部分 action 必填）
    "from": "number",            // 起始值
    "to": "number",              // 结束值
    "color": "string",           // 颜色（flash / color / scan / signal 用）
    "duration_ms": "integer",    // 持续时间（覆盖阶段时长）
    "easing": "string",          // 缓动函数
    "sub_phase": "string"        // 阶段内分段，用于复杂动画
  }
}
```

**action 枚举值（8 种）**：

| action | 必填字段 | 说明 |
|--------|---------|------|
| `translate` | axis / from / to | 平移 |
| `rotate` | axis / from / to | 旋转 |
| `scale` | axis / from / to | 缩放 |
| `flash` | color / duration_ms | 闪烁 |
| `visibility` | from / to（0/1） | 显隐 |
| `color` | color | 变色 |
| `scan` | axis / from / to / color | 扫描 |
| `signal` | color / duration_ms | 信号波动 |

**axis 枚举值**：`x` / `y` / `z`

**easing 枚举值（5 种）**：

| easing | 说明 |
|--------|------|
| `linear` | 匀速 |
| `easeInOut` | 先慢后快再慢 |
| `mechanical` | 机械感（带停顿） |
| `easeOut` | 先快后慢 |
| `easeIn` | 先慢后快 |

### C.4 targets 字段

```json
"targets": {
  "{TARGET_KEY}": {              // 部件 key，如 "podShell"
    "view_2d": "string",         // SVG 元素 id（不带 #）
    "view_3d": "string",         // Three.js Group userData 标识
    "desc": "string"             // 部件描述
  }
}
```

**关键约束**：

- `view_2d` 的值必须与 SVG 文件中元素的 `id` 属性完全一致（不带 `#` 前缀）
- `view_3d` 的值必须与 Three.js Group 的 `userData.name` 完全一致
- 同一个 `target_key` 可以同时被多个动画原语引用

### C.5 校验规则（useAnimationConfig.js 内置）

加载器在加载配置时会执行轻量校验：

| 校验项 | 错误信息 |
|--------|---------|
| 缺少 `machine_type` | `缺少 machine_type` |
| 缺少 `version` | `缺少 version` |
| 缺少 `flows` | `缺少 flows 对象` |
| `flows.{key}.phases` 不是数组 | `flows.{key}.phases 必须是数组` |
| 阶段缺少 `key` | `flows.{key}.phases[{idx}].key 缺失` |
| 阶段缺少 `label` | `flows.{key}.phases[{idx}].label 缺失` |
| 阶段 `duration_ms` 无效 | `flows.{key}.phases[{idx}].duration_ms 无效` |
| `flows.{key}.event_to_phase` 不是对象 | `flows.{key}.event_to_phase 必须是对象` |
| 缺少 `animations` | `缺少 animations 对象` |
| 缺少 `targets` | `缺少 targets 对象` |

校验失败会抛出异常，配置不会加载。前端控制台会打印错误信息。

---

## 附录 D：常见问题速查

### D.1 配置加载失败

| 现象 | 原因 | 解决 |
|------|------|------|
| 控制台报「未找到机台类型的配置文件」 | 文件名大小写不对 | 文件名必须全小写，如 `podopener.json` |
| 控制台报「配置校验失败: 缺少 xxx」 | 必填字段缺失 | 补全字段（参考附录 C） |
| 控制台报「flows.XXX.phases 必须是数组」 | phases 写成对象 | 改为数组 `[...]` |
| 控制台报「duration_ms 无效」 | duration_ms < 100 或非数字 | 设为 ≥ 100 的整数 |

### D.2 动画不触发

| 现象 | 原因 | 解决 |
|------|------|------|
| 点事件按钮无反应 | `targets.xxx.view_2d` 与 SVG id 不匹配 | 检查命名 |
| 动画方向反了 | `from` / `to` 写反 | 互换两个值 |
| 动画太快 | `duration_ms` 太小 | 增大（最小 100） |
| 动画卡顿 | 多个动画争抢同一部件 | 检查是否同时触发多个 translate |

### D.3 事件不触发

| 现象 | 原因 | 解决 |
|------|------|------|
| WinForm 点击无前端反应 | db_poller 未启动 | 检查 `DB_POLLER_ENABLED = True` |
| WebSocket 不连接 | 后端未启动 / 端口不对 | 检查后端 `http://localhost:8002` |
| 事件名大小写不一致 | `event_to_phase` key 必须大写 | 用 `.toUpperCase()` |
| 偏差检测一直报警 | 期望阶段 ≠ 实际阶段 | 检查 `event_to_phase` 映射 |

### D.4 部署问题

| 现象 | 原因 | 解决 |
|------|------|------|
| `npm install` 失败 | 内网无法访问 npm | 配置内网 npm 镜像 |
| `pip install` 失败 | 内网无法访问 PyPI | 配置内网 pip 镜像 |
| Oracle 连接失败 | DSN/账号密码错 | 检查 `backend/config.py` |
| 前端构建报错 | 配置文件 JSON 语法错 | 用 JSON 校验工具检查 |

### D.5 调试技巧

1. **F12 控制台**：所有错误都会打印，第一个排查点
2. **Network 面板**：检查 API 请求 / WebSocket 消息
3. **Elements 面板**：检查 SVG 元素是否有正确 id
4. **调试面板「事件列表」Tab**：看期望阶段 vs 实际阶段
5. **调试面板「配置编辑」Tab**：热修改快速试错
6. **后端日志**：`db_poller` 的日志会打印事件解析结果

---

## 结语

这份 SOP 会随项目迭代持续更新。如果你在跟着做时遇到问题：

1. 先看附录 D「常见问题速查」
2. 再看对应阶段的「常见问题」小节
3. 还解决不了 → 找 PODOPENER 的实现对比（`podopener.json` + `MachineVpoView.vue`）
4. 最后兜底 → 提 GitHub Issue 或联系项目负责人

祝你接入顺利！🎉

---

## 相关文档

- 《系统架构说明书.md》—— 系统架构与模块说明
- 《开发进度管控.md》—— 版本里程碑与验收标准
- 《变更更改版记录.md》—— 按版本号变更明细
