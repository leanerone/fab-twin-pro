/**
 * AMAT METSPUT 机型的 Motion 参数推导器（deriver）
 *
 * 从模型组返回包 MotionPreview.vue 抽取的业务状态机：
 * - lotRegistry:      BATCH_INFO_FROM_ECUI 登记 LOT_ID → { PORT, BATCH_ID, ... }
 * - waferPosRegistry: CHAMBER_PS 播放成功后登记 LOT_ID::slot → { chamber }
 *
 * 职责：把事件 payload 推导成 Motion JSON 模板可用的 params
 * （from_arm/to_arm/pickup_part/drop_part/from_angle/to_angle/cross_angle_* 等），
 * 不含任何播放逻辑；角度表读 motionConfig.arm_chamber_angles，不写死。
 */
import { enrichMotionParams } from '../composables/useExprEval'

function waferPosKey(lotId, slot) {
  return `${String(lotId || '').trim()}::${String(slot || '1').trim()}`
}

function normalizeKey(value) {
  return String(value || '').trim().toUpperCase()
}

function buildArmAngleMap(motionConfig) {
  const src = motionConfig?.arm_chamber_angles || {}
  const out = {}
  for (const [armId, angles] of Object.entries(src)) {
    if (!armId || !angles || typeof angles !== 'object' || Array.isArray(angles)) continue
    const table = {}
    for (const [k, v] of Object.entries(angles)) {
      const n = Number(v)
      if (Number.isFinite(n)) table[normalizeKey(k)] = n
    }
    out[armId] = table
  }
  return out
}

/**
 * P1：计算机械臂 R 轴径向伸缩量（臂组局部坐标，写进 offset_x/offset_y）
 * 几何：chuck 旋转后位置 = pivot + R(θ)·(chuckRest − pivot)；
 * 屏幕位移 D = 腔心 − chuckPos；chuck 的 CSS translate 会被臂组上的 rotate(θ) 再旋转，
 * 故局部量 L = R(−θ)·D；offset 写入时 y 翻号（offset_y 为 y-up）。
 * @returns {{ dx: number, dy: number } | null} 局部伸缩量（dx=offset_x, dy=offset_y）
 */
export function computeExtendVec(ext, armId, chamberKey, angleDeg) {
  const geo = ext?.extend_geometry
  const arm = geo?.arms?.[armId]
  const ch = geo?.chambers?.[normalizeKey(chamberKey)]
  const deg = Number(angleDeg)
  if (!arm || !ch || !Number.isFinite(deg)) return null
  const rad = (deg * Math.PI) / 180
  const cos = Math.cos(rad)
  const sin = Math.sin(rad)
  const rx = arm.chuck_x - arm.pivot_x
  const ry = arm.chuck_y - arm.pivot_y
  const px = arm.pivot_x + rx * cos - ry * sin
  const py = arm.pivot_y + rx * sin + ry * cos
  const dx = ch.x - px
  const dy = ch.y - py
  const lx = dx * cos + dy * sin
  const ly = -dx * sin + dy * cos
  return { dx: +lx.toFixed(2), dy: +(-ly).toFixed(2) }
}

export function createAmatMetsputDeriver() {
  const lotRegistry = new Map()
  const waferPosRegistry = new Map()

  function findArmByPos(angleMap, posKey) {
    const key = String(posKey ?? '').trim()
    if (!key) return ''
    const upper = normalizeKey(key)
    for (const [armId, table] of Object.entries(angleMap)) {
      if (table[key] != null || table[upper] != null) return armId
    }
    return ''
  }

  function armAngleFor(angleMap, armId, posKey) {
    if (!armId) return null
    const key = String(posKey ?? '').trim()
    if (!key) return null
    const table = angleMap[armId] || {}
    const angle = table[key] ?? table[normalizeKey(key)]
    return Number.isFinite(angle) ? angle : null
  }

  function armChuckPart(armId) {
    const m = String(armId || '').match(/(\d+)\s*$/)
    return `Wafer_Chuck${m ? m[1] : '1'}`
  }

  /**
   * 推导单步参数
   * @param {string} stepName - motion.step
   * @param {object} eventPayload - 事件 payload（LOT_ID/PORT/SLOT/CHAMBER/...）
   * @param {{ motionConfig: object, ext: object }} ctx
   * @returns {{ ok: boolean, params?: object, info?: string, warn?: string }}
   */
  function derive(stepName, eventPayload, { motionConfig, ext = {} } = {}) {
    const angleMap = buildArmAngleMap(motionConfig)

    if (stepName === 'BATCH_INFO_FROM_ECUI') {
      const lotId = String(eventPayload?.LOT_ID || '').trim()
      if (lotId) {
        lotRegistry.set(lotId, {
          PORT: eventPayload.PORT,
          BATCH_ID: eventPayload.BATCH_ID,
          Qty: eventPayload.Qty,
          RunMode: eventPayload.RunMode,
          RECIPE1: eventPayload.RECIPE1,
        })
      }
    }

    const { params, matchedBy, lotId, carrier, slot } = enrichMotionParams(eventPayload, lotRegistry, ext)

    if (stepName === 'CHAMBER_PS') {
      if (matchedBy !== 'LOT_ID' || !carrier) {
        return { ok: false, warn: `未找到 LOT_ID=${lotId || '?'} 的载具映射，请先触发 BATCH_INFO_FROM_ECUI` }
      }
      const chamber = String(params.CHAMBER || '').trim()
      const waferId = `${carrier}${slot || '1'}`
      const prev = waferPosRegistry.get(waferPosKey(lotId, slot))
      const fromChamber = String(prev?.chamber || '').trim()
      let fromArm = fromChamber ? findArmByPos(angleMap, fromChamber) : findArmByPos(angleMap, carrier)
      if (fromChamber && !fromArm) {
        return { ok: false, warn: `未在 arm_chamber_angles 中找到上次腔体 ${fromChamber}` }
      }
      let toArm = findArmByPos(angleMap, chamber)
      if (fromArm && armAngleFor(angleMap, fromArm, chamber) != null) toArm = fromArm
      if (!fromArm) fromArm = toArm
      const toAngle = armAngleFor(angleMap, toArm, chamber)
      if (!chamber || !toArm) {
        return { ok: false, warn: `未在 arm_chamber_angles 中找到位置 ${chamber || '?'}` }
      }
      if (toAngle == null) {
        return { ok: false, warn: `未配置 ${toArm} 到腔体 ${chamber} 的角度` }
      }
      const pickupPart = armChuckPart(fromArm)
      const dropPart = armChuckPart(toArm)
      const crossArm = Boolean(fromArm && toArm && fromArm !== toArm)
      params.from_arm = fromArm
      params.to_arm = toArm
      params.arm = toArm
      params.ARM = toArm
      params.pickup_part = pickupPart
      params.drop_part = dropPart
      params.cross_arm = crossArm
      params.has_entered_chamber = Boolean(fromChamber)
      if (fromChamber) {
        const fromAngle = armAngleFor(angleMap, fromArm, fromChamber)
        if (fromAngle == null) {
          return { ok: false, warn: `未配置 ${fromArm} 到上次腔体 ${fromChamber} 的角度` }
        }
        params.from_chamber = fromChamber
        params.from_angle = fromAngle
        params.from_part = `CH_${fromChamber}`
      } else {
        const pickupAngle = armAngleFor(angleMap, fromArm, carrier)
        if (pickupAngle == null) {
          return { ok: false, warn: `未配置 ${fromArm} 到 ${carrier || '?'} 的角度` }
        }
        params.from_chamber = ''
        params.from_angle = pickupAngle
        params.from_part = pickupPart
      }
      if (crossArm) {
        const crossFrom = armAngleFor(angleMap, fromArm, 'Cross')
        const crossTo = armAngleFor(angleMap, toArm, 'Cross')
        if (crossFrom == null) return { ok: false, warn: `未配置 ${fromArm} 的 Cross 角度` }
        if (crossTo == null) return { ok: false, warn: `未配置 ${toArm} 的 Cross 角度` }
        params.cross_angle_from = crossFrom
        params.cross_angle_to = crossTo
      }
      params.to_angle = toAngle
      const v = computeExtendVec(ext, toArm, chamber, toAngle)
      if (v) {
        params.ext_dx = v.dx
        params.ext_dy = v.dy
        params.ret_dx = -v.dx
        params.ret_dy = -v.dy
      }
      return { ok: true, params, info: { lotId, carrier, slot, chamber, fromChamber, waferId } }
    }

    if (stepName === 'WAFER_PROCESS_COMPLETE') {
      if (matchedBy !== 'LOT_ID' || !carrier) {
        return { ok: false, warn: `未找到 LOT_ID=${lotId || '?'} 的载具映射，请先触发 BATCH_INFO_FROM_ECUI` }
      }
      const prev = waferPosRegistry.get(waferPosKey(lotId, slot))
      const fromChamber = String(prev?.chamber || params.CHAMBER || '').trim()
      if (!fromChamber) {
        return { ok: false, warn: `未找到 LOT_ID=${lotId} SLOT=${slot || '1'} 的上次腔体，请先触发 CHAMBER_PS` }
      }
      const fromAngle = armAngleFor(angleMap, 'ARM_1', fromChamber)
      if (fromAngle == null) {
        return { ok: false, warn: `未配置 ARM_1 到上次腔体 ${fromChamber} 的角度` }
      }
      const carrierAngle = armAngleFor(angleMap, 'ARM_1', carrier)
      if (carrierAngle == null) {
        return { ok: false, warn: `未配置 ARM_1 到 ${carrier} 的角度` }
      }
      params.ARM = 'ARM_1'
      params.arm = 'ARM_1'
      params.from_arm = 'ARM_1'
      params.to_arm = 'ARM_1'
      params.from_chamber = fromChamber
      params.from_angle = fromAngle
      params.carrier_angle = carrierAngle
      params.to_angle = carrierAngle
      params.pickup_part = armChuckPart('ARM_1')
      params.drop_part = armChuckPart('ARM_1')
      const v = computeExtendVec(ext, 'ARM_1', fromChamber, fromAngle)
      if (v) {
        params.ext_dx = v.dx
        params.ext_dy = v.dy
        params.ret_dx = -v.dx
        params.ret_dy = -v.dy
      }
      return { ok: true, params, info: { lotId, carrier, slot, fromChamber } }
    }

    return { ok: true, params, info: { lotId, carrier, slot } }
  }

  /**
   * 播放成功后的登记（wafer 位置流转）
   */
  function commit(stepName, params, info = {}) {
    const { lotId, slot } = info
    if (stepName === 'CHAMBER_PS') {
      const chamber = String(params?.CHAMBER || '').trim()
      if (lotId && chamber) waferPosRegistry.set(waferPosKey(lotId, slot), { chamber })
    }
    if (stepName === 'WAFER_PROCESS_COMPLETE') {
      if (lotId) waferPosRegistry.delete(waferPosKey(lotId, slot))
    }
  }

  function reset() {
    lotRegistry.clear()
    waferPosRegistry.clear()
  }

  return { derive, commit, reset }
}

export default { createAmatMetsputDeriver }
