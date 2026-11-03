# 模块② 生产监控（production-monitor）

- **负责人**：季世庆
- **功能边界**：机台实时监控与历史回放、车间看板/楼层平面、告警、批次、天车、配方、事件接入（poller）。

## 目录

```
frontend/
  pages/       MachineDetailPage（机台详情，消费①的 MachineMotion2D）、DashboardPage（看板）
  components/
    playback/  PlaybackBar、HistoryReplay
    machine-3d/ MachineModel3D、MachineVpo3DView
    floor/     FloorPlan、FloorView3D、KpiCards、MachineList
    panels/    LotList、AlarmList
  composables/ useMachinePlayback、useRunState、timeFormat、useAnimationConfig、useEventActionMapping
```

后端对应：`routers/{history,events,lots,alarms,oht,oxe,recipes,machines,floors,rvmessages,debug}.py`、
`services/{db_poller,simulator,ods}.py`；`sql/`、`deploy/`（dify/n8n 除外）；
表 `dt_event_raw/_cur/_std、machine_events、alarms、lots、recipes、chamber_snapshots、machines、
floors、floor_areas、oht_positions、tracks、vehicles、dashboard_kpi、dt_state_snapshot、dt_alarm_event`。

## 公开接口

- 路由 `/`（看板）、`/machine/:id`（详情）
- `api` barrel 中的 machines/history/floors 等方法、WebSocket raw_event 事件流

## 依赖方向

- 用①模型库的 `<MachineMotion2D>` 渲染动画（只读组件，不改①目录）
- 用③AI 助手的 `<AiAssistant>`（详情页内问答）
- 共享 3D/RAF/WebSocket 工具走 `@/platform/frontend/core/composables`
- 数据统一从 `@/api`、状态从 `@/stores`（内核入口），不直接进别的模块内部

## 自测

`npm run build`；看板/机台详情/回放/告警批次面板浏览器回归；后端
`pytest tests/pytest`（history/lots/machines/poller）。
