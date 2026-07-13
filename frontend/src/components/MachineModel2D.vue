<script setup>
import { computed } from 'vue'

/**
 * 机台2D原理图 - 严格匹配真实设备布局
 * 机械臂: 旋转+伸缩+夹爪开合，晶圆跟随臂尖
 */
const props = defineProps({
  machine: { type: Object, default: null },
  currentState: { type: String, default: 'idle' },
  metrics: { type: Object, default: () => ({}) },
  processStep: { type: String, default: '待机' },
  runState: { type: Object, default: null },
})

const stateColors = {
  run: '#10b981', idle: '#f59e0b', error: '#ef4444',
  loading: '#3b82f6', unloading: '#8b5cf6',
}

// SVG坐标
const POS = {
  smif1: { x: 120, y: 430 },
  smif2: { x: 260, y: 430 },
  port1: { x: 120, y: 360 },
  port2: { x: 260, y: 360 },
  pa: { x: 90, y: 220 },
  arm: { x: 350, y: 230 },
  chamberA: { x: 280, y: 70 },
  chamberB: { x: 430, y: 70 },
  chamberC: { x: 570, y: 230 },
}

const ARM_BASE_LEN = 30    // 臂收回时的基础长度
const ARM_MAX_EXTEND = 120 // 臂最大伸长量
const GRIPPER_OPEN_OFFSET = 22  // 夹爪张开时的间距
const GRIPPER_CLOSE_OFFSET = 14 // 夹爪闭合时的间距

// 计算臂尖位置
const armTip = computed(() => {
  const angle = (props.runState?.armAngle || 90) * Math.PI / 180
  const ext = props.runState?.armExtension || 0
  const len = ARM_BASE_LEN + ext * ARM_MAX_EXTEND
  return {
    x: POS.arm.x + Math.cos(angle) * len,
    y: POS.arm.y + Math.sin(angle) * len,
  }
})

// 夹爪间距（开合）
const gripperOffset = computed(() => {
  if (props.runState?.gripperClosed) return GRIPPER_CLOSE_OFFSET
  return GRIPPER_OPEN_OFFSET
})

// 各模块状态
const chamberStates = computed(() => {
  if (!props.runState?.chambers) return [
    { state: 'idle', wafer: null, progress: 0 },
    { state: 'idle', wafer: null, progress: 0 },
    { state: 'idle', wafer: null, progress: 0 },
  ]
  return props.runState.chambers
})

const chamberColors = computed(() =>
  chamberStates.value.map(c => stateColors[c.state] || '#94a3b8')
)

// 晶圆在各模块位置上的显示
const waferAtPort = computed(() => props.runState?.waferLocation === 'port')
const waferAtPA = computed(() => props.runState?.waferLocation === 'pa')
const waferInChambers = computed(() => {
  const loc = props.runState?.waferLocation
  return {
    A: loc === 'chamberA',
    B: loc === 'chamberB',
    C: loc === 'chamberC',
  }
})
const waferOnArm = computed(() => props.runState?.waferLocation === 'arm')
const armHoldingId = computed(() => props.runState?.armHolding || null)
</script>

<template>
  <div class="machine-2d">
    <svg class="m2d-svg" viewBox="0 0 700 500" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
      <defs>
        <filter id="glow">
          <feGaussianBlur stdDeviation="2" result="b"/>
          <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
        </filter>
      </defs>

      <!-- 背景 -->
      <rect width="700" height="500" fill="#e8ecf0"/>
      <g opacity="0.3">
        <path d="M 0 250 H 700 M 350 0 V 500" stroke="#94a3b8" stroke-width="0.5" stroke-dasharray="4,4"/>
      </g>

      <!-- ===== 连接通道（画在底层） ===== -->
      <rect :x="POS.port1.x + 35" :y="POS.port1.y - 5" width="120" height="10" rx="2" fill="#cbd5e1" stroke="#94a3b8"/>
      <rect :x="POS.port2.x - 115" :y="POS.port2.y - 5" width="120" height="10" rx="2" fill="#cbd5e1" stroke="#94a3b8"/>
      <rect :x="POS.pa.x + 35" :y="POS.pa.y - 5" width="180" height="10" rx="2" fill="#ddd6fe" stroke="#a78bfa"/>
      <rect :x="POS.chamberA.x - 5" :y="POS.chamberA.y + 55" width="10" height="65" rx="2" fill="#cbd5e1" stroke="#94a3b8"/>
      <rect :x="POS.chamberB.x - 5" :y="POS.chamberB.y + 55" width="10" height="65" rx="2" fill="#cbd5e1" stroke="#94a3b8"/>
      <rect :x="POS.arm.x + 80" :y="POS.arm.y - 5" width="140" height="10" rx="2" fill="#cbd5e1" stroke="#94a3b8"/>

      <!-- ===== SMIF1 ===== -->
      <g>
        <rect :x="POS.smif1.x - 40" :y="POS.smif1.y - 25" width="80" height="50" rx="3" fill="#94a3b8" stroke="#64748b" stroke-width="1.5"/>
        <rect :x="POS.smif1.x - 30" :y="POS.smif1.y - 15" width="60" height="30" rx="2" fill="#64748b"/>
        <rect :x="POS.smif1.x - 25" :y="POS.smif1.y - 10" width="15" height="20" rx="1" fill="#fbbf24"/>
        <text :x="POS.smif1.x" :y="POS.smif1.y + 38" fill="#475569" font-size="10" text-anchor="middle" font-weight="bold">SMIF1</text>
      </g>

      <!-- ===== SMIF2 ===== -->
      <g>
        <rect :x="POS.smif2.x - 40" :y="POS.smif2.y - 25" width="80" height="50" rx="3" fill="#94a3b8" stroke="#64748b" stroke-width="1.5"/>
        <rect :x="POS.smif2.x - 30" :y="POS.smif2.y - 15" width="60" height="30" rx="2" fill="#64748b"/>
        <rect :x="POS.smif2.x - 25" :y="POS.smif2.y - 10" width="15" height="20" rx="1" fill="#fbbf24"/>
        <text :x="POS.smif2.x" :y="POS.smif2.y + 38" fill="#475569" font-size="10" text-anchor="middle" font-weight="bold">SMIF2</text>
      </g>

      <!-- ===== PORT1 ===== -->
      <g>
        <rect :x="POS.port1.x - 40" :y="POS.port1.y - 30" width="80" height="60" rx="3" fill="#cbd5e1" stroke="#3b82f6" stroke-width="1.5"/>
        <rect :x="POS.port1.x - 30" :y="POS.port1.y - 15" width="60" height="30" rx="2" fill="#94a3b8"/>
        <!-- PORT上的晶圆 -->
        <circle v-if="waferAtPort" :cx="POS.port1.x" :cy="POS.port1.y" r="12" fill="#f0f4f8" stroke="#0ea5e9" stroke-width="2" filter="url(#glow)"/>
        <text :x="POS.port1.x" :y="POS.port1.y + 44" fill="#1e40af" font-size="10" text-anchor="middle" font-weight="bold">PORT1</text>
      </g>

      <!-- ===== PORT2 ===== -->
      <g>
        <rect :x="POS.port2.x - 40" :y="POS.port2.y - 30" width="80" height="60" rx="3" fill="#cbd5e1" stroke="#3b82f6" stroke-width="1.5"/>
        <rect :x="POS.port2.x - 30" :y="POS.port2.y - 15" width="60" height="30" rx="2" fill="#94a3b8"/>
        <text :x="POS.port2.x" :y="POS.port2.y + 44" fill="#1e40af" font-size="10" text-anchor="middle" font-weight="bold">PORT2</text>
      </g>

      <!-- ===== PA (Pre-Aligner) ===== -->
      <g>
        <rect :x="POS.pa.x - 35" :y="POS.pa.y - 45" width="70" height="90" rx="4" fill="#a78bfa" stroke="#7c3aed" stroke-width="1.5"/>
        <circle :cx="POS.pa.x" :cy="POS.pa.y" r="25" fill="#c4b5fd" stroke="#7c3aed" stroke-width="1"/>
        <circle :cx="POS.pa.x" :cy="POS.pa.y" r="15" fill="#ede9fe"/>
        <!-- PA上的晶圆 -->
        <circle v-if="waferAtPA" :cx="POS.pa.x" :cy="POS.pa.y" r="12" fill="#f0f4f8" stroke="#0ea5e9" stroke-width="2" filter="url(#glow)"/>
        <text :x="POS.pa.x" :y="POS.pa.y - 55" fill="#6d28d9" font-size="11" text-anchor="middle" font-weight="bold">PA</text>
      </g>

      <!-- ===== CHAMBER-A ===== -->
      <g>
        <rect :x="POS.chamberA.x - 45" :y="POS.chamberA.y" width="90" height="55" rx="4" :fill="chamberColors[0] === '#94a3b8' ? '#cbd5e1' : '#dcfce7'" :stroke="chamberColors[0]" stroke-width="2"/>
        <text :x="POS.chamberA.x" :y="POS.chamberA.y + 18" fill="#1e293b" font-size="10" font-weight="bold" text-anchor="middle">CHAMBER_A</text>
        <rect :x="POS.chamberA.x - 30" :y="POS.chamberA.y + 25" width="60" height="20" rx="2" fill="#64748b"/>
        <circle v-if="waferInChambers.A" :cx="POS.chamberA.x" :cy="POS.chamberA.y + 35" r="9" fill="#f0f4f8" stroke="#0ea5e9" stroke-width="1.5" filter="url(#glow)"/>
        <!-- 加工进度条 -->
        <rect v-if="chamberStates[0].state === 'run'" :x="POS.chamberA.x - 35" :y="POS.chamberA.y + 50" width="70" height="4" rx="2" fill="#e2e8f0"/>
        <rect v-if="chamberStates[0].state === 'run'" :x="POS.chamberA.x - 35" :y="POS.chamberA.y + 50" :width="chamberStates[0].progress * 70" height="4" rx="2" fill="#10b981"/>
      </g>

      <!-- ===== CHAMBER-B ===== -->
      <g>
        <rect :x="POS.chamberB.x - 45" :y="POS.chamberB.y" width="90" height="55" rx="4" :fill="chamberColors[1] === '#94a3b8' ? '#cbd5e1' : '#dcfce7'" :stroke="chamberColors[1]" stroke-width="2"/>
        <text :x="POS.chamberB.x" :y="POS.chamberB.y + 18" fill="#1e293b" font-size="10" font-weight="bold" text-anchor="middle">CHAMBER_B</text>
        <rect :x="POS.chamberB.x - 30" :y="POS.chamberB.y + 25" width="60" height="20" rx="2" fill="#64748b"/>
        <circle v-if="waferInChambers.B" :cx="POS.chamberB.x" :cy="POS.chamberB.y + 35" r="9" fill="#f0f4f8" stroke="#0ea5e9" stroke-width="1.5" filter="url(#glow)"/>
        <rect v-if="chamberStates[1].state === 'run'" :x="POS.chamberB.x - 35" :y="POS.chamberB.y + 50" width="70" height="4" rx="2" fill="#e2e8f0"/>
        <rect v-if="chamberStates[1].state === 'run'" :x="POS.chamberB.x - 35" :y="POS.chamberB.y + 50" :width="chamberStates[1].progress * 70" height="4" rx="2" fill="#10b981"/>
      </g>

      <!-- ===== CHAMBER-C ===== -->
      <g>
        <rect :x="POS.chamberC.x" :y="POS.chamberC.y - 35" width="60" height="90" rx="4" :fill="chamberColors[2] === '#94a3b8' ? '#cbd5e1' : '#dcfce7'" :stroke="chamberColors[2]" stroke-width="2"/>
        <text :x="POS.chamberC.x + 30" :y="POS.chamberC.y - 10" fill="#1e293b" font-size="10" font-weight="bold" text-anchor="middle">CHAMBER_C</text>
        <rect :x="POS.chamberC.x + 8" :y="POS.chamberC.y + 5" width="44" height="20" rx="2" fill="#64748b"/>
        <circle v-if="waferInChambers.C" :cx="POS.chamberC.x + 30" :cy="POS.chamberC.y + 15" r="9" fill="#f0f4f8" stroke="#0ea5e9" stroke-width="1.5" filter="url(#glow)"/>
        <rect v-if="chamberStates[2].state === 'run'" :x="POS.chamberC.x + 5" :y="POS.chamberC.y + 35" width="50" height="4" rx="2" fill="#e2e8f0"/>
        <rect v-if="chamberStates[2].state === 'run'" :x="POS.chamberC.x + 5" :y="POS.chamberC.y + 35" :width="chamberStates[2].progress * 50" height="4" rx="2" fill="#10b981"/>
      </g>

      <!-- ===== ARM (八角形中心) ===== -->
      <g :transform="`translate(${POS.arm.x}, ${POS.arm.y})`">
        <!-- 八角形外框 -->
        <polygon points="-80,-35 -55,-80 55,-80 80,-35 80,35 55,80 -55,80 -80,35" fill="#cbd5e1" stroke="#64748b" stroke-width="2"/>
        <polygon points="-65,-28 -45,-65 45,-65 65,-28 65,28 45,65 -45,65 -65,28" fill="#e2e8f0"/>
        <text x="0" y="-55" fill="#475569" font-size="11" font-weight="bold" text-anchor="middle">ARM</text>
        <circle cx="0" cy="0" r="15" fill="#94a3b8" stroke="#64748b" stroke-width="1.5"/>
        <circle cx="0" cy="0" r="6" fill="#64748b"/>

        <!-- ===== 机械臂（旋转+伸缩） ===== -->
        <g :transform="`rotate(${runState?.armAngle || 90})`">
          <!-- 臂杆（长度随extension变化） -->
          <rect x="-5" y="0" width="10" :height="ARM_BASE_LEN + (runState?.armExtension || 0) * ARM_MAX_EXTEND" rx="3" fill="#94a3b8" stroke="#64748b" stroke-width="1"/>
          
          <!-- 夹爪组（在臂尖位置） -->
          <g :transform="`translate(0, ${ARM_BASE_LEN + (runState?.armExtension || 0) * ARM_MAX_EXTEND})`">
            <!-- 左夹爪 -->
            <rect :x="-gripperOffset" y="-5" width="6" height="22" rx="2" fill="#64748b" stroke="#475569" stroke-width="0.5"/>
            <!-- 右夹爪 -->
            <rect :x="gripperOffset - 6" y="-5" width="6" height="22" rx="2" fill="#64748b" stroke="#475569" stroke-width="0.5"/>
            <!-- 夹爪内侧（夹住时显示垫片） -->
            <rect v-if="runState?.gripperClosed" :x="-gripperOffset + 5" y="0" width="3" height="15" rx="1" fill="#8899aa"/>
            <rect v-if="runState?.gripperClosed" :x="gripperOffset - 8" y="0" width="3" height="15" rx="1" fill="#8899aa"/>
            
            <!-- 被夹住的晶圆 -->
            <circle v-if="waferOnArm" cx="0" cy="8" r="13" fill="#f0f4f8" stroke="#0ea5e9" stroke-width="2" filter="url(#glow)"/>
            <text v-if="waferOnArm && armHoldingId" x="0" y="11" fill="#0f172a" font-size="7" font-weight="bold" text-anchor="middle">{{ armHoldingId }}</text>
          </g>
        </g>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.machine-2d {
  width: 100%;
  height: 100%;
  background: #e8ecf0;
  display: flex;
  align-items: center;
  justify-content: center;
}
.m2d-svg {
  width: 100%;
  height: 100%;
}
</style>