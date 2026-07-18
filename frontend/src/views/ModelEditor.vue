<script setup>
import { ref, computed } from 'vue'
import { api } from '../api'
import { useAuthStore } from '../stores/auth'

const authStore = useAuthStore()

const activeTab = ref('guide')
const models = ref([])
const selectedModel = ref(null)
const newModel = ref({
  model_id: '',
  model_name: '',
  vendor: '',
  process_type: 'ETCH',
  view_mode: 'threejs',
  description: '',
})

async function loadModels() {
  try {
    models.value = await api.getModels()
  } catch (e) {
    console.error('加载模型失败:', e)
  }
}

async function createModel() {
  if (!newModel.value.model_id) return
  try {
    await api.createModel(newModel.value)
    await loadModels()
    newModel.value = { model_id: '', model_name: '', vendor: '', process_type: 'ETCH', view_mode: 'threejs', description: '' }
  } catch (e) {
    console.error('创建模型失败:', e)
  }
}

function selectModel(m) {
  selectedModel.value = m
}

const guideSections = [
  {
    id: 'overview',
    title: '📋 模型开发流程概述',
    content: `FabTwin 平台支持三种模型类型：
- 3D模型（Three.js）：适用于复杂机台结构展示
- 2D原理图（SVG）：适用于设备原理和状态监控
- 2.5D等角视图：介于2D和3D之间的轻量化展示

开发流程：设计 → AI生成代码 → 配置映射 → 测试验证`,
  },
  {
    id: 'step1',
    title: '🔧 第一步：分析机台结构',
    content: `在开始建模前，需要了解：
1. 机台的主要部件和组件
2. 各部件的运动方式（旋转、平移、伸缩）
3. 需要监控的状态和事件
4. 关键工艺步骤和动作序列

建议先画一张简单的草图或使用 PowerPoint 标注各部件位置。`,
  },
  {
    id: 'step2',
    title: '🤖 第二步：AI辅助生成代码',
    content: `使用 GitHub Copilot 生成模型代码，参考以下提示词模板：

【PODOPENER 3D模型提示词】
```
帮我生成一个Vue3 + Three.js的PODOPENER（POD开盖机）设备3D模型组件。
要求：
1. 包含以下部件：Base底座、ARM手臂、POD托架、Sensor传感器、ScanLine扫描线
2. ARM手臂支持旋转和平移运动
3. POD托架支持升降动画
4. ScanLine支持扫描动画
5. 使用group组织部件，方便控制
6. 定义MODEL_SCALE常量统一缩放
7. 提供事件处理方法：onEvent(eventCode)
8. 支持事件：POD_LOAD, POD_UNLOAD, SCAN_START, SCAN_END, ARM_MOVE
\`\`\`

【OXE 2.5D等角模型提示词】
\`\`\`
帮我生成一个Vue3的OXE刻蚀机2.5D等角视图组件。
要求：
1. 使用SVG绘制等轴测图
2. 包含Chamber腔体、ARM传送臂、Port端口、RF电源模块
3. ARM臂支持IK逆运动学动画
4. 各部件支持状态变色（运行中绿色、待机灰色、异常红色）
5. 提供动画控制方法：animateArm(targetPosition)
6. 支持晶圆Run货动画
\`\`\`

【通用提示词模板】
\`\`\`
帮我生成一个Vue3的{机台名称}设备{2D/3D/2.5D}模型组件。
要求：
1. 使用{Three.js/SVG/Canvas}技术栈
2. 包含部件：{列出主要部件}
3. 支持运动：{旋转/平移/伸缩/IK}
4. 提供事件处理方法：onEvent(eventCode)
5. 支持事件：{列出需要处理的事件}
6. 输出文件：Machine{ModelName}View.vue
\`\`\``,
  },
  {
    id: 'step3',
    title: '📝 第三步：配置事件-动作映射',
    content: `在模型配置中定义事件到动画的映射关系：

\`\`\`json
{
  "model_id": "PODOPENER-1",
  "model_name": "POD开盖机",
  "view_mode": "vpo3d",
  "state_mapping": [
    { "event_code": "POD_LOAD", "state": "loading", "color": "#22c55e" },
    { "event_code": "POD_UNLOAD", "state": "unloading", "color": "#3b82f6" },
    { "event_code": "SCAN_START", "state": "scanning", "color": "#f59e0b" }
  ],
  "event_action_mappings": [
    {
      "mapping_id": "pod-load-sequence",
      "description": "POD穿入序列",
      "trigger": {
        "event_type": "STATE_CHANGE",
        "event_code": "POD_LOAD"
      },
      "action_sequence": [
        { "action": "translate", "target": "pod", "to": [0, 0, -50], "duration": 2000 },
        { "action": "rotate", "target": "arm", "to": [0, 180, 0], "duration": 1500 },
        { "action": "scan", "target": "scanLine", "duration": 3000 }
      ]
    }
  ]
}
\`\`\`

常用动作类型：
- translate：平移 { target, to: [x, y, z], duration }
- rotate：旋转 { target, to: [rx, ry, rz], duration }
- scale：缩放 { target, to: [sx, sy, sz], duration }
- color：变色 { target, color, duration }
- opacity：透明度 { target, opacity, duration }
- scan：扫描动画 { target, duration }`,
  },
  {
    id: 'step4',
    title: '✅ 第四步：测试验证',
    content: `测试步骤：
1. 在平台上传模型配置
2. 选择机台查看模型渲染效果
3. 使用事件回放功能测试动画
4. 检查状态变化和颜色反馈是否正确
5. 验证响应式和性能

常用测试事件：
- POD_LOAD / POD_UNLOAD：POD穿入/脱出
- SCAN_START / SCAN_END：扫描开始/结束
- CHAMBER_OPEN / CHAMBER_CLOSE：腔体开关
- ARM_MOVE：手臂移动
- LOT_START / LOT_END：Lot开始/结束`,
  },
  {
    id: 'step5',
    title: '📦 第五步：部署上线',
    content: `部署步骤：
1. 将模型组件文件放置在 frontend/src/components/ 目录
2. 在 MachineDetail.vue 中添加对应模型组件的导入和渲染逻辑
3. 在数据库中添加机台型号配置（model_id、view_mode、views_config）
4. 添加事件-动作映射配置
5. 重启前端和后端服务`,
  },
]

const eventCodeReference = [
  { category: 'POD操作', codes: ['POD_LOAD', 'POD_UNLOAD', 'POD_OPEN', 'POD_CLOSE'] },
  { category: 'ARM动作', codes: ['ARM_MOVE', 'ARM_EXTEND', 'ARM_RETRACT', 'ARM_ROTATE'] },
  { category: '扫描检测', codes: ['SCAN_START', 'SCAN_END', 'SCAN_OK', 'SCAN_ERROR'] },
  { category: '腔体操作', codes: ['CHAMBER_OPEN', 'CHAMBER_CLOSE', 'CHAMBER_VENT', 'CHAMBER_PUMP'] },
  { category: '晶圆传送', codes: ['WAFER_LOAD', 'WAFER_UNLOAD', 'WAFER_TRANSFER'] },
  { category: '工艺状态', codes: ['PROCESS_START', 'PROCESS_END', 'PROCESS_PAUSE', 'PROCESS_RESUME'] },
  { category: '报警事件', codes: ['ALARM_HIGH', 'ALARM_MEDIUM', 'ALARM_LOW', 'ALARM_CLEAR'] },
]
</script>

<template>
  <div class="model-editor">
    <div class="editor-header">
      <h1>模型管理与开发指导</h1>
      <div class="header-tabs">
        <button 
          v-for="tab in ['guide', 'models', 'events']" 
          :key="tab"
          class="tab-btn"
          :class="{ active: activeTab === tab }"
          @click="activeTab = tab"
        >
          {{ tab === 'guide' ? '📖 开发指南' : tab === 'models' ? '📦 模型管理' : '📝 事件代码' }}
        </button>
      </div>
    </div>

    <!-- 开发指南 -->
    <div v-show="activeTab === 'guide'" class="guide-panel">
      <div class="guide-container">
        <div class="guide-sidebar">
          <button 
            v-for="section in guideSections" 
            :key="section.id"
            class="section-btn"
            :class="{ active: guideSections.findIndex(s => s.id === section.id) === 0 }"
          >
            {{ section.title }}
          </button>
        </div>
        <div class="guide-content">
          <div v-for="section in guideSections" :key="section.id" class="guide-section">
            <h2>{{ section.title }}</h2>
            <div class="section-body">
              <pre>{{ section.content }}</pre>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 模型管理 -->
    <div v-show="activeTab === 'models'" class="models-panel">
      <div class="models-toolbar">
        <button class="btn-primary" @click="loadModels">🔄 刷新</button>
      </div>
      
      <div class="models-grid">
        <div 
          v-for="model in models" 
          :key="model.model_id"
          class="model-card"
          :class="{ selected: selectedModel?.model_id === model.model_id }"
          @click="selectModel(model)"
        >
          <div class="model-header">
            <span class="model-id">{{ model.model_id }}</span>
            <span class="model-vendor">{{ model.vendor }}</span>
          </div>
          <div class="model-name">{{ model.model_name }}</div>
          <div class="model-meta">
            <span>{{ model.process_type }}</span>
            <span>{{ model.view_mode }}</span>
          </div>
          <div class="model-desc">{{ model.description }}</div>
        </div>
      </div>

      <div v-if="authStore.hasPermission('model_edit')" class="create-panel">
        <h3>新建机台型号</h3>
        <div class="form-grid">
          <div class="form-item">
            <label>型号ID *</label>
            <input v-model="newModel.model_id" placeholder="如：PODOPENER-1" />
          </div>
          <div class="form-item">
            <label>型号名称</label>
            <input v-model="newModel.model_name" placeholder="如：真空预对准机" />
          </div>
          <div class="form-item">
            <label>厂商</label>
            <input v-model="newModel.vendor" placeholder="如：TEL" />
          </div>
          <div class="form-item">
            <label>工艺类型</label>
            <select v-model="newModel.process_type">
              <option value="ETCH">刻蚀</option>
              <option value="LITHO">光刻</option>
              <option value="CVD">沉积</option>
              <option value="PVD">物理气相沉积</option>
              <option value="CMP">化学机械抛光</option>
              <option value="WET">湿法工艺</option>
              <option value="METAL">金属化</option>
              <option value="INSPECT">检测</option>
            </select>
          </div>
          <div class="form-item">
            <label>视图模式</label>
            <select v-model="newModel.view_mode">
              <option value="threejs">Three.js 3D</option>
              <option value="svg">SVG 2D</option>
              <option value="isometric">2.5D 等角</option>
              <option value="vpo">PODOPENER 2D</option>
              <option value="vpo3d">PODOPENER 3D</option>
              <option value="hybrid">混合模式</option>
            </select>
          </div>
          <div class="form-item full">
            <label>描述</label>
            <textarea v-model="newModel.description" placeholder="型号描述"></textarea>
          </div>
        </div>
        <button class="btn-primary" @click="createModel">创建型号</button>
      </div>

      <div v-if="!authStore.hasPermission('model_edit')" class="no-permission">
        <p>⚠️ 您没有模型编辑权限</p>
        <p>普通用户只能查看模型配置，无法编辑或创建</p>
      </div>
    </div>

    <!-- 事件代码参考 -->
    <div v-show="activeTab === 'events'" class="events-panel">
      <h2>📝 事件代码参考</h2>
      <div class="events-grid">
        <div v-for="cat in eventCodeReference" :key="cat.category" class="event-category">
          <div class="category-title">{{ cat.category }}</div>
          <div class="event-codes">
            <span v-for="code in cat.codes" :key="code" class="event-code">{{ code }}</span>
          </div>
        </div>
      </div>
      
      <div class="mapping-example">
        <h3>事件-动作映射示例</h3>
        <pre class="code-block">{
  "mapping_id": "pod-load-sequence",
  "description": "POD穿入序列",
  "trigger": {
    "event_type": "STATE_CHANGE",
    "event_code": "POD_LOAD"
  },
  "action_sequence": [
    { "action": "translate", "target": "pod", "to": [0, 0, -50], "duration": 2000 },
    { "action": "rotate", "target": "arm", "to": [0, 180, 0], "duration": 1500 },
    { "action": "scan", "target": "scanLine", "duration": 3000 }
  ],
  "rollback": {
    "event_type": "STATE_CHANGE",
    "event_code": "POD_UNLOAD"
  }
}</pre>
      </div>
    </div>
  </div>
</template>

<style scoped>
.model-editor {
  padding: 20px;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.editor-header {
  margin-bottom: 20px;
}
.editor-header h1 {
  font-size: 20px;
  margin-bottom: 12px;
}
.header-tabs {
  display: flex;
  gap: 8px;
}
.tab-btn {
  padding: 8px 16px;
  border: 1px solid var(--border);
  background: var(--panel);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.tab-btn:hover {
  border-color: var(--accent);
}
.tab-btn.active {
  background: rgba(0, 212, 255, 0.15);
  border-color: var(--accent);
  color: var(--accent);
}

/* 开发指南 */
.guide-container {
  display: flex;
  gap: 20px;
}
.guide-sidebar {
  width: 260px;
  flex-shrink: 0;
}
.section-btn {
  width: 100%;
  padding: 10px 12px;
  border: none;
  background: var(--panel);
  border-radius: 6px;
  text-align: left;
  font-size: 12px;
  margin-bottom: 6px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.section-btn:hover {
  background: var(--panel-2);
}
.section-btn.active {
  background: rgba(0, 212, 255, 0.15);
  color: var(--accent);
}
.guide-content {
  flex: 1;
}
.guide-section {
  background: var(--panel);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 16px;
}
.guide-section h2 {
  font-size: 15px;
  margin-bottom: 12px;
}
.section-body pre {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--text);
  margin: 0;
}

/* 模型管理 */
.models-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 16px;
}
.btn-primary {
  background: var(--accent);
  color: #000;
  border: none;
  padding: 8px 16px;
  border-radius: 6px;
  font-weight: 700;
  font-size: 13px;
  cursor: pointer;
}
.btn-primary:hover {
  opacity: 0.9;
}
.models-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.model-card {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s;
}
.model-card:hover {
  border-color: var(--accent);
}
.model-card.selected {
  border-color: var(--accent);
  background: rgba(0, 212, 255, 0.08);
}
.model-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.model-id {
  font-family: monospace;
  font-weight: 700;
  color: var(--accent);
}
.model-vendor {
  font-size: 11px;
  color: var(--text-dim);
}
.model-name {
  font-weight: 600;
  margin-bottom: 6px;
}
.model-meta {
  display: flex;
  gap: 8px;
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 8px;
}
.model-desc {
  font-size: 11.5px;
  color: var(--text-dim);
  line-height: 1.4;
}

.create-panel {
  background: var(--panel);
  border-radius: 8px;
  padding: 20px;
}
.create-panel h3 {
  font-size: 15px;
  margin-bottom: 16px;
}
.form-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-bottom: 16px;
}
.form-item.full {
  grid-column: span 2;
}
.form-item label {
  display: block;
  font-size: 11px;
  color: var(--text-dim);
  margin-bottom: 4px;
}
.form-item input, .form-item select, .form-item textarea {
  width: 100%;
  background: var(--bg);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 8px 10px;
  border-radius: 6px;
  font-size: 12.5px;
  outline: none;
}
.form-item input:focus, .form-item select:focus, .form-item textarea:focus {
  border-color: var(--accent);
}
.form-item textarea {
  resize: vertical;
  min-height: 60px;
}

.no-permission {
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.3);
  border-radius: 8px;
  padding: 20px;
  text-align: center;
}
.no-permission p {
  margin: 4px 0;
  color: var(--text-dim);
}

/* 事件代码 */
.events-panel h2 {
  font-size: 16px;
  margin-bottom: 16px;
}
.events-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px;
  margin-bottom: 24px;
}
.event-category {
  background: var(--panel);
  border-radius: 8px;
  padding: 14px;
}
.category-title {
  font-weight: 700;
  font-size: 13px;
  margin-bottom: 10px;
  color: var(--accent);
}
.event-codes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.event-code {
  padding: 4px 10px;
  background: var(--bg);
  border-radius: 12px;
  font-size: 11px;
  font-family: monospace;
  color: var(--text);
}

.mapping-example {
  background: var(--panel);
  border-radius: 8px;
  padding: 20px;
}
.mapping-example h3 {
  font-size: 14px;
  margin-bottom: 12px;
}
.code-block {
  font-family: 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.6;
  background: var(--bg);
  border-radius: 6px;
  padding: 14px;
  overflow-x: auto;
  color: #00d4ff;
}
</style>