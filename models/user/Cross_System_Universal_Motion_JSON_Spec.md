# 跨系统通用 Motion JSON 规范

## 1. 目的

本规范定义一套可跨 Web 画布、WinForms 编辑器及后续其他系统复用的通用 Motion JSON 格式。

目标：
1. 不依赖某个具体画布实现。
2. 坐标含义稳定，可在不同系统间迁移。
3. 业务语义与几何语义分离，便于扩展。
4. 兼容你当前的 SVG Motion Editor 产物，并支持后续转换。

---

## 2. 设计原则

1. **业务字段与几何字段分离**：step、when、target_part_id 属于业务语义；坐标与旋转属于几何语义。
2. **使用逻辑坐标，不使用屏幕像素**：不得把浏览器窗口像素、WinForms 控件像素作为持久化标准。
3. **统一坐标基准**：默认采用 SVG user space 的逻辑坐标，并以 `document.coord` 明确声明原点与轴向。
4. **保留扩展口**：任何系统特有字段统一放到 `ext` 中。
5. **保持向后兼容**：旧格式可通过转换器映射到新格式，不要求一次性改完所有下游系统。

---

## 3. 版本规则

建议在根对象中固定版本号：

```json
{
  "schema_version": "1.0"
}
```

版本升级原则：
1. 兼容旧字段时优先保留旧字段读取能力。
2. 新增字段不破坏旧解析器。
3. 大版本升级时修改 `schema_version`。

---

## 4. 坐标规范

### 4.1 坐标系

默认坐标系定义为：
1. 类型：`svg_user_space`
2. 原点：左下角
3. X 轴：向右为正
4. Y 轴：向上为正
5. 单位：`px` 或等价逻辑单位

说明：
1. 几何位置、动作位移、轨迹记录都按该逻辑坐标解释。
2. SVG 浏览器/画布内部坐标可在编辑器内转换，但 JSON 落盘统一使用该坐标系。

### 4.2 基准信息

每个文档应包含画布基准信息：

```json
{
  "coord": {
    "type": "svg_user_space",
    "unit": "px",
    "origin": "bottom_left",
    "y_axis": "up",
    "viewBox": [0, 0, 1920, 1080]
  }
}
```

说明：
1. `viewBox` 用于跨画布还原坐标比例。
2. 不同系统可通过 `viewBox` 和自己的画布尺寸做缩放映射。
3. 当 `origin` 为 `bottom_left` 时，`y` 方向按向上递增理解。
4. `rotation` 统一使用角度制，正值按当前 SVG/浏览器惯例解释。

### 4.3 不允许的坐标来源

以下坐标不得直接作为标准持久化坐标：
1. 浏览器 clientX / clientY
2. WinForms 控件坐标
3. 设备屏幕绝对像素
4. 未经坐标转换的鼠标事件位置

---

## 5. 根对象结构

建议根对象如下：

```json
{
  "schema_version": "1.0",
  "document": {},
  "parts": [],
  "motions": [],
  "ext": {}
}
```

### 5.1 `document`

描述文档与坐标基准。

内部简写建议：
1. `name`：文档名或工程名。
2. `src`：来源类型，例如 `svg`、`amat_metsput`。
3. `coord`：坐标系定义。
4. `src_id`：原始文件标识，可选。
5. `coord` 下的 `origin`、`y_axis` 共同说明逻辑坐标方向，建议与 SVG 画布转换保持一致。

推荐写法示例：

```json
{
  "document": {
    "name": "amat_metsput",
    "src": "amat_metsput",
    "coord": {
      "type": "logical",
      "unit": "px",
      "origin": "bottom_left",
      "y_axis": "up"
    }
  }
}
```

### 5.2 `parts`

描述可被 motion 驱动的对象集合。

建议字段：
1. `part_id`：稳定唯一标识。
2. `part_name`：显示名称。
3. `part_type`：对象类型，例如 `group`、`module`、`panel`。
4. `anchors`：锚点集合，可选。
5. `ext`：扩展字段。

### 5.3 `motions`

描述步骤与动作规则。

### 5.4 `ext`

根级扩展字段，保留给系统专用信息。

---

## 6. motions 结构

每个 motion 表示一个步骤。

```json
{
  "step": "CHAMBER_START",
  "enabled": true,
  "target_part_id": "group1",
  "rules": []
}
```

### 6.1 motion 字段定义

1. `step`：步骤名，字符串，必填。
2. `enabled`：是否启用，布尔值，建议默认 `true`。
3. `target_part_id`：该 STEP 的目标部件标识。
4. `rules`：规则数组，必填，至少可为空数组。
5. `priority`：可选，数字越大优先级越高。
6. `comment`：可选说明。
7. `ext`：扩展字段。

### 6.2 step 命名建议

1. 使用业务语义名称优先，例如 `CHAMBER_START`、`ALIGN`、`LOAD`。
2. 若无业务名称，再退回到自动编号，例如 `STEP_001`。
3. 同一文件内 step 名称应尽量唯一。

---

## 7. rules 结构

每个 rule 代表一个条件分支下的动作集合。

推荐结构：

```json
{
  "when": "params.port == '1'",
  "target_part_id": "group1",
  "actions": [
    {
      "type": "offset",
      "offset_x": 0,
      "offset_y": -50
    }
  ]
}
```

### 7.1 rule 字段定义

1. `when`：触发条件表达式，字符串，必填。
2. `target_part_id`：规则目标部件标识，可选。
3. `actions`：动作数组，必填。
4. `comment`：可选说明。
5. `ext`：扩展字段。

### 7.2 动作定义

建议动作统一使用数组，不再把位移/旋转拆成多个孤立字段。

动作类型建议：
1. `offset`
2. `rotate`
3. `scale`
4. `opacity`
5. `visibility`
6. `custom`

#### rotate

```json
{
  "type": "rotate",
  "angle": 90,
  "pivot": {
    "x": 520,
    "y": 300
  }
}
```

说明：
1. `angle` 表示旋转角度。
2. `pivot.x` / `pivot.y` 表示旋转中心坐标。
3. 若未显式写 `pivot`，执行端可按目标部件中心处理。

#### custom

```json
{
  "type": "custom",
  "name": "heater_power",
  "value": 1
}
```

### 7.3 动作为 0 的处理原则

1. 动作值为 0 时，保存层可以省略该动作项或省略该字段。
2. 若整条 rule 的动作均为 0，则建议该 rule 不写入导出 JSON。
3. 读取层应把缺失字段视为默认值 0，而不是错误。

补充说明：
1. `offset` 动作的 0 值会保留为显式字段，便于表达"到位但无偏移"这一状态。
2. 其他动作是否保留 0 值，可按各系统需要决定。

---

## 8. 推荐完整示例

```json
{
  "schema_version": "1.0",
  "document": {
    "name": "amat_metsput",
    "src": "svg",
    "coord": {
      "type": "svg_user_space",
      "unit": "px",
      "origin": "bottom_left",
      "y_axis": "up",
      "viewBox": [0, 0, 1920, 1080]
    }
  },
  "parts": [
    {
      "part_id": "group1",
      "part_name": "module1",
      "part_type": "group",
      "anchors": [
        { "name": "center", "x": 520, "y": 300 }
      ],
      "ext": {}
    }
  ],
  "motions": [
    {
      "step": "CHAMBER_START",
      "enabled": true,
      "target_part_id": "group1",
      "rules": [
        {
          "when": "params.port == '1'",
          "target_part_id": "group1",
          "actions": [
            { "type": "offset", "x": 0, "y": -50 }
          ]
        }
      ]
    }
  ],
  "ext": {}
}
```

---

## 9. 与当前 SvgMotionEditor 的映射关系

你当前编辑器里使用的字段，可按下列方式映射到通用格式：

1. `motions[].step` -> `motions[].step`
2. `motions[].target_part_id` -> `motions[].target_part_id`
3. `rules[].when` -> `rules[].when`
4. `rules[].target_part_id` -> `rules[].target_part_id`
5. `rules[].rotation` / `rules[].angle` -> `actions[{ type: "rotate", angle: ..., pivot: { x, y } }]`
6. `rules[].offset_x` -> `actions[{ type: "offset", offset_x: ... }]`
7. `rules[].offset_y` -> `actions[{ type: "offset", offset_y: ... }]`

### 9.1 当前格式到通用格式的建议转换

1. 如果 rule 同时有 `rotation` 和 `offset_x`、`offset_y`，转换为同一条 rule 下多个 actions。
2. rotate 动作优先写成 `angle + pivot`，pivot 建议使用目标部件中心。
3. 若某个动作值为 0，则不写入动作数组。
4. 若 rule 没有任何有效动作，则可整条跳过。

### 9.2 通用格式到当前编辑器的建议转换

1. `rotate.angle` 写回 `rotation`
2. `rotate.pivot.x/y` 写回旋转中心坐标
3. `offset.offset_x` 写回 `offset_x`
4. `offset.offset_y` 写回 `offset_y`
5. 若动作数组中没有对应动作，则在编辑器里显示为 0

---

## 10. 跨系统兼容建议

如果你未来还要给 PLC、机台侧或后端服务用，建议再加两层：

1. **单位转换层**：把逻辑坐标转换成各系统所需单位。
2. **命名映射层**：把 part_id、step 名称、动作名映射到各系统习惯字段。

原则是：
1. 通用 JSON 不改。
2. 每个系统只写自己的转换器。
3. 不把系统差异反向污染通用格式。

---

## 11. 外部系统接入规范

本规范所定义的 SVG + JSON 产物，允许外部系统直接消费，但前提是外部系统必须实现一层明确的适配器，用于把通用格式映射到本系统内部对象模型。接入时不建议直接依赖编辑器内部实现细节，而应只依赖 JSON 中的稳定字段与 SVG 中的稳定标识。

### 11.1 接入目标

外部系统接入后，应至少具备以下能力：
1. 读取文档级坐标基准。
2. 识别 SVG 中的目标部件或分组。
3. 解析 motion、rule 与 actions 的业务语义。
4. 将逻辑坐标转换为本系统坐标或设备坐标。
5. 按顺序执行 offset、rotate 等动作。

### 11.2 必须读取的输入

外部系统至少需要读取以下内容：
1. `document.coord`：用于确定原点、轴向、单位与视图基准。
2. `parts`：用于建立 part_id 到实际对象的映射关系。
3. `motions[].step`：用于识别步骤。
4. `motions[].rules[].when`：用于判断规则是否命中。
5. `motions[].rules[].target_part_id`：用于定位目标对象。
6. `motions[].rules[].actions`：用于获取具体动作。

### 11.3 处理流程

推荐处理流程如下：
1. 解析 JSON 根对象，校验 `schema_version`。
2. 读取 `document.coord`，建立统一坐标解释。
3. 读取 `parts`，建立目标对象索引。
4. 按 `motions` 顺序遍历步骤。
5. 对每个 `rule` 先判断 `when`，再决定是否执行。
6. 将 `actions` 按顺序应用到 `target_part_id` 对应对象。
7. 若存在多条命中规则，按系统约定的优先级或文件顺序执行。

### 11.4 坐标映射规则

外部系统处理坐标时，应遵循以下原则：
1. `origin: bottom_left` 表示逻辑原点在左下角。
2. `y_axis: up` 表示 y 值向上递增。
3. `offset` 为相对位移，不是绝对定位。
4. `rotate.angle` 为角度制。
5. `rotate.pivot` 为旋转中心，若缺省则应使用目标对象中心或系统默认锚点。
6. 若本系统内部坐标方向与规范不同，应在适配器层完成转换，不得改写通用 JSON。

### 11.5 动作执行规则

外部系统执行动作时，应遵循以下顺序：
1. 先确定目标对象的当前基准位置。
2. 再应用 `offset` 的增量位移。
3. 再应用 `rotate` 的角度与 pivot。
4. 若同一 rule 下存在多个动作，按数组顺序执行。
5. 若动作值为 0，也应视为有效输入，不得因为 0 而误删规则语义。

### 11.6 兼容性要求

外部系统接入时，应满足以下兼容性约束：
1. 允许忽略未知扩展字段，但不得拒绝整个文件。
2. 允许读取旧字段并映射为当前动作模型。
3. 不应把 SVG 原始像素坐标直接当作通用逻辑坐标。
4. 不应把编辑器 UI 状态作为持久化语义来源。
5. 若无法执行某个动作类型，应明确降级、跳过或报错，不可静默篡改。

### 11.7 错误处理建议

建议将错误分为三类：

1. **结构错误**：JSON 语法错误、缺少必填字段、类型不匹配。
2. **语义错误**：`target_part_id` 找不到对象、`when` 无法解析、坐标基准缺失。
3. **执行错误**：动作超出系统能力、对象不可见、运行时变换失败。

处理原则：
1. 结构错误应直接拒绝加载。
2. 语义错误应记录并跳过相关 rule 或 motion。
3. 执行错误应尽量局部降级，不影响其他独立规则。

### 11.8 最小接入要求

如果某系统只想先做最小接入，至少应实现：
1. 读取 `document.coord`。
2. 读取 `motions[].rules[].actions`。
3. 支持 `offset` 与 `rotate` 两类动作。
4. 支持 `target_part_id` 到本地对象的映射。
5. 支持按 `step` 顺序执行。

### 11.9 推荐接入边界

推荐把外部系统的职责限制为三层：

1. **解析层**：读取并校验 JSON。
2. **映射层**：把通用字段映射为本系统对象与坐标。
3. **执行层**：真正应用偏移、旋转与其他动作。

不要把以下内容混进通用 JSON 解释器：
1. 具体 UI 交互逻辑。
2. 编辑器拖拽状态。
3. 某个机台专有命令序列。
4. 临时调试字段。

---

## 12. 验收标准

一份合格的通用 JSON 应满足：
1. 任意系统都能识别 step、when、target_part_id 和 actions。
2. 坐标可通过 viewBox 或等价基准还原。
3. 0 值动作不会污染导出文件。
4. 旧格式能通过转换器无损迁移到新格式。
5. 新系统只要实现 actions 解释器即可接入。

---

## 13. 推荐后续落地顺序

1. 先冻结该规范。
2. 再给当前编辑器加导出转换器。
3. 然后补一个旧格式兼容导入器。
4. 最后让其他系统只消费通用格式。

---

## 14. 关联文档

1. [POC_Interface_Field_Mapping_and_Normalized_Event.md](POC_Interface_Field_Mapping_and_Normalized_Event.md)
2. [POC_2D_3D_Unified_Mapping.md](POC_2D_3D_Unified_Mapping.md)
3. [POC_Oracle_Minimum_Schema_Design.md](POC_Oracle_Minimum_Schema_Design.md)