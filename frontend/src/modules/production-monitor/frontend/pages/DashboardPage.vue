<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAppStore } from '@/stores/app'
import { useAuthStore } from '@/stores/auth'
import KpiCards from '@/modules/production-monitor/frontend/components/floor/KpiCards.vue'
import MachineList from '@/modules/production-monitor/frontend/components/floor/MachineList.vue'
import FloorView3D from '@/modules/production-monitor/frontend/components/floor/FloorView3D.vue'
import FloorPlan from '@/modules/production-monitor/frontend/components/floor/FloorPlan.vue'
import { api } from '@/api'
import { useInterval } from '@/platform/frontend/core/composables/useRafLoop'

const appStore = useAppStore()
const router = useRouter()
const authStore = useAuthStore()

const floors = ref([])
const currentFloor = ref(3)  // 默认主生产楼层
const viewMode = ref('plan')   // 3d / plan
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

// 受管定时器：卸载即清理，页面切到后台时暂停（前台才需要刷 KPI）。
// 必须在 setup 顶层调用，onMounted 内调用会失去组件实例上下文并触发 Vue 警告。
useInterval(() => appStore.fetchStats(), 10000)

onMounted(async () => {
  await appStore.fetchMachines()
  appStore.fetchStats()
  await loadFloors()
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
              :aria-pressed="currentFloor === floor.id"
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
            <button class="view-toggle" type="button" :aria-pressed="viewMode === '3d'" @click="toggleViewMode">
              <svg viewBox="0 0 20 20" fill="none" aria-hidden="true">
                <path v-if="viewMode === '3d'" d="M4 4h12v12H4zM7 7h6v6H7z" stroke="currentColor" stroke-width="1.5"/>
                <path v-else d="m10 2 7 4-7 4-7-4 7-4Zm-7 8 7 4 7-4m-14 4 7 4 7-4" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>
              </svg>
              {{ viewMode === '3d' ? '平面图' : '3D 视图' }}
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
  grid-template-columns: 264px minmax(0, 1fr);
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
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: var(--control-md);
  padding: 0 12px;
  border: 1px solid var(--border-2);
  background: var(--panel);
  color: var(--text-dim);
  border-radius: var(--radius-sm);
  font-size: 12px;
  cursor: pointer;
}
.view-toggle svg { width: 17px; height: 17px; }

.view-toggle:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.view-content {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
}
.fs-btn { border-radius: var(--radius-sm); transition: color 0.15s, background-color 0.15s, border-color 0.15s; }
.fs-btn.active { background: rgba(0, 212, 255, 0.08); }
.floor-selector { border-radius: var(--radius-md); }
@media (max-width: 1366px) {
  .dashboard { gap: 10px; padding: 10px; }
  .dashboard-main { grid-template-columns: 236px minmax(0, 1fr); gap: 10px; }
  .sidebar-section { gap: 10px; }
  .fs-btn { padding: 8px 10px; }
}
@media (max-width: 1280px) {
  .dashboard-main { grid-template-columns: 220px minmax(0, 1fr); }
  .fs-desc, .view-desc { display: none; }
}
</style>
