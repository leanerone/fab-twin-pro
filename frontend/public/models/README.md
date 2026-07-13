# 模型文件存放目录

本目录用于存放 3D 模型文件（GLB/GLTF 格式）。

## 目录结构

```
models/
├── machines/                 # 机台模型
│   ├── ETCH-TEL-DRM-UNITY-v1.glb    # TEL DRM UNITY 刻蚀机精细模型
│   ├── ETCH-AMAT-v1.glb             # AMAT 刻蚀机模型
│   ├── WAT-v1.glb                   # 测试机模型
│   ├── STK-v1.glb                   # STK 传输机模型
│   └── WS-v1.glb                    # 分选机模型
├── vehicles/                 # 天车/搬运车模型
│   ├── OHT-v1.glb                   # OHT 天车精细模型
│   └── AGV-v1.glb                   # AGV 搬运车模型
└── scenes/                   # 场景模型
    ├── floor-3f-v1.glb              # 3F 楼层场景
    └── fab-overview-v1.glb          # 工厂总览场景
```

## 使用方法

1. 将同事提供的 GLB 模型文件放入对应子目录
2. 在代码中使用以下路径加载：

```javascript
// 加载机台模型
const modelPath = '/models/machines/ETCH-TEL-DRM-UNITY-v1.glb'

// 加载天车模型
const vehiclePath = '/models/vehicles/OHT-v1.glb'
```

## 注意事项

- 文件命名使用英文 + 连字符，如：`ETCH-TEL-DRM-UNITY-v1.glb`
- 版本号使用 `v1`、`v2` 区分不同版本
- 模型大小尽量控制在 10MB 以内（使用 Draco 压缩）
- 模型单位为米（Blender 默认单位）

## 详细集成指南

请参考项目根目录下的 `3D模型集成指南.md` 文档。