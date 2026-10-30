# 新机台建模 SOP v1

> 适用范围：motion2d 新机台，从参考图到 SVG、Motion JSON、deriver、入库和动画验收。
> 原则：公共库负责基础结构、材质和通用部件；机型脚本只维护布局、通道、专属外观和动作参数。

## 1. 输入与不可变契约

1. 将参考图保存到 `docs/assets/machine-references/`，记录腔体数量、传输路径、EFEM/Load Port、PM、泵组和 UI 的可辨识结构。
2. 先确认复用的事件词表、deriver 和部件 ID，不在机型脚本中另造一套动画协议。
3. 可动或可检视部件必须同时具有 `id` 与 `data-pid`；根 SVG 必须保留 `width`、`height` 和 `viewBox`。
4. 动画开发与调试只在「模型编辑器 → 动画调试」进行，机台详情仅用于最终演示。
5. 新机台入库只执行数据 upsert/insert，不增加 DDL；`VIEWS_CONFIG_JSON`、`ANIMATION_CONFIG_JSON` 等 Oracle CLOB 配置使用 SQLAlchemy ORM `SELECT + UPDATE/INSERT`，避免 `MERGE` 触发 `ORA-03146`。

Cluster 机型沿用 `cluster_motion.py` 的 26 步标准事件及以下挂点：

- `{LPn}_CST`、`{LPn}_DOOR`
- `{PMn}`、`{PMn}_run`、`{PMn}_alarm`、`{PMn}_unload`
- `ATM_ARM`、`VTM_ARM`、`WAFER_MOVE`、`WAFER_VTM`
- `ALIGNER`、`ALIGNER_WAFER`
- `TOWER_run`、`TOWER_alarm`、`TITLE`

## 2. 建立生成器

1. 用 `models/svg_kit/scaffold.py` 生成基础资产，或参考 `build_lam2300.py`、`build_sym3.py`、`build_synapse.py` 新建机型生成器。
2. 颜色、线宽和材质先查 `tokens.json`；通用金属色新增到统一 token，不在多个机型脚本中复制色值。
3. 优先复用 `primitives.py`：俯视腔体、Airlock、封闭通道、Aligner、Load Port，以及 `iso_box`、`iso_cylinder`、等角 PM 和泵组。
4. 真正可复用的结构回收到公共库；参考图中的专属外轮廓、布局和通道保留在机型生成器。
5. 等角部件的 `cx/cy` 是底面或底部椭圆中心，顶面中心为 `(cx, cy-h)`。封闭通道先绘制，再绘制腔体覆盖端部。

## 3. 布局与 Motion

1. 按参考图摆放部件，检查 PM 朝向、ATM→Airlock→VTM→PM 传输路径和前后遮挡关系。
2. 用 MotionBuilder 或共享 `cluster_motion.py` 生成 Motion JSON，保持 `document.src` 与 SVG 文件名一致。
3. 配置 `ext.deriver`、`param_defaults`、`event_aliases`、`part_aliases` 和基态隐藏标记。
4. 运行时 `{PORT}`、`{CH}` 等占位符由 deriver 展开；静态校验会对这些目标给出 warning，不能用跳过校验代替 deriver 回归。
5. 生成 `models/user/*.svg` 与 `*.motion.json`；生成物不手工编辑，修正后重新运行生成器。

## 4. 静态与编辑器校验

执行 CLI：

```powershell
python -m models.svg_kit.validate models/user/<machine>.svg models/user/<machine>.motion.json
```

然后在平台编辑器验证内存草稿：

1. 打开「模型编辑器 → 动画配置」，选择机型并等待 SVG 加载。
2. 点击「校验」，检查 `POST /api/uploads/models/validate-draft` 返回的 errors、warnings 和统计信息。
3. errors 必须清零；保存前会自动再次校验，errors 或校验请求失败都会阻断保存。
4. 在部件清单和 SVG 之间双向点选，确认高亮、别名解析和缺失目标提示正确。
5. warnings 逐项分类：静态装饰件未被 Motion 引用可保留；运行时占位符必须由后续 deriver/事件回归覆盖。

## 5. 入库与动画全链验收

1. 同步运行时 SVG 并 upsert 机型配置：

```powershell
python scripts/sync_cluster_models_to_db.py all
```

2. 核对 `models/user/` 与 `backend/uploads/models/` 的 SVG 哈希一致，并确认只发生数据 upsert/insert。`backend/uploads/` 默认被 `.gitignore` 忽略，新增加的规范运行时 SVG 必须逐文件 `git add -f` 纳入交付，不能用目录级强制添加混入上传历史和备份。
3. 在「动画调试」选择演示机台，用最小初始化参数运行 deriver；确认端口、腔体、slot 归一和占位符展开。
4. 逐条注入标准事件，验证 debug 注入→DB→轮询→WS→deriver→MotionPlayback 全链；重点观察晶圆是否始终位于叉前端、机械臂基座是否固定、PM 状态灯和基态隐藏是否正确。
5. 不在机台详情增加调试按钮或测试入口。

## 6. 回归与交付

1. 对新机台和 PODOPENER、OXE、AMAT 存量机台执行 SVG×Motion 校验。
2. 执行后端聚焦测试、Python 语法检查、前端 `npm run build` 和 preview 冒烟。
3. 浏览器检查完整布局、控制台和网络请求；新机台截图保存到 `docs/assets/baseline/`。
4. 更新公共库指南、计划、变更记录和交接说明，明确 DB 变更、warnings、未执行项及环境限制。
5. 清理临时预览页和调试产物，不删除或混入用户已有的备份、日志文件。

### 交付检查表

- [x] SVG 与 Motion 由生成器可重复产出；OXE 定稿只允许 defs 安全同步
- [x] `id + data-pid`、Motion 目标、deriver 和事件契约一致
- [x] CLI 与编辑器草稿校验均为 0 error，warnings 已分类
- [x] 部件清单/SVG 双向高亮通过
- [x] 运行时副本与 DB 配置同步，源/运行时 SVG 哈希一致
- [x] 六台 deriver 动态目标回归及 LAM2300 真实 22 事件全链通过
- [x] 六台静态/动态回归、聚焦测试、构建和六张截图基线完成
- [x] 文档、临时文件和工作区差异已复核
- [ ] PODOPENER/AMAT 最新 token defs 运行时副本的补充浏览器视觉对照（非阻塞后续项，不得提前宣称零视觉回归）
