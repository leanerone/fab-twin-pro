import { nextTick } from 'vue'
import { resolveTextTemplate } from './useExprEval'

/**
* 动画配置 / 动画调试共用的 Motion 播放引擎。
* 跟随旋转以 measureElementMoveAfterTransform 为准（测量 leader transform 对 snap 目标的位移）。
*/

export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, Math.max(0, ms || 0)))
}

export function easingToCss(easing) {
  if (!easing || easing === 'linear') return 'linear'
  if (easing === 'ease-in') return 'ease-in'
  if (easing === 'ease-out') return 'ease-out'
  if (easing === 'ease-in-out') return 'ease-in-out'
  if (easing === 'mechanical') return 'cubic-bezier(0.25, 0.1, 0.25, 1.0)'
  return easing
}

export function clearMotionTexts(container, kind) {
  if (!container) return
  const selector = kind ? `[data-motion-text="${kind}"]` : '[data-motion-text]'
  container.querySelectorAll(selector).forEach(el => el.remove())
}

export function fillSvgMultilineText(el, content, x, fontSize = 16) {
  const lines = String(content ?? '').replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')
  el.textContent = ''
  const lineHeight = fontSize * 1.3
  lines.forEach((line, i) => {
    const tspan = document.createElementNS(el.namespaceURI, 'tspan')
    tspan.setAttribute('x', String(x))
    if (i > 0) tspan.setAttribute('dy', String(lineHeight))
    tspan.textContent = line.length ? line : '\u00a0'
    el.appendChild(tspan)
  })
}

function getLocalCenter(el) {
  if (!el) return { x: 0, y: 0 }
  const tag = String(el.tagName || '').toLowerCase()
  if (tag === 'circle') {
    return {
      x: Number(el.getAttribute('cx')) || 0,
      y: Number(el.getAttribute('cy')) || 0,
    }
  }
  try {
    const bbox = el.getBBox()
    return { x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 }
  } catch (_) {
    return { x: 0, y: 0 }
  }
}

function syncFollowMotionTexts(el) {
  const id = el?.getAttribute?.('id')
  const svg = el?.ownerSVGElement
  if (!id || !svg) return
  svg.querySelectorAll(`[data-motion-text-follow="${id.replace(/"/g, '\\"')}"]`).forEach((textEl) => {
    textEl.style.transform = el.style.transform
    textEl.style.transformOrigin = el.style.transformOrigin
    textEl.style.transformBox = el.style.transformBox
    textEl.style.transition = el.style.transition
  })
}

function appendAttachedMotionText(targetEl, action, kind, content) {
  const svg = targetEl?.ownerSVGElement
  if (!svg || !targetEl?.parentNode) return null
  const pid = targetEl.getAttribute('id') || ''
  if (pid) {
    svg.querySelectorAll(`[data-motion-text-follow="${pid.replace(/"/g, '\\"')}"]`).forEach(el => el.remove())
  }
  const center = getLocalCenter(targetEl)
  const fontSize = Number(action.fontSize) > 0 ? Number(action.fontSize) : 10
  const el = document.createElementNS(svg.namespaceURI, 'text')
  el.setAttribute('x', String(center.x))
  el.setAttribute('y', String(center.y))
  el.setAttribute('fill', action.fill || '#ffffff')
  el.setAttribute('stroke', action.stroke || '#000000')
  el.setAttribute('stroke-width', String(action.strokeWidth ?? 0.6))
  el.setAttribute('paint-order', 'stroke')
  el.setAttribute('font-size', String(fontSize))
  el.setAttribute('font-family', 'sans-serif')
  el.setAttribute('font-weight', '700')
  el.setAttribute('text-anchor', 'middle')
  el.setAttribute('dominant-baseline', 'central')
  el.setAttribute('xml:space', 'preserve')
  el.setAttribute('data-motion-text', kind)
  if (pid) el.setAttribute('data-motion-text-follow', pid)
  el.style.pointerEvents = 'none'
  el.style.transform = targetEl.style.transform || ''
  el.style.transformOrigin = targetEl.style.transformOrigin || ''
  el.style.transformBox = targetEl.style.transformBox || ''
  el.style.transition = targetEl.style.transition || ''
  fillSvgMultilineText(el, content, center.x, fontSize)
  targetEl.parentNode.insertBefore(el, targetEl.nextSibling)
  return el
}

function removeMotionTextsAt(svg, x, y) {
  if (!svg) return
  const tx = Number(x)
  const ty = Number(y)
  svg.querySelectorAll('[data-motion-text]').forEach((el) => {
    if (Number(el.getAttribute('x')) === tx && Number(el.getAttribute('y')) === ty) el.remove()
  })
}

// ============================================================
// 「信息卡」（text 动作可选面板模式）
// 所有样式字段均可由 JSON action.panel 覆盖，引擎不写死机型专属值
// ============================================================

const TEXT_PANEL_DEFAULTS = {
  width: 170,
  headerHeight: 20,
  rowHeight: 15,
  padX: 10,
  padTop: 13,
  radius: 4,
  bg: '#f4f5f7',
  bgStroke: '#94a3b8',
  screen: '#ffffff',
  screenStroke: '#cbd5e1',
  headerBg: '#2b3340',
  headerFill: '#cbd5e1',
  headerSize: 9,
  headerText: 'INFO',
  badgeFill: '#22a06b',
  badgeKey: '',
  labelFill: '#6b7280',
  labelSize: 8,
  valueFill: '#1f2937',
  valueSize: 10.5,
  sepFill: '#e5e7eb',
  fontFamily: "'Segoe UI','Microsoft YaHei',sans-serif",
  monoFamily: "Consolas,'Courier New',monospace",
}

function mkSvgEl(svg, tag, attrs) {
  const el = document.createElementNS(svg.namespaceURI, tag)
  for (const k in attrs) {
    const v = attrs[k]
    if (v !== undefined && v !== null) el.setAttribute(k, String(v))
  }
  return el
}

/**
 * 信息卡：外框 + 屏幕 + 头栏 + 标签/值两列 + 细分隔线。
 * content 按行解析为「键:值」；键名升位作标签，值右对齐等宽显示。
 * @returns {SVGGElement|null}
 */
function buildTextPanel(svg, action, content, kind) {
  const p = { ...TEXT_PANEL_DEFAULTS, ...(action.panel || {}) }
  const x = Number(action.x)
  const y = Number(action.y)
  const w = Number(p.width)
  const hh = Number(p.headerHeight)
  const rh = Number(p.rowHeight)
  const r = Number(p.radius)
  const px = Number(p.padX)
  const rows = String(content).split('\n').map(s => s.trim()).filter(Boolean).map((line) => {
    const i = line.indexOf(':')
    return i < 0 ? [line, ''] : [line.slice(0, i).trim(), line.slice(i + 1).trim()]
  })
  if (!rows.length) return null
  const ph = hh + Number(p.padTop) + rows.length * rh

  const g = mkSvgEl(svg, 'g', {
    'data-motion-text': kind,
    x: String(x),
    y: String(y),
    'pointer-events': 'none',
  })

  // 外框 + 内屏
  g.appendChild(mkSvgEl(svg, 'rect', {
    x, y, width: w, height: ph, rx: r, fill: p.bg, stroke: p.bgStroke, 'stroke-width': 1.2,
  }))
  g.appendChild(mkSvgEl(svg, 'rect', {
    x: x + 3, y: y + 3, width: w - 6, height: ph - 6, rx: 2, fill: p.screen, stroke: p.screenStroke, 'stroke-width': 0.6,
  }))

  // 头栏（仅上两角圆角）
  const headerD = [
    `M${x + r},${y}`,
    `h${w - 2 * r}`,
    `a${r},${r} 0 0 1 ${r},${r}`,
    `v${hh - r}`,
    `h${-w}`,
    `v${-(hh - r)}`,
    `a${r},${r} 0 0 1 ${r},${-r}`,
    'z',
  ].join(' ')
  g.appendChild(mkSvgEl(svg, 'path', { d: headerD, fill: p.headerBg }))
  const title = mkSvgEl(svg, 'text', {
    x: x + px, y: y + hh - 6, 'font-family': p.fontFamily, 'font-size': p.headerSize,
    fill: p.headerFill, 'letter-spacing': 1,
  })
  title.textContent = String(p.headerText)
  g.appendChild(title)

  // 头栏右侧徽标：取 badgeKey 对应行的值
  const badge = p.badgeKey
    ? rows.find(([k]) => k.toUpperCase() === String(p.badgeKey).toUpperCase())
    : null
  if (badge && badge[1]) {
    const b = mkSvgEl(svg, 'text', {
      x: x + w - px, y: y + hh - 6, 'text-anchor': 'end', 'font-family': p.monoFamily,
      'font-size': p.headerSize, fill: p.badgeFill,
    })
    b.textContent = `${p.badgeKey} ${badge[1]}`
    g.appendChild(b)
  }

  // 数据行（标签 / 值 / 分隔线）
  rows.forEach(([k, v], i) => {
    const ry = y + hh + Number(p.padTop) + i * rh
    const label = mkSvgEl(svg, 'text', {
      x: x + px, y: ry, 'font-family': p.fontFamily, 'font-size': p.labelSize,
      fill: p.labelFill, 'letter-spacing': 0.5,
    })
    label.textContent = k.toUpperCase()
    g.appendChild(label)
    const value = mkSvgEl(svg, 'text', {
      x: x + w - px, y: ry, 'text-anchor': 'end', 'font-family': p.monoFamily,
      'font-size': p.valueSize, fill: p.valueFill,
    })
    value.textContent = v
    g.appendChild(value)
    if (i < rows.length - 1) {
      g.appendChild(mkSvgEl(svg, 'line', {
        x1: x + px, y1: ry + 5.5, x2: x + w - px, y2: ry + 5.5,
        stroke: p.sepFill, 'stroke-width': 0.6,
      }))
    }
  })

  return g
}

export function appendMotionText(svg, action, kind, params = {}, targetEl = null) {
  const content = resolveTextTemplate(action.content, params)
  const isClear = !String(content ?? '').trim()
  if (targetEl) {
    if (isClear) {
      const pid = targetEl.getAttribute('id') || ''
      const owner = targetEl.ownerSVGElement
      if (pid && owner) {
        owner.querySelectorAll(`[data-motion-text-follow="${pid.replace(/"/g, '\\"')}"]`).forEach(el => el.remove())
      }
      return null
    }
    return appendAttachedMotionText(targetEl, action, kind, content)
  }
  if (!svg) return null
  const x = action.x ?? action.textX
  const y = action.y ?? action.textY
  if (!Number.isFinite(Number(x)) || !Number.isFinite(Number(y))) return null
  removeMotionTextsAt(svg, x, y)
  if (isClear) return null
  // 信息卡模式：x/y 为卡片左上角，content 按「键:值」行渲染为屏幕式信息卡
  if (action.panel) {
    const panel = buildTextPanel(svg, action, content, kind)
    if (panel) svg.appendChild(panel)
    return panel
  }
  const el = document.createElementNS(svg.namespaceURI, 'text')
  el.setAttribute('x', String(x))
  el.setAttribute('y', String(y))
  el.setAttribute('fill', '#000000')
  el.setAttribute('font-size', '16')
  el.setAttribute('font-family', 'sans-serif')
  el.setAttribute('xml:space', 'preserve')
  el.setAttribute('data-motion-text', kind)
  el.style.pointerEvents = 'none'
  fillSvgMultilineText(el, content, x, 16)
  svg.appendChild(el)
  return el
}

export const PART_ID_ALIASES = {
  Wafer_Chuck1: ['svg_49'],
  svg_49: ['Wafer_Chuck1'],
}

export function findPreviewPart(container, partId) {
  if (!container || !partId) return null
  const candidates = [partId, ...(PART_ID_ALIASES[partId] || [])]
  for (const id of candidates) {
    const el = container.querySelector(`#${CSS.escape(id)}`)
      || container.querySelector(`[id="${id.replace(/"/g, '\\"')}"]`)
    if (el) return el
  }
  return null
}

function parseRotateDeg(value) {
  const match = String(value || '').match(/rotate\(([-\d.]+)deg\)/)
  return match ? Number(match[1]) || 0 : 0
}

function getElementCenterRect(el) {
  const rect = el.getBoundingClientRect()
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
}

function svgMatrixToDOM(m) {
  return new DOMMatrix([m.a, m.b, m.c, m.d, m.e, m.f])
}

function applyMatrixPoint(m, x, y) {
  return { x: m.a * x + m.c * y + m.e, y: m.b * x + m.d * y + m.f }
}

function getRotateOriginScreen(el) {
  const svg = el?.ownerSVGElement
  if (!el || !svg) return el ? getElementCenterRect(el) : { x: 0, y: 0 }
  let bbox
  try { bbox = el.getBBox() } catch (_) { return getElementCenterRect(el) }
  const cx = bbox.x + bbox.width / 2
  const cy = bbox.y + bbox.height / 2
  const screenCTM = el.getScreenCTM()
  if (!screenCTM) return getElementCenterRect(el)
  return applyMatrixPoint(svgMatrixToDOM(screenCTM), cx, cy)
}

function applyPreviewTransform(el, state) {
  const parts = []
  if (state.translateX || state.translateY) {
    parts.push(`translate(${state.translateX}px, ${state.translateY}px)`)
  }
  if (state.rotate) {
    el.style.transformBox = 'fill-box'
    parts.push(state.rotate)
  }
  if (state.scale) {
    parts.push(state.scale)
  }
  el.style.transformOrigin = state.origin || ''
  el.style.transform = parts.join(' ')
  syncFollowMotionTexts(el)
}

function rotatePointAround(origin, point, deg) {
  const rad = (deg * Math.PI) / 180
  const dx = point.x - origin.x
  const dy = point.y - origin.y
  return {
    x: origin.x + dx * Math.cos(rad) - dy * Math.sin(rad),
    y: origin.y + dx * Math.sin(rad) + dy * Math.cos(rad),
  }
}

function ensurePreviewState(previewStates, pid) {
  if (!previewStates.has(pid)) {
    previewStates.set(pid, { translateX: 0, translateY: 0, rotate: '', scale: '', origin: '' })
  }
  return previewStates.get(pid)
}

function readPreviewStateFromEl(el) {
  const transform = el.style.transform || ''
  const translateMatch = transform.match(/translate\(\s*([-\d.]+)px\s*,\s*([-\d.]+)px\s*\)/)
  const rotateMatch = transform.match(/rotate\(\s*([-\d.]+)deg\s*\)/)
  const scaleMatch = transform.match(/scale\(([^)]+)\)/)
  return {
    translateX: translateMatch ? Number(translateMatch[1]) || 0 : 0,
    translateY: translateMatch ? Number(translateMatch[2]) || 0 : 0,
    rotate: rotateMatch ? `rotate(${rotateMatch[1]}deg)` : '',
    scale: scaleMatch ? `scale(${scaleMatch[1]})` : '',
    origin: el.style.transformOrigin || '',
  }
}

function seedPreviewStatesFromDom(container, previewStates) {
  if (!container) return
  for (const el of container.querySelectorAll('[id]')) {
    const id = el.getAttribute('id')
    if (!id || !el.style.transform) continue
    previewStates.set(id, readPreviewStateFromEl(el))
  }
}

function setPreviewTransition(el, duration, easing) {
  el.style.transition = duration > 0
    ? `transform ${duration}ms ${easing}, opacity ${duration}ms ${easing}`
    : 'none'
}

function resolveFollowAngles(phaseItems, action, fromAngle) {
  let toAngle = action.angle || 0
  for (const { rule: leaderRule } of (phaseItems || [])) {
    if (leaderRule.target_part_id !== action.follow_part_id) continue
    const leaderRotate = (Array.isArray(leaderRule.actions) ? leaderRule.actions : [])
      .find(item => item?.type === 'rotate' && !item.follow_part_id)
    if (leaderRotate) toAngle = leaderRotate.angle || 0
  }
  return { fromAngle: fromAngle || 0, toAngle, delta: toAngle - (fromAngle || 0) }
}

function findLatestSnapDestEl(orderedRules, followerId, container, beforePhase) {
  let destId = ''
  for (const { rule, phase } of (orderedRules || [])) {
    if (Number(phase) >= Number(beforePhase)) continue
    if (rule.target_part_id !== followerId) continue
    for (const action of (Array.isArray(rule.actions) ? rule.actions : [])) {
      if (action?.type === 'snap' || action?.type === 'move_to') {
        destId = action.to_part_id || action.target_part_id || action.to || destId
      }
    }
  }
  return findPreviewPart(container, destId)
}

function findRotatingLeaderForFollow(container, followEl, rotatingLeaders) {
  if (!followEl) return { leaderId: '', leaderEl: null }
  for (const leaderId of rotatingLeaders || []) {
    const leaderEl = findPreviewPart(container, leaderId)
    if (!leaderEl) continue
    if (leaderEl === followEl || leaderEl.contains(followEl)) {
      return { leaderId, leaderEl }
    }
  }
  return { leaderId: '', leaderEl: null }
}

function forceReflow(el) {
  el?.getBoundingClientRect()
}

function measureElementMoveAfterTransform(leaderEl, leaderState, trackedEl) {
  if (!leaderEl || !trackedEl || !leaderState) return { dx: 0, dy: 0, start: null, end: null }
  const start = getElementCenterRect(trackedEl)
  const prev = {
    transition: leaderEl.style.transition,
    transform: leaderEl.style.transform,
    transformOrigin: leaderEl.style.transformOrigin,
    transformBox: leaderEl.style.transformBox,
  }
  leaderEl.style.transition = 'none'
  applyPreviewTransform(leaderEl, leaderState)
  forceReflow(leaderEl)
  const end = getElementCenterRect(trackedEl)
  leaderEl.style.transition = 'none'
  leaderEl.style.transform = prev.transform
  leaderEl.style.transformOrigin = prev.transformOrigin
  leaderEl.style.transformBox = prev.transformBox
  forceReflow(leaderEl)
  leaderEl.style.transition = prev.transition
  return { dx: end.x - start.x, dy: end.y - start.y, start, end }
}

function syncFollowerToSnap(plan, previewStates) {
  const followerEl = plan?.followerEl
  const snapEl = plan?.snapEl || followerEl
  if (!followerEl || !snapEl) return
  const state = ensurePreviewState(previewStates, plan.followerId)
  const src = getElementCenterRect(followerEl)
  const dst = getElementCenterRect(snapEl)
  state.translateX += dst.x - src.x
  state.translateY += dst.y - src.y
  state.rotate = ''
  applyPreviewTransform(followerEl, state)
}

function animateFollowersWithLeader(followPlans, previewStates, duration, onPartBase) {
  return new Promise((resolve) => {
    const start = performance.now()
    const tick = (now) => {
      for (const plan of followPlans || []) syncFollowerToSnap(plan, previewStates)
      if (now - start >= duration) {
        for (const plan of followPlans || []) {
          syncFollowerToSnap(plan, previewStates)
          const st = previewStates.get(plan.followerId)
          if (st) onPartBase?.(plan.followerId, { x: st.translateX, y: st.translateY })
        }
        resolve()
        return
      }
      requestAnimationFrame(tick)
    }
    requestAnimationFrame(tick)
  })
}

function collectPhaseFollowPlans(container, phaseItems, orderedRules, phase) {
  const plans = []
  const seen = new Set()
  const rotatingLeaders = []
  for (const { rule } of (phaseItems || [])) {
    const actions = Array.isArray(rule.actions) ? rule.actions : []
    if (actions.some(action => action?.type === 'rotate' && !action.follow_part_id)) {
      rotatingLeaders.push(rule.target_part_id)
    }
  }

  for (const { rule } of (phaseItems || [])) {
    const pid = rule.target_part_id
    for (const action of (Array.isArray(rule.actions) ? rule.actions : [])) {
      if (action?.type !== 'rotate' || !action.follow_part_id) continue
      const followerEl = findPreviewPart(container, pid)
      const followEl = findPreviewPart(container, action.follow_part_id)
      if (!followerEl || !followEl) continue
      const rotating = findRotatingLeaderForFollow(container, followEl, rotatingLeaders)
      const leaderId = rotating.leaderId || action.follow_part_id
      const leaderEl = rotating.leaderEl || followEl
      const snapEl = findLatestSnapDestEl(orderedRules, pid, container, phase)
      plans.push({
        followerId: pid,
        leaderId,
        followerEl,
        leaderEl,
        snapEl: snapEl || followEl || followerEl,
        explicit: true,
      })
      seen.add(pid)
    }
  }

  for (const { rule } of (phaseItems || [])) {
    const pid = rule.target_part_id
    if (seen.has(pid)) continue
    const snapEl = findLatestSnapDestEl(orderedRules, pid, container, phase)
    if (!snapEl) continue
    for (const leaderId of rotatingLeaders) {
      if (!leaderId || leaderId === pid) continue
      const leaderEl = findPreviewPart(container, leaderId)
      if (!leaderEl) continue
      if (leaderEl !== snapEl && !leaderEl.contains(snapEl)) continue
      const followerEl = findPreviewPart(container, pid)
      if (!followerEl) continue
      plans.push({
        followerId: pid,
        leaderId,
        followerEl,
        leaderEl,
        snapEl,
        explicit: false,
      })
      seen.add(pid)
      break
    }
  }
  return plans
}

function applyFollowRotate(container, previewStates, frozenOrigins, pid, el, state, action, phaseItems, fromAngle, orderedRules, phase) {
  const followEl = findPreviewPart(container, action.follow_part_id)
  if (!followEl) return
  const rotatingLeaders = []
  for (const { rule } of (phaseItems || [])) {
    const actions = Array.isArray(rule.actions) ? rule.actions : []
    if (actions.some(item => item?.type === 'rotate' && !item.follow_part_id)) {
      rotatingLeaders.push(rule.target_part_id)
    }
  }
  const rotating = findRotatingLeaderForFollow(container, followEl, rotatingLeaders)
  const leaderId = rotating.leaderId || action.follow_part_id
  const leaderEl = rotating.leaderEl || followEl
  const leaderState = previewStates.get(leaderId)
  const snapEl = findLatestSnapDestEl(orderedRules, pid, container, phase) || followEl || el
  if (leaderState) {
    const move = measureElementMoveAfterTransform(leaderEl, leaderState, snapEl)
    state.translateX += move.dx
    state.translateY += move.dy
    state.rotate = ''
    console.log('[follow]', { pid, leader: leaderId, follow: action.follow_part_id, ...move })
    return
  }
  const startAngle = fromAngle ?? parseRotateDeg(previewStates.get(leaderId)?.rotate)
  const { delta } = resolveFollowAngles(phaseItems, { ...action, follow_part_id: leaderId }, startAngle)
  const origin = frozenOrigins.get(leaderId) || getRotateOriginScreen(leaderEl)
  const center = getElementCenterRect(snapEl)
  const next = rotatePointAround(origin, center, delta)
  const dx = next.x - center.x
  const dy = next.y - center.y
  state.translateX += dx
  state.translateY += dy
  state.rotate = ''
  console.log('[follow]', { pid, leader: leaderId, follow: action.follow_part_id, origin, center, delta, dx, dy })
}

function applyActionVisibility(el, action) {
  if (!el || !action) return
  if (action.visible !== true && action.visible !== false) return
  if (action.visible) {
    el.removeAttribute('visibility')
    el.style.visibility = ''
  } else {
    el.setAttribute('visibility', 'hidden')
    el.style.visibility = 'hidden'
  }
}

function applyPreviewAction(container, ctm, el, state, action, onWarn) {
  if (action.type === 'text') {
    appendMotionText(container?.querySelector('svg'), action, 'preview', {}, el)
    return
  }
  if (!el || !state) return
  applyActionVisibility(el, action)
  if (action.type === 'offset') {
    state.translateX += (action.offset_x || 0) * ctm.a
    state.translateY += -((action.offset_y || 0) * ctm.d)
    return
  }
  if (action.type === 'rotate') {
    const useCenter = !action.pivot || (action.pivot.x === 0 && action.pivot.y === 0)
    state.origin = useCenter ? 'center' : `${action.pivot.x}px ${action.pivot.y}px`
    state.rotate = `rotate(${action.angle || 0}deg)`
    return
  }
  if (action.type === 'scale') {
    state.scale = `scale(${action.scale_x ?? 1}, ${action.scale_y ?? 1})`
    return
  }
  if (action.type === 'opacity') {
    el.style.opacity = String(action.to ?? 1)
    return
  }
  if (action.type === 'visibility') {
    applyActionVisibility(el, { visible: action.to })
    return
  }
  if (action.type === 'snap' || action.type === 'move_to') {
    const destId = String(action.to_part_id || action.target_part_id || action.to || '').trim()
    if (destId === '{home}' || destId === 'home') {
      state.translateX = 0
      state.translateY = 0
      return
    }
    const destEl = findPreviewPart(container, destId)
    if (!destEl) {
      console.warn('[snap] 目标部件未找到:', destId)
      onWarn?.(`snap 找不到目标「${destId}」，请确认 SVG 已包含该 id`)
      return
    }
    const srcRect = el.getBoundingClientRect()
    const dstRect = destEl.getBoundingClientRect()
    state.translateX += (dstRect.left + dstRect.width / 2) - (srcRect.left + srcRect.width / 2)
    state.translateY += (dstRect.top + dstRect.height / 2) - (srcRect.top + srcRect.height / 2)
  }
}

/**
* 按 phase 播放已解析的 rules（与动画配置单击动作相同的几何逻辑）。
* @param {object} options
* @param {Element} options.container SVG 容器
* @param {object[]} options.rules 已 resolveMotionRule 的规则
* @param {Function} [options.onClearTransforms]
* @param {Function} [options.onPartBase] (pid, {x,y}) => void
* @param {Function} [options.onWarn] (msg) => void
* @param {boolean} [options.reset=true] 为 false 时保留已有变换和文字，用于调试页连播
*/
export async function playMotion({
  container,
  rules,
  onClearTransforms,
  onPartBase,
  onWarn,
  reset = true,
} = {}) {
  const empty = { ok: false, playedPids: new Set(), hasText: false }
  if (!container) return { ...empty, reason: 'container' }
  const svg = container.querySelector('svg')
  if (!svg) return { ...empty, reason: 'svg' }
  const ctm = svg.getScreenCTM()
  if (!ctm) return { ...empty, reason: 'ctm' }
  if (ctm.a === 0 || ctm.d === 0) return { ...empty, reason: 'ctm-scale' }

  const matchedRules = Array.isArray(rules) ? rules : []
  if (matchedRules.length === 0) return { ...empty, reason: 'no-rules' }

  const orderedRules = matchedRules
    .map((rule, order) => ({
      rule,
      order,
      phase: Number.isFinite(rule.phase) ? Math.max(0, Math.floor(rule.phase)) : 0,
    }))
    .sort((left, right) => left.phase - right.phase || left.order - right.order)

  const previewStates = new Map()
  const playedPids = new Set()

  if (reset) {
    clearMotionTexts(container)
    if (typeof onClearTransforms === 'function') onClearTransforms()
    await nextTick()
    await sleep(0)
  } else {
    seedPreviewStatesFromDom(container, previewStates)
  }

  const frozenOrigins = new Map()
  const captureFrozenOrigin = (id) => {
    if (!id || frozenOrigins.has(id)) return
    const el = findPreviewPart(container, id)
    if (el) frozenOrigins.set(id, getRotateOriginScreen(el))
  }
  for (const { rule } of orderedRules) {
    captureFrozenOrigin(rule.target_part_id)
    for (const action of (Array.isArray(rule.actions) ? rule.actions : [])) {
      if (action?.follow_part_id) captureFrozenOrigin(action.follow_part_id)
    }
  }

  const phases = new Map()
  for (const item of orderedRules) {
    if (!phases.has(item.phase)) phases.set(item.phase, [])
    phases.get(item.phase).push(item)
  }

  for (const phase of [...phases.keys()].sort((a, b) => a - b)) {
    const phaseItems = phases.get(phase) || []
    const followPlans = collectPhaseFollowPlans(container, phaseItems, orderedRules, phase)
    const hasFollow = followPlans.length > 0
    const phaseStartAngles = new Map()
    for (const [id, st] of previewStates.entries()) {
      phaseStartAngles.set(id, parseRotateDeg(st.rotate))
    }

    if (!hasFollow) {
      for (const { rule } of phaseItems) {
        const pid = rule.target_part_id
        const actions = Array.isArray(rule.actions) ? rule.actions : []
        if (actions.length === 0) continue
        const el = findPreviewPart(container, pid)
        if (!el) {
          for (const action of actions) {
            if (action?.type === 'text') applyPreviewAction(container, ctm, null, null, action, onWarn)
          }
          continue
        }
        playedPids.add(pid)
        const state = ensurePreviewState(previewStates, pid)
        for (const action of actions) {
          if (!action) continue
          const duration = action.duration || 0
          setPreviewTransition(el, duration, easingToCss(action.easing))
          if (action.type === 'rotate' && action.follow_part_id) {
            applyFollowRotate(
              container, previewStates, frozenOrigins, pid, el, state, action, phaseItems,
              phaseStartAngles.get(action.follow_part_id) || 0, orderedRules, phase
            )
          } else {
            applyPreviewAction(container, ctm, el, state, action, onWarn)
          }
          applyPreviewTransform(el, state)
          onPartBase?.(pid, { x: state.translateX, y: state.translateY })
          if (duration > 0) await sleep(duration)
        }
      }
      continue
    }

    let maxDuration = 0
    const touched = new Set()
    const skipFollowRotate = new Set(followPlans.map(plan => plan.followerId))
    for (const { rule } of phaseItems) {
      const pid = rule.target_part_id
      const actions = Array.isArray(rule.actions) ? rule.actions : []
      if (actions.length === 0) continue
      const el = findPreviewPart(container, pid)
      if (!el) {
        for (const action of actions) {
          if (action?.type === 'text') applyPreviewAction(container, ctm, null, null, action, onWarn)
        }
        continue
      }
      playedPids.add(pid)
      touched.add(pid)
      const state = ensurePreviewState(previewStates, pid)
      for (const action of actions) {
        if (!action) continue
        const duration = action.duration || 0
        maxDuration = Math.max(maxDuration, duration)
        if (action.type === 'rotate' && (action.follow_part_id || skipFollowRotate.has(pid))) {
          setPreviewTransition(el, 0, 'linear')
          continue
        }
        setPreviewTransition(el, duration, easingToCss(action.easing))
        applyPreviewAction(container, ctm, el, state, action, onWarn)
      }
    }

    for (const pid of touched) {
      if (skipFollowRotate.has(pid)) continue
      const el = findPreviewPart(container, pid)
      const state = previewStates.get(pid)
      if (!el || !state) continue
      applyPreviewTransform(el, state)
      onPartBase?.(pid, { x: state.translateX, y: state.translateY })
    }

    for (const plan of followPlans) {
      if (plan.followerEl) setPreviewTransition(plan.followerEl, 0, 'linear')
      touched.add(plan.followerId)
    }
    forceReflow(container)
    for (const plan of followPlans) syncFollowerToSnap(plan, previewStates)

    if (maxDuration > 0) {
      await animateFollowersWithLeader(followPlans, previewStates, maxDuration, onPartBase)
    } else {
      for (const plan of followPlans) {
        const st = previewStates.get(plan.followerId)
        if (st) onPartBase?.(plan.followerId, { x: st.translateX, y: st.translateY })
      }
    }
  }

  const hasText = orderedRules.some(({ rule }) => (rule.actions || []).some(action => action?.type === 'text'))
  return { ok: true, playedPids, hasText }
}
