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
 * @returns {{ dx: number, dy: number, rdx: number, rdy: number } | null}
 *   dx/dy = 臂局部伸缩量（chuck 用）；rdx/rdy = root 空间伸缩量（晶圆同步平移用，父链纯平移时 1:1）
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
  // 伸缩量模长 e：伸缩臂杆 scale_y/offset_y 驱动参数（杆以收拢态为自然态，伸长 e）
  const e = Math.hypot(lx, ly)
  const lbase = Number(arm.link_lbase)
  return {
    dx: +lx.toFixed(2),
    dy: +(-ly).toFixed(2),
    rdx: +dx.toFixed(2),
    rdy: +(-dy).toFixed(2),
    e: +e.toFixed(2),
    link_sy: Number.isFinite(lbase) && lbase > 0 ? +((lbase + e) / lbase).toFixed(4) : 1,
  }
}

/**
 * 填伸缩量参数：prefix 为空时填 ext/ext_rdx/ret/ret_rdy 系；prefix 为 'pk_' 时填取还片侧参数。
 * 晶圆同步用 root 版（rdx/rdy），chuck 用臂局部版（dx/dy）。
 */
function fillExtendParams(params, v, prefix = '') {
  if (!v) return
  params[`${prefix}ext_dx`] = v.dx
  params[`${prefix}ext_dy`] = v.dy
  params[`${prefix}ret_dx`] = -v.dx
  params[`${prefix}ret_dy`] = -v.dy
  params[`${prefix}ext_rdx`] = v.rdx
  params[`${prefix}ext_rdy`] = v.rdy
  params[`${prefix}ret_rdx`] = -v.rdx
  params[`${prefix}ret_rdy`] = -v.rdy
  // 伸缩臂杆参数：伸出 scale_y 拉长 + offset_y=+e/2 保持顶端藏 chuck 下；收回反向
  params[`${prefix}link_ext_sy`] = v.link_sy ?? 1
  params[`${prefix}link_ext_oy`] = +((v.e || 0) / 2).toFixed(2)
  params[`${prefix}link_ret_sy`] = 1
  params[`${prefix}link_ret_oy`] = -(+((v.e || 0) / 2).toFixed(2))
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

  function armLinkPart(armId) {
    const m = String(armId || '').match(/(\d+)\s*$/)
    return `ARM${m ? m[1] : '1'}_Link`
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
      params.pickup_link = armLinkPart(fromArm)
      params.drop_link = armLinkPart(toArm)
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
        // 取片侧（源腔）伸缩量：blade 伸出进源腔取片用
        fillExtendParams(params, computeExtendVec(ext, fromArm, fromChamber, fromAngle), 'pk_')
      } else {
        const pickupAngle = armAngleFor(angleMap, fromArm, carrier)
        if (pickupAngle == null) {
          return { ok: false, warn: `未配置 ${fromArm} 到 ${carrier || '?'} 的角度` }
        }
        params.from_chamber = ''
        params.from_angle = pickupAngle
        params.from_part = pickupPart
        // 取片侧（cassette 槽位）伸缩量：blade 伸出到 LLA/LLB 取片用
        fillExtendParams(params, computeExtendVec(ext, fromArm, carrier, pickupAngle), 'pk_')
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
      // 放片侧（目标腔）伸缩量：blade 托片进腔/抽刀用
      fillExtendParams(params, computeExtendVec(ext, toArm, chamber, toAngle))
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
      // 取片臂 = 实际服务该腔体的臂（CH_1-4 → ARM_2，A-F → ARM_1）；还片臂 = 服务载具的臂（LLA/LLB → ARM_1）
      const chamberArm = findArmByPos(angleMap, fromChamber)
      if (!chamberArm) {
        return { ok: false, warn: `未在 arm_chamber_angles 中找到上次腔体 ${fromChamber}` }
      }
      const returnArm = findArmByPos(angleMap, carrier)
      if (!returnArm) {
        return { ok: false, warn: `未在 arm_chamber_angles 中找到载具 ${carrier}` }
      }
      const fromAngle = armAngleFor(angleMap, chamberArm, fromChamber)
      if (fromAngle == null) {
        return { ok: false, warn: `未配置 ${chamberArm} 到上次腔体 ${fromChamber} 的角度` }
      }
      const carrierAngle = armAngleFor(angleMap, returnArm, carrier)
      if (carrierAngle == null) {
        return { ok: false, warn: `未配置 ${returnArm} 到 ${carrier} 的角度` }
      }
      const crossArm = chamberArm !== returnArm
      params.ARM = returnArm
      params.arm = returnArm
      params.from_arm = chamberArm
      params.to_arm = returnArm
      params.from_chamber = fromChamber
      params.from_angle = fromAngle
      params.carrier_angle = carrierAngle
      params.to_angle = carrierAngle
      params.pickup_part = armChuckPart(chamberArm)
      params.drop_part = armChuckPart(returnArm)
      params.pickup_link = armLinkPart(chamberArm)
      params.drop_link = armLinkPart(returnArm)
      params.cross_arm = crossArm
      if (crossArm) {
        const crossFrom = armAngleFor(angleMap, chamberArm, 'Cross')
        const crossTo = armAngleFor(angleMap, returnArm, 'Cross')
        if (crossFrom == null) return { ok: false, warn: `未配置 ${chamberArm} 的 Cross 角度` }
        if (crossTo == null) return { ok: false, warn: `未配置 ${returnArm} 的 Cross 角度` }
        params.cross_angle_from = crossFrom
        params.cross_angle_to = crossTo
      }
      // 腔体取片侧：blade 伸出进源腔（ext）/带片收回（ret）
      fillExtendParams(params, computeExtendVec(ext, chamberArm, fromChamber, fromAngle))
      // cassette 还片侧：blade 伸出到槽位（pk_ext）/抽刀（pk_ret）
      fillExtendParams(params, computeExtendVec(ext, returnArm, carrier, carrierAngle), 'pk_')
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
