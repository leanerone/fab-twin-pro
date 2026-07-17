<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '../stores/app'
import { useAuthStore } from '../stores/auth'
import KpiCards from '../components/KpiCards.vue'
import MachineList from '../components/MachineList.vue'
import FloorView3D from '../components/FloorView3D.vue'
import FloorPlan from '../components/FloorPlan.vue'
import { api } from '../api'

const appStore = useAppStore()
const router = useRouter()
const authStore = useAuthStore()

const floors = ref([])
const currentFloor = ref(3)  // 默认主生产楼层
const viewMode = ref('3d')   // 3d / plan
const refreshKey = ref(0)    // 强制刷新3D数据的key

async function loadFloors() {
  try {
    floors.value = await api.getFloors()
  } catch (e) {
    console.error('加载楼层列表失败:', e)
  }
}

function selectMachine(m) {
  appStore.selectMachine(m.id)
  router.push(`/machine/${m.id}`)
}

function switchFloor(floorId) {
  currentFloor.value = floorId
}

function toggleViewMode() {
  const prevMode = viewMode.value
  viewMode.value = viewMode.value === '3d' ? 'plan' : '3d'
  if (viewMode.value === '3d' && prevMode === 'plan') {
    refreshKey.value++
  }
}

onMounted(async () => {
  await appStore.fetchMachines()
  appStore.fetchStats()
  await loadFloors()
  
  setInterval(() => appStore.fetchStats(), 10000)
})
</script>

<template>
  <div class="dashboard">
    <KpiCards />
    
    <div class="dashboard-main">
      <div class="sidebar-section">
        <div class="floor-selector">
          <div class="fs-title">楼层选择</div>
          <div class="fs-buttons">
            <button 
              v-for="floor in floors" 
              :key="floor.id"
              class="fs-btn"
              :class="{ active: currentFloor === floor.id }"
              @click="switchFloor(floor.id)"
            >
              <span class="fs-name">{{ floor.name }}</span>
              <span class="fs-desc">{{ floor.description }}</span>
              <span class="fs-count">{{ floor.machine_count }}台</span>
            </button>
          </div>
        </div>
        
        <MachineList :selected-id="appStore.selectedMachineId" @select="selectMachine" />
      </div>
      
      <div class="main-section">
        <div class="view-header">
          <div class="view-title">
            {{ viewMode === '3d' ? '3D 视图' : '平面图' }} - 
            {{ floors.find(f => f.id === currentFloor)?.name || '' }}
            <span class="view-desc">{{ floors.find(f => f.id === currentFloor)?.description }}</span>
          </div>
          <div class="view-actions">
            <button class="view-toggle" @click="toggleViewMode">
              {{ viewMode === '3d' ? '📋 平面图' : '🎯 3D视图' }}
            </button>
            <button
              v-if="authStore.hasPermission('model_edit')"
              class="view-toggle editor-btn"
              @click="router.push('/model-editor')"
            >
              🔧 模型编辑器
            </button>
          </div>
        </div>
        
        <div class="view-content">
          <FloorView3D 
            v-if="viewMode === '3d'" 
            :floor-id="currentFloor" 
            :force-refresh="refreshKey"
            @select-machine="selectMachine" 
          />
          <FloorPlan 
            v-else 
            :floor-id="currentFloor" 
            @select-machine="selectMachine" 
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  height: 100%;
}

.dashboard-main {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  overflow-y: auto;
}

.floor-selector {
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  flex-shrink: 0;
}

.fs-title {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 1px;
  color: var(--text-dim);
  margin-bottom: 10px;
}

.fs-buttons {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.fs-btn {
  padding: 10px 12px;
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text-dim);
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.fs-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.fs-btn.active {
  background: rgba(0, 212, 255, 0.12);
  color: var(--accent);
  border-color: var(--accent);
}

.fs-name {
  font-size: 14px;
  font-weight: 700;
}

.fs-desc {
  font-size: 10px;
  opacity: 0.7;
}

.fs-count {
  font-size: 10px;
  opacity: 0.6;
  margin-top: 2px;
}

.main-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 0;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 4px;
  flex-shrink: 0;
}

.view-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}

.view-desc {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 400;
  margin-left: 8px;
}

.view-toggle {
  padding: 6px 14px;
  border: 1px solid var(--border);
  background: var(--panel);
  color: var(--text-dim);
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}

.view-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.editor-btn {
  margin-left: 8px;
  border-color: #f59e0b;
  color: #f59e0b;
}

.editor-btn:hover {
  background: rgba(245, 158, 11, 0.15);
}

.view-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
</style>
