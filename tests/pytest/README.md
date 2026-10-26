# 数据读写 pytest 套件（千万级本地库实测）

面向本地 Oracle 19c（`fabtwin@localhost:1521/ORCLPDB`，`DT_EVENT_RAW` 1000 万行）的
**真实数据读写**测试。与 `tests/` 下既有的手工 print 脚本不同，这里全部是可断言、
可重复执行的 pytest 用例。

## 前置

1. Oracle 服务在跑、ORCLPDB 可连（默认账号 fabtwin/fabtwin，走 backend/config.py 的环境变量覆盖）。
2. 后端依赖已装：`backend/venv` 已由 `pip install -r backend/requirements.txt` + `pytest` 建好。

## 运行

```bash
cd backend

# 常规套件（不含 CLOB 全表扫慢测试），约 2-3 分钟
./venv/Scripts/python -m pytest ../tests/pytest -m "not slow"

# 全量（含千万行 CLOB LIKE 实测，慢测试可能单个数分钟）
./venv/Scripts/python -m pytest ../tests/pytest

# 单个文件/用例
./venv/Scripts/python -m pytest ../tests/pytest/test_write_rvmessages.py -v
```

测试会启动真实 FastAPI app（TestClient，startup 跑 `init_db()` + db_poller），
并直连库做断言；不需要另起后端/前端服务。

## 覆盖内容

| 文件 | 覆盖 |
|---|---|
| `test_read_history.py` | /history 同日查询、60s TTL 缓存冷暖、keyset 翻页、事件详情、payload 裁剪、/timeline 小时聚合、实时最新 N 条 |
| `test_read_machines.py` | /api/machines 与库行数一致、60s 缓存冷暖、/stats、详情 200/404、/history alarms、/alarms/stats |
| `test_read_lots_slow.py` | **@pytest.mark.slow**：/api/lots/{id} 的 CLOB LIKE 命中/未命中、/{id}/events，量千万行全表扫基线耗时 |
| `test_write_rvmessages.py` | POST /api/rv/message 双表落库回读、CUR 表 merge 语义、非法 JSON 的 500 副作用、同秒 raw_id 碰撞、PK 全局唯一 |
| `test_e2e_poller_ws.py` | 外部直写 DT_EVENT_RAW → db_poller 轮询 → /ws/realtime 推送的完整闭环 |

## 已钉住的缺陷（xfail / 明确断言的现状）

- **keyset 翻页重叠**：`_decrement_raw_id`（backend/routers/history.py:41）对零填充
  数字后缀丢失宽度——`SEED0009489888` 减 1 变成 `SEED9489887`（短了，字符串序反而更大），
  `raw_id < cursor` 命中全部行，第二页与第一页完全重叠。**strict xfail**：修复后该用例会
  XPASS 提醒你去掉标记。注意：数字型 raw_id 无此问题，只影响定宽字符串型（种子/部分灌库数据）。
- **rv raw_id 秒级碰撞**：rvmessages.py:44 `f"TID.{int(timestamp())}"`，同秒第二条 → 500。
- **非法 payload 的 500 副作用**：rvmessages.py 在 commit 之后才 `json.loads`，行已落库但客户端收 500。

## 数据清理约定

- 所有测试写入：tool_id 前缀 `TEST-RW-`、raw_id 前缀 `TIDZ.TEST.`（TIDZ 在字符串序上
  高于 TID.，保证能进 db_poller 的"最新 100 行"窗口）。
- autouse 夹具每个用例前后都按这两个前缀清理 `DT_EVENT_RAW` / `DT_EVENT_RAW_CUR`，
  可安全反复运行，不污染业务数据。
- `.perf_report.json`（各读路径实测耗时，自动生成）勿提交。
