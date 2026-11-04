# 模块① 模型库（model-library）

- **负责人**：钱鸣
- **功能边界**：机台建模资产、2D 动画引擎、deriver、模型编辑器、素材上传与入库。

## 目录

```
frontend/
  engine/      MachineMotion2D（对外公开组件）、MotionPreview（编辑器预览）、
               useMotionPlayback、useExprEval（唯一表达式实现）
  derivers/    各机型 deriver，import.meta.glob 自动发现；新机型放文件即生效，零注册表编辑
  editor/      pages/ModelEditorPage、pages/MachineManagementPage、components/ModelUpload
```

后端对应（当前真实目录，由 CODEOWNERS 按模块归此负责人）：
`backend/modules/model_library/routes/{models,uploads}.py`、
`backend/modules/model_library/services/html_parser.py`、
`backend/modules/model_library/seeds/{seed_amat_metsput,seed_oxe_motion}.py`；
资产 `models/`、`frontend/public/models/`、`scripts/sync_*`、`backend/uploads/models/`；
表 `machine_model_configs / machine_tool_mappings / event_action_mappings`。
`backend/models.py` 是公共 ORM，改动由洪佳琪最终审核。旧平铺 routers/services 与兼容 shim 已移除，不要恢复旧路径。

## 公开接口（别的模块只准用这些）

- `<MachineMotion2D>`：机台 2D 动画组件（props: machine / modelConfig / events / mode）
- deriver 解析能力：Motion JSON `ext.deriver` 名字 → `derivers/` 自动绑定
- 模型配置 API：`api` barrel 中的 models/uploads 方法

## 内部文件（其他模块不可 import）

`engine/useMotionPlayback.js`、`engine/useExprEval*.js`、`derivers/*`、`editor/**`。
②生产监控的机台详情页只用 `<MachineMotion2D>`，不进本目录改引擎；引擎需求提 issue 给负责人。

## 自测

`cd frontend && npm run build`；六机台 `python models/svg_kit/validate.py <svg> <motion>` 0 error；
模型编辑器四 Tab 手测 + MotionPreview 调试回归。
