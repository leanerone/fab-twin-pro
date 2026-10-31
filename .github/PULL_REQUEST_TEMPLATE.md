# 变更说明

**归属线**（勾一个）：
- [ ] 总控/数据链路（季世庆）
- [ ] 机台建模（钱鸣）
- [ ] AI应用/界面（朱明钊）
- [ ] Dify/n8n（张亮）
- [ ] 平台内核（洪佳琪）

**做了什么**（1~3 句话说清楚，评审的人不一定了解上下文）：

**为什么这么做**（背景/问题链接）：

## 自测证据（必填，粘贴命令输出或截图说明）

- [ ] 本地跑过，命令与结果：
- [ ] 前端改动：`npm run build` 通过
- [ ] 后端改动：`python -m pytest tests/test_ai_middleware_regressions.py tests/test_model_draft_validation.py -q` 通过
- [ ] 机台建模改动：六机台 `validate` 0 errors（CI 会自动查）

## 边界检查

- [ ] 我只改了自己分工表里的路径
- [ ] 如果碰了别人的/公共的文件，原因：
- [ ] 数据库有变更时：已写成 `sql/` 脚本放进本 PR（没有则不勾）
- [ ] 新增了第三方依赖：已更新 `backend/requirements.txt` 或 `package.json`（没有则不勾）
