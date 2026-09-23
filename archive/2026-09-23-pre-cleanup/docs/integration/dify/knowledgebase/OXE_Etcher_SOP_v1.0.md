# OXE 刻蚀机操作与异常处理 SOP
> 文档版本: v1.0 | 更新日期: 2026-08-28
> 适用机台: Applied Materials OXE 系列 (OXE-01 ~ OXE-20)
> 用途: 作为 FabTwin Dify RAG 知识库种子文档，供 AI 助手基于工艺文档回答工程师提问

---

## 1. 机台概述

Applied Materials OXE 刻蚀机台为 FAB 厂 12 英寸 Wafer 主刻蚀设备，主要用于
Poly / Oxide / Metal 刻蚀工艺。单台机台含 3 个刻蚀 Chamber (Ch1/Ch2/Ch3)，
2 个 Pod 装卸区 (Port1/Port2)，1 组机械臂 (ATM) 负责 Wafer 在 Pod→Chamber
之间的搬运。

关键指标：
- 机台节拍 (CT)：90~120 秒 / 片
- Lot 容量：25 片 / FOUP
- 日产能：≥ 1000 片 / 台（3 个 Chamber 均衡使用时）
- 典型 MTBA（平均两次辅助间隔）：> 48 小时

---

## 2. 操作员日常作业流程 (Daily SOP)

### 2.1 上班前检查 (Shift Start Check)
1. 登录机台 GUI，确认 OXE 处于 `Idle` 或 `Run` 状态。
2. 检查 3 个 Chamber 的 RF Hour 累计：
   - 任一 Chamber 的 RF Hour 超过 2000h → 提交清洁工单 (PM)，禁止继续 Run。
   - 1500h ~ 2000h → 黄色预警，通知工程师评估。
3. 检查 Pressure Pump（干泵 / 分子泵）状态：
   - 分子泵转速应稳定在 24000±500 RPM。
   - 干泵油位必须在绿色区间内。
4. 检查 Process Gas 压力：
   - Cl2 : 0.30~0.35 MPa
   - HBr : 0.28~0.32 MPa
   - O2  : 0.45~0.55 MPa
   - He  : 0.60~0.70 MPa
   - 任一气体压力超出公差 → 立即停 Run，通知厂务气柜。

### 2.2 开始 Run Lot
1. 扫描 FOUP 条形码放入 Port1。
2. 机台自动读取 Wafer 映射 (Map)，若发现空槽或双片 → FOUP 退回，标记 E130 报警。
3. 在 MES 中绑定 Lot 与 Recipe：
   - Recipe 名必须与当前产品型号严格对应（例：`POLY_MAIN_A_202608`）。
   - 严禁使用未签核的测试版 Recipe 量产。
4. 点击 MES `Start` 按钮，机台进入自动 Run 状态。

### 2.3 Run 中监控
1. 观察 FabTwin 看板 Chamber 实时颜色：
   - 绿色 = 刻蚀中 (PS→PE 阶段)
   - 黄色 = 空闲或等待 Wafer
   - 红色 = 报警停机（见 §4 报警处理）
2. 每 30 分钟查看一次 MES EP（工程参数）趋势：
   - 反射功率 (Reflected Power) 不得 > 5W。
   - ESC 温度稳定在 -10℃ ~ -15℃。
3. 若 OXE 连续 3 片均出现 Over-etch（刻蚀深度偏差 > 8%） → 暂停 Lot，通知工艺工程师。

### 2.4 Lot 结束
1. 机台 `End Lot` 后，在 MES 中将 Wafer 结果与 SPC 图表归档。
2. 取 5 片送计量（OCD / AEI / X-SEM）抽检。
3. 清除 Chamber 前处理残余：执行 `Chamber Clean A` 短清洁配方 1 次。

---

## 3. PM (Preventive Maintenance) 周期

| PM 级别 | 周期           | 主要内容                                              | 预计停机时长 |
|--------|----------------|-----------------------------------------------------|---------|
| Weekly | 每周一 AM 2:00 | 换 Quartz Ring、清洁 ESC 表面、Dry Pump Pumping     | 4h      |
| PM-A   | RF Hour 2000h  | 拆 Chamber 上盖、换 Upper/Lower Electrode、检漏 (He Leak) | 8h |
| PM-B   | RF Hour 6000h  | 换 Turbo Pump、换 RF Matching 网络元件、整 Chamber Overhaul | 24h |

PM 后必须执行的验证项目 (Chamber Qualification, CQ)：
1. He Leak < 5×10⁻⁹ atm·cc/s。
2. 空白片刻蚀 Uniformity < 3% (1σ)。
3. 工艺中心点深度偏差 < 5%。
4. 颗粒计数 (≥ 0.12μm) < 30 颗 / 片。

---

## 4. 常见报警与处理

### 4.1 E1xx - Wafer Transport
- **E101 Wafer Not Found (ARM pick fail)**
  1. 打开 Port 门确认 Pod 中的 Wafer 未掉落或倾斜。
  2. 使用 FabTwin 历史回放查看 Port1/Port2 事件时间线，确认是 Pod 映射错误还是 ARM 偏移。
  3. 清理后重试；若 3 次均失败 → 机械臂伺服参数归零重校。
- **E130 Double Slot or Empty (Map Fail)**
  FOUP 放错或 Wafer 移位，整盒 FOUP 需退回 PTD (Photo Track Department) 重排。
- **E155 Wafer Slip at Chamber**
  ESC 静电吸附电压异常或 Wafer 翘曲 > 0.3mm；检查 ESC 电压输出曲线，若正常则 Lot 强制放行但该片标记复查。

### 4.2 E2xx - Process / RF
- **E201 RF Reflect Power High**
  1. 立即 SCRAM（停 RF、送气、关 Chamber gate）。
  2. 进入 Maintenance → Check RF Match 网络有无器件变色。
  3. 清洁 Chamber 顶部 Shower Head，通常由副产物堆积引起。
  4. 重启后若仍报警 → 升级 PM-A。
- **E220 Pressure Unstable**
  检查节流阀 (Throttle Valve) 反馈位置，若 TV 角度 > 85°仍达不到设定压力：
  - 干泵入口滤网堵塞 → 停机清洁滤网。
  - 气体流量设定 MFC 异常 → 校准 MFC。
- **E250 Endpoint Timeout (Endpoint Not Detected)**
  刻蚀终点检测 (IEP/OES) 信号未跳变。常见原因：
  a) 薄膜厚度偏差大（前道 CVD 异常）→ 联系前道追查。
  b) Window 脏污遮挡光路 → 清洁 Endpoint Window。
  c) Recipe 时间窗口过短 → 在 Time+30% 安全上限内调长。

### 4.3 E3xx - Utility
- **E301 Cooling Water Flow Low**
  - 机台水冷流量 < 8 L/min → 立即停止 Run。
  - 厂务水压应在 3.5±0.5 kgf/cm²；若厂务侧正常则拆机台端过滤器。
- **E310 He Backside Pressure High**
  Wafer 翘曲导致 He 泄漏；检查 Wafer 边缘是否有膜层崩裂。3 片/小时以上时需停 Run。

### 4.4 紧急停机 (E-Stop)
出现以下任一情况必须立即按下机台正面红色 E-Stop 按钮：
1. 闻到氟/氯类刺鼻气味（泄漏风险）。
2. 看到机械臂断片飞片。
3. 机台内部冒烟或电弧。

E-Stop 后恢复步骤：
1. 排查原因 → 由工程师签核后方可解除。
2. Chamber N2 Purge ≥ 3 分钟。
3. 空 Run 1 片dummy 验证。
4. 记录到《机台异常报告系统》。

---

## 5. Recipe 命名规范与切换

### 5.1 命名规范
`<Layer>_<Step>_<Version>_<YYYYMM>`
- Layer：POLY / OX / MT / VIA / CONT …
- Step ：MAIN / SOFTLAND / OPEN / STOP …
- Version：A / B / C / D (按签核顺序)

例：`POLY_MAIN_A_202608`

### 5.2 切换 Recipe 注意
1. 切换 Recipe 时必须先 Empty Chamber（无 Wafer）。
2. 切换后先跑 2 片 dummy（Warm-up）。
3. 第 3 片送计量确认后，方可 Run 量产 Lot。
4. 禁止跨 Layer 切换后直接 Run 量产（例：MT → POLY 必须 Warm-up）。

---

## 6. 异常问题排查 (FAQ)

**Q1. OXE 某 Chamber 产出颗粒明显偏高，如何定位？**
1. 查看 FabTwin 报警日志，确认是否存在 E250 连续报警。
2. 进 Chamber 做 Visual Check：
   - Shower Head 针孔堵塞（可用 He 背压逐针检测）。
   - Upper/Lower Electrode 边缘副产物剥落。
   - Focus Ring 老化。
3. 若排除硬件 → 查气体纯度（厂务 GCMS 报告），H2O 含量应 < 1ppb。

**Q2. 3 Chamber 均匀度差异 > 2%，如何平衡？**
1. 对 3 个 Chamber 同时做 CQ（同一片分 3 区）。
2. 调节 Match Box 的 Load Cap (L/Cap) 与 Tune Cap (T/Cap)：
   - Etch rate 偏高 → 下调功率 5%。
   - Etch rate 偏低 → 上调功率 5%。
3. 每次功率调整后用 5 片统计稳定（通常 2~3 轮收敛）。

**Q3. FabTwin 回放里看到 WaferLoaded 事件后 WaferUnloaded 立即触发，中间无 PS/PE？**
说明 Wafer 在 Align / Transfer 阶段即失败。
1. 查 OXE GUI Aligner 日志是否 `Notch Find Fail`。
2. 查机械臂 Z 高度补偿值（参数 `ARM_Z_OFFSET`），近期若做过 ARM 维护需重写。
3. 用 FabTwin AI 提问“查询 OXE-01 Chamber1 最近1小时 Lot 流向”确认是否 Lot 级的连续异常。

**Q4. Dify / FabTwin AI 回答里提到的跳转到某个时间戳，如何使用？**
在 AI 详情面板点击"跳转"按钮，或在 OXE 看板手动输入跳转时间：
- 回放进度条会自动 seek 到对应事件前 3 秒。
- 左侧报警列表会同步高亮那一刻的报警。
- 若跳转目标超过当天数据范围，会自动切换到对应日期并重新拉数据。

---

## 7. 安全要点 (Safety)
1. 严禁在 Chamber 开启时裸露手部伸入；操作必须戴长袖无尘手套。
2. 处理副产物粉末 (Aluminum Chloride 等) 必须佩戴 N95 口罩与护目镜。
3. EMO (Emergency Off) 按钮每月测试一次，响应时间应 < 200ms。
4. 机台开盖后必须执行 LOTO (Lock Out Tag Out) 流程。

---

> 本文档由 FabTwin 项目组维护，作为 RAG 知识库种子文档示例。
> 量产环境应以厂内正式签核版 SOP 为主。
