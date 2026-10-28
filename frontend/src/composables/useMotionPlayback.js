/**
 * 平台版 Motion 播放器（SVG user space 版）
 *
 * 与模型组返回包 useMotionPlayback.js 播放语义对齐，关键差异：
 * 1. 全链路 SVG user space 纯几何：加载时用 getBBox()+getCTM() 一次性测量基准中心，
 *    播放过程不依赖 getScreenCTM()/getBoundingClientRect()。
 *    → 历史回放 seek、容器 CSS 缩放、视图隐藏后再显示均不影响几何正确性。
 * 2. 支持 mode: 'instant'（无过渡无等待，直接落到终态），用于历史回放 seek。
 * 3. 部件别名不写死，由 options.partAliases 注入（来自 Motion JSON ext.part_aliases）。
 * 4. 旋转统一用「绕自身中心等效」表示：外部 pivot / 跟随旋转都折算成 rotate + translate，
 *    transform-origin 恒为 fill-box center，状态可增量累积。
 *
 * 保留能力（用户批准的 7 动作 + 4 特性）：
 *   动作：offset / rotate / scale / opacity / visibility(折叠在 action.visible) / snap / text
 *   特性：phase 分组升序播放（同 phase 并发）、follow 跟随旋转、snap 吸附、文字跟随
 *
 * 坐标约定：
 *   - offset_y 正方向向上（SVG y 轴向下，内部取负）
 *   - rotate angle 单位 deg，CSS 顺时针为正（与模型组编辑器一致）
 *   - text action 的 x/y 直接是 SVG user space 坐标（与模型组实现一致，不做 y 翻转）
 */

import { nextTick } from 'vue'
import { resolveTextTemplate } from './useExprEval'

export function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms))
}

export function easingToCss(easing) {
  switch (easing) {
    case 'linear': return 'linear'
    case 'ease-out': return 'ease-out'
    case 'ease-in': return 'ease-in'
    case 'ease-in-out': return 'ease-in-out'
    case 'mechanical': return 'cubic-bezier(0.25, 0.1, 0.25, 1.0)'
    default: return 'ease'
  }
}

// 跟随弧线的 JS 缓动近似（仅用于从动件逐帧插值；主动件仍走原生 CSS transition）
function easingFn(easing) {
  switch (easing) {
    case 'linear': return t => t
    case 'ease-out': return t => 1 - Math.pow(1 - t, 3)
    case 'ease-in': return t => t * t * t
    default: return t => t * t * (3 - 2 * t) // ease-in-out / mechanical 近似
  }
}

// ============================================================
// 基准几何测量（一次性，user space）
// ============================================================

// WeakMap<svgRoot, Map<pid, { cx, cy, invA, invB, invC, invD }>>
// cx/cy: 部件基准中心（SVG root user space）
// invA~invD: 父坐标系逆矩阵的线性部分（root 位移 → 元素本地位移）
const geomCache = new WeakMap()

function getLocalCenter(el) {
  if (!el) return { x: 0, y: 0 }
  const tag = String(el.tagName || '').toLowerCase()
  if (tag === 'circle') {
    return { x: Number(el.getAttribute('cx')) || 0, y: Number(el.getAttribute('cy')) || 0 }
  }
  try {
    const bbox = el.getBBox()
    return { x: bbox.x + bbox.width / 2, y: bbox.y + bbox.height / 2 }
  } catch (_) {
    return null
  }
}

function measureSvg(container, onWarn) {
  const svg = container?.querySelector('svg')
  if (!svg) return null
  let geom = geomCache.get(svg)
  if (geom) return geom
  geom = new Map()
  // getCTM() 含 viewBox→viewport 的渲染缩放 s（本页 s≈1.197），而 deriver 注入的位移
  // （ext_dx/dy 等）是 viewBox 单位；applyState 用含 1/s 的 inv 换算时会把位移二次缩放，
  // 导致 chuck 少伸 ~16%、晶圆偏离腔心 ~23px。统一改用「viewBox(user) 坐标系」：
  // 以 M = svg.getScreenCTM().inverse()（screen→user）把元素/父链 CTM 归一到 user 单位，
  // 与 deriver / extend_geometry 的 viewBox 几何对齐。getScreenCTM 不可用时回退 getCTM。
  let toUser = null
  try {
    const sctm = svg.getScreenCTM()
    toUser = sctm ? sctm.inverse() : null
  } catch (_) { toUser = null }
  const userCtmOf = (el) => {
    if (toUser) {
      try {
        const m = el.getScreenCTM()
        if (m) return toUser.multiply(m)
      } catch (_) { /* fall through to getCTM */ }
    }
    try { return el.getCTM() } catch (_) { return null }
  }
  for (const el of svg.querySelectorAll('[id]')) {
    const id = el.getAttribute('id')
    if (!id) continue
    const local = getLocalCenter(el)
    if (!local) continue // 元素未渲染（display:none 等），跳过，用到时再告警
    const ctm = userCtmOf(el)
    if (!ctm) continue
    const root = new DOMPoint(local.x, local.y).matrixTransform(ctm)
    // 父链 CTM 的逆（线性部分），用于把 root(user) 空间位移换算成本地 CSS translate
    let inv = null
    const parent = el.parentElement
    if (parent && !(parent instanceof SVGSVGElement)) {
      try {
        const p = userCtmOf(parent)
        if (p) inv = p.inverse()
      } catch (_) { inv = null }
    }
    geom.set(id, {
      cx: root.x,
      cy: root.y,
      invA: inv ? inv.a : 1, invB: inv ? inv.b : 0,
      invC: inv ? inv.c : 0, invD: inv ? inv.d : 1,
    })
  }
  geomCache.set(svg, geom)
  return geom
}

/** SVG 结构变化（重新加载）后调用，丢弃几何缓存 */
export function invalidateMotionGeometry(container) {
  const svg = container?.querySelector('svg')
  if (svg) geomCache.delete(svg)
}

// ============================================================
// 播放状态（每容器持久，跨多次 playMotion 累积）
// ============================================================

// WeakMap<container, Map<pid, { tx, ty, rotate, scale }>>
// tx/ty: root user space 位移累积；rotate: 绝对角度 deg；scale: 绝对缩放
const stateCache = new WeakMap()

function getStateMap(container, create = true) {
  let m = stateCache.get(container)
  if (!m && create) {
    m = new Map()
    stateCache.set(container, m)
  }
  return m
}

function ensureState(states, pid) {
  if (!states.has(pid)) states.set(pid, { tx: 0, ty: 0, rotate: 0, scale: 1, scaleY: 1 })
  return states.get(pid)
}

function currentCenter(geom, states, pid) {
  const g = geom.get(pid)
  if (!g) return null
  const st = states.get(pid)
  return { x: g.cx + (st?.tx || 0), y: g.cy + (st?.ty || 0) }
}

/**
 * 视觉中心：基准中心 + 父链祖先 state（旋转/平移）带动 + 自身平移
 * currentCenter 只看自身 state，父 group（如 ARM_1）旋转后其子件（Wafer_Chuck1）
 * 的视觉位置已变，但基准中心没跟上 → snap/follow 会落到未旋转的旧位置。
 * 这里沿 DOM 父链逐级套用祖先 state，还原真实视觉位置（对齐完整版 getBoundingClientRect 语义）。
 */
function visualCenter(ctx, pid) {
  const { geom, states, container, partAliases } = ctx
  const g = geom.get(pid)
  if (!g) return null
  const el = findMotionPart(container, pid, partAliases)
  if (!el) return currentCenter(geom, states, pid)
  const svg = container.querySelector('svg')
  // 祖先 id 链（远 → 近）
  const ancestors = []
  let node = el.parentElement
  while (node && node !== svg && node !== container) {
    const id = node.getAttribute?.('id')
    if (id) ancestors.unshift(id)
    node = node.parentElement
  }
  // 沿父链累计动态旋转量：CSS 中子元素的 translate 会被父级动态 rotate 一起旋转
  // （p ↦ O + t + R(θ)(p − O)，t 在 R(θ) 内部），故各级 tx/ty 须按对应累计角旋转后再加。
  let rotSum = 0
  let p = { x: g.cx, y: g.cy }
  for (const ancId of ancestors) {
    if (ancId === pid) continue
    const s = states.get(ancId)
    if (!s || (!s.rotate && !s.tx && !s.ty)) continue
    if (s.rotate) {
      // 祖先绕自身视觉中心旋转（其视觉中心同样含更高祖先的带动，递归求）
      const pivot = visualCenter(ctx, ancId)
      if (pivot) p = rotatePointAround(pivot, p, s.rotate)
    }
    if (s.tx || s.ty) {
      // 祖先平移在其父空间施加，仅受更高祖先旋转影响（不含自身 rotate）
      const t = rotSum ? rotateVector(s.tx, s.ty, rotSum) : { x: s.tx, y: s.ty }
      p.x += t.x
      p.y += t.y
    }
    rotSum += s.rotate || 0
  }
  const st = states.get(pid)
  if (st && (st.tx || st.ty)) {
    // 自身平移受全部祖先动态旋转影响（典型：ARM 旋转后 chuck 伸出量随之转向）
    const t = rotSum ? rotateVector(st.tx, st.ty, rotSum) : { x: st.tx, y: st.ty }
    p.x += t.x
    p.y += t.y
  }
  return p
}

// ============================================================
// 部件查找（别名由 ext 注入，不写死）
// ============================================================

export function findMotionPart(container, partId, partAliases = {}) {
  if (!container || !partId) return null
  const candidates = [partId, ...(partAliases[partId] || [])]
  for (const id of candidates) {
    const el = container.querySelector(`#${CSS.escape(id)}`)
      || container.querySelector(`[id="${id.replace(/"/g, '\\"')}"]`)
    if (el) return el
  }
  return null
}

// ============================================================
// 文字（含跟随文字）
// ============================================================

export function clearMotionTexts(container, kind) {
  if (!container) return
  const sel = kind ? `[data-motion-text="${kind}"]` : '[data-motion-text]'
  container.querySelectorAll(sel).forEach(el => el.remove())
}

export function fillSvgMultilineText(el, content, x, fontSize = 16) {
  const lines = String(content ?? '').split('\n')
  el.textContent = ''
  lines.forEach((line, i) => {
    const tspan = document.createElementNS(el.namespaceURI, 'tspan')
    tspan.setAttribute('x', String(x))
    if (i > 0) tspan.setAttribute('dy', String(fontSize * 1.2))
    tspan.textContent = line
    el.appendChild(tspan)
  })
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
  const center = getLocalCenter(targetEl) || { x: 0, y: 0 }
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

/**
 * text 动作落 DOM。x/y 直接作为 SVG user space 坐标（与模型组实现一致）。
 * targetEl 存在时为跟随文字（复制目标 transform，随目标移动）。
 * action.panel 存在时走「信息卡」模式：x/y 为卡片左上角，content 按「键:值」行渲染为屏幕卡。
 */
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

// ============================================================
// transform 应用与基础可见性
// ============================================================

function applyState(el, state, g) {
  if (!el) return
  // root 位移 → 本地 CSS translate（父链含缩放/旋转时换算；纯平移父链时 1:1）
  const lx = state.tx * g.invA + state.ty * g.invC
  const ly = state.tx * g.invB + state.ty * g.invD
  const parts = []
  // === 关键：静态 matrix 必须**前置**到 dynamic transform 之前 ===
  // 原因：CSS transform 属性从右往左链式应用，transform-origin 是元素**未变换坐标系**里的 fill-box center。
  // 用户定稿版 SVG 可能给整个机台加了全局 translate（如 translate(94.5 -11.4)），
  // 如果把这个 static matrix 拼在 dynamic rotate 右边：先应用 static matrix → origin 跟着平移 →
  // rotate 就绕 translate 后的 bbox center 转，而 deriver/JSON 里所有 pivot/角度都是按 static translate 前
  // 的 hub (444, 400) 算的 → 机械臂送错方向、门开在错误位置、晶圆飘走。
  //
  // 前置后应用顺序：rotate(本地 hub) → translate(已旋转) → static matrix(整体移到 user space)，
  // rotate 就绕 deriver 假设的 hub 旋转，与几何管线一致。
  // === CSS matrix() 参数必须用逗号分隔，否则浏览器忽略整个 transform 声明 ===
  let staticM = null
  try {
    const bv = el.transform?.baseVal
    if (bv && bv.numberOfItems > 0) staticM = bv.consolidate()?.matrix
  } catch (_) { staticM = null }
  if (staticM && !(staticM.a === 1 && staticM.b === 0 && staticM.c === 0 && staticM.d === 1 && staticM.e === 0 && staticM.f === 0)) {
    parts.push(`matrix(${staticM.a}, ${staticM.b}, ${staticM.c}, ${staticM.d}, ${staticM.e}, ${staticM.f})`)
  }
  parts.push(`translate(${lx}px, ${ly}px)`)
  if (state.rotate) parts.push(`rotate(${state.rotate}deg)`)
  if (state.scale !== 1 || (state.scaleY ?? 1) !== 1) parts.push(`scale(${state.scale}, ${state.scaleY ?? 1})`)
  el.style.transformBox = 'fill-box'
  el.style.transformOrigin = 'center'
  el.style.transform = parts.join(' ')
  syncFollowMotionTexts(el)
}

function setMotionTransition(el, duration, easing, instant) {
  if (instant || !duration) {
    el.style.transition = 'none'
    return
  }
  const ease = easingToCss(easing)
  el.style.transition = `transform ${duration}ms ${ease}, opacity ${duration}ms ${ease}`
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

/** 复位：清文字、清全部播放状态与内联样式、恢复 data-motion-base-visibility */
export function resetMotionState(container) {
  if (!container) return
  clearMotionTexts(container)
  stateCache.delete(container)
  for (const el of container.querySelectorAll('[id]')) {
    el.style.transform = ''
    el.style.transformOrigin = ''
    el.style.transformBox = ''
    el.style.transition = ''
    el.style.opacity = ''
    el.removeAttribute('visibility')
    el.style.visibility = ''
  }
  applyMotionBaseVisibility(container)
}

/** data-motion-base-visibility="hidden" 的元素在复位后保持隐藏 */
export function applyMotionBaseVisibility(container) {
  if (!container) return
  container.querySelectorAll('[data-motion-base-visibility="hidden"]').forEach((el) => {
    el.setAttribute('visibility', 'hidden')
    el.style.visibility = 'hidden'
  })
}

// ============================================================
// 动作执行（user space 纯几何）
// ============================================================

function rotatePointAround(origin, point, deg) {
  const rad = (deg * Math.PI) / 180
  const dx = point.x - origin.x
  const dy = point.y - origin.y
  return {
    x: origin.x + dx * Math.cos(rad) - dy * Math.sin(rad),
    y: origin.y + dx * Math.sin(rad) + dy * Math.cos(rad),
  }
}

// 向量旋转（y-down 坐标，正角度视觉顺时针，与 CSS/rotatePointAround 一致）
function rotateVector(x, y, deg) {
  const rad = (deg * Math.PI) / 180
  return {
    x: x * Math.cos(rad) - y * Math.sin(rad),
    y: x * Math.sin(rad) + y * Math.cos(rad),
  }
}

function toAngleNumber(value, onWarn) {
  const n = Number(value)
  if (Number.isFinite(n)) return n
  if (value !== undefined && value !== null && value !== '') {
    onWarn?.(`角度「${value}」不是数字，按 0 处理`)
  }
  return 0
}

/**
 * 单条 action 应用到 state（不触 DOM，由调用方统一 applyState）
 * @returns {{skipSelfRotate?: boolean}} rotate+follow 时返回标记，由 follow 流程处理
 */
function applyActionToState(ctx, pid, el, state, action) {
  const { geom, states, container, partAliases, params, onWarn } = ctx
  applyActionVisibility(el, action)

  switch (action.type) {
    case 'text': {
      const svg = container?.querySelector('svg')
      appendMotionText(svg, action, 'motion', params, el)
      return {}
    }
    case 'offset':
      // 两种数据约定并存，由 Motion JSON ext.offset_mode 决定（默认 relative）：
      // - relative（旧约定，PODOPENER 等）：offset 是增量，多次叠加（往返位移靠 +x/-x 抵消）
      // - absolute（OXE）：offset 是相对静态基准的绝对位置，同一部件反复写 offset(0)
      //   表示「收回原位」。若按增量算，offset(0) 什么都不改，机械臂/门只进不退，
      //   位移越累越多（臂越伸越长、门开完关不上）。
      if (ctx.offsetMode === 'absolute') {
        state.tx = Number(action.offset_x) || 0
        state.ty = -(Number(action.offset_y) || 0) // y 向上为正
      } else {
        state.tx += Number(action.offset_x) || 0
        state.ty += -(Number(action.offset_y) || 0) // y 向上为正
      }
      // 可选 scale_y：伸缩臂杆等单 action 内"平移+纵向缩放"同步补间（绝对赋值，收回时写 1）
      if (action.scale_y != null) state.scaleY = Number(action.scale_y) || 1
      return {}
    case 'rotate': {
      if (action.follow_part_id) return { skipSelfRotate: true }
      const target = toAngleNumber(action.angle, onWarn)
      // 外部 pivot：折算成绕自身中心旋转 + 平移（origin 恒为自身中心）
      if (action.pivot && Number.isFinite(Number(action.pivot.x)) && Number.isFinite(Number(action.pivot.y))
        && !(Number(action.pivot.x) === 0 && Number(action.pivot.y) === 0)) {
        const svgEl = container?.querySelector('svg')
        const vbH = svgEl?.viewBox?.baseVal?.height || 0
        const pivotRoot = { x: Number(action.pivot.x), y: vbH - Number(action.pivot.y) } // 逻辑 y 向上 → SVG y
        const c = visualCenter(ctx, pid)
        if (c) {
          const next = rotatePointAround(pivotRoot, c, target - state.rotate)
          state.tx += next.x - c.x
          state.ty += next.y - c.y
        }
      }
      state.rotate = target
      return {}
    }
    case 'scale': {
      const s = Number(action.scale_x ?? action.scale ?? 1) || 1
      state.scale = s
      // 未给 scale_y 时保持旧语义（等比缩放）
      state.scaleY = Number(action.scale_y ?? s) || 1
      return {}
    }
    case 'opacity':
      if (el) el.style.opacity = String(action.to ?? 1)
      return {}
    case 'visibility':
      applyActionVisibility(el, { visible: action.to })
      return {}
    case 'snap':
    case 'move_to': {
      const destId = String(action.to_part_id || action.to || '').trim()
      if (destId === '{home}' || destId === 'home') {
        state.tx = 0
        state.ty = 0
        return {}
      }
      const destEl = findMotionPart(container, destId, partAliases)
      if (!destEl) {
        onWarn?.(`snap 找不到目标「${destId}」，请确认 SVG 已包含该 id`)
        return {}
      }
      const src = visualCenter(ctx, pid)
      const dst = visualCenter(ctx, destId)
      if (!src || !dst) {
        onWarn?.(`snap 几何测量失败（${pid} → ${destId}）`)
        return {}
      }
      state.tx += dst.x - src.x
      state.ty += dst.y - src.y
      return {}
    }
    default:
      onWarn?.(`未知动作类型「${action.type}」，已跳过`)
      return {}
  }
}

// ============================================================
// follow 跟随旋转（user space 轨道计算）
// ============================================================

/** 找 pid 在当前 phase 之前最近一次 snap 的目标 id */
function findLatestSnapDestId(orderedRules, followerId, beforePhase) {
  let destId = ''
  for (const { rule, phase } of orderedRules) {
    if (phase >= beforePhase) break
    if (rule.target_part_id !== followerId) continue
    for (const action of (Array.isArray(rule.actions) ? rule.actions : [])) {
      if ((action?.type === 'snap' || action?.type === 'move_to') && action.to_part_id) {
        const id = String(action.to_part_id).trim()
        if (id !== '{home}' && id !== 'home') destId = id
      }
    }
  }
  return destId
}

/** 收集当前 phase 的跟随计划：显式 follow_part_id + 隐式（snap 到旋转件内部的部件） */
function collectPhaseFollowPlans(ctx, phaseItems, orderedRules, phase) {
  const { container, partAliases } = ctx
  const plans = []
  const seen = new Set()
  // 本 phase 内做自转（rotate 无 follow）的主动件及其目标角度
  const rotatingLeaders = new Map() // pid -> targetAngle
  for (const { rule } of phaseItems) {
    for (const action of (Array.isArray(rule.actions) ? rule.actions : [])) {
      if (action?.type === 'rotate' && !action.follow_part_id) {
        rotatingLeaders.set(rule.target_part_id, action.angle)
      }
    }
  }

  // 显式 follow
  for (const { rule } of phaseItems) {
    const pid = rule.target_part_id
    for (const action of (Array.isArray(rule.actions) ? rule.actions : [])) {
      if (action?.type !== 'rotate' || !action.follow_part_id) continue
      const followId = action.follow_part_id
      // follow 目标可能是旋转件的子件（如 Wafer_Chuck1 属于 ARM_1）
      let leaderId = rotatingLeaders.has(followId) ? followId : ''
      if (!leaderId) {
        const followEl = findMotionPart(container, followId, partAliases)
        for (const [lid] of rotatingLeaders) {
          const leaderEl = findMotionPart(container, lid, partAliases)
          if (leaderEl && followEl && (leaderEl === followEl || leaderEl.contains(followEl))) {
            leaderId = lid
            break
          }
        }
      }
      leaderId = leaderId || followId
      plans.push({
        followerId: pid,
        leaderId,
        leaderAngle: rotatingLeaders.get(leaderId) ?? action.angle,
        duration: action.duration || 0,
        easing: action.easing,
        explicit: true,
      })
      seen.add(pid)
    }
  }

  // 隐式 follow：本 phase 未显式跟随、但此前 snap 到了某个旋转件（或其子件）上
  for (const { rule } of phaseItems) {
    const pid = rule.target_part_id
    if (seen.has(pid)) continue
    const snapDestId = findLatestSnapDestId(orderedRules, pid, phase)
    if (!snapDestId) continue
    const snapEl = findMotionPart(container, snapDestId, partAliases)
    if (!snapEl) continue
    for (const [lid, angle] of rotatingLeaders) {
      if (!lid || lid === pid) continue
      const leaderEl = findMotionPart(container, lid, partAliases)
      if (!leaderEl) continue
      if (leaderEl !== snapEl && !leaderEl.contains(snapEl)) continue
      const firstAction = (rule.actions || [])[0] || {}
      plans.push({
        followerId: pid,
        leaderId: lid,
        leaderAngle: angle,
        duration: firstAction.duration || 0,
        easing: firstAction.easing,
        explicit: false,
      })
      seen.add(pid)
      break
    }
  }
  return plans
}

/** 计算跟随位移并写入 state（终态）。返回轨道信息供逐帧动画用 */
function computeFollowOrbit(ctx, plan, leaderStartAngles) {
  const { geom, states, onWarn } = ctx
  const followerState = ensureState(states, plan.followerId)
  const leaderCenter = visualCenter(ctx, plan.leaderId)
  const followerCenter = visualCenter(ctx, plan.followerId)
  if (!leaderCenter || !followerCenter) {
    onWarn?.(`follow 几何测量失败（${plan.followerId} 跟随 ${plan.leaderId}）`)
    return null
  }
  const leaderStart = leaderStartAngles.get(plan.leaderId) || 0
  const leaderTarget = toAngleNumber(plan.leaderAngle, onWarn)
  const delta = leaderTarget - leaderStart
  const next = rotatePointAround(leaderCenter, followerCenter, delta)
  return {
    followerId: plan.followerId,
    leaderCenter,
    startCenter: followerCenter,
    delta,
    startTx: followerState.tx,
    startTy: followerState.ty,
    endTx: followerState.tx + (next.x - followerCenter.x),
    endTy: followerState.ty + (next.y - followerCenter.y),
    duration: plan.duration,
    easing: plan.easing,
  }
}

/** 逐帧沿圆弧移动从动件（user space 纯数学，不做屏幕测量） */
function animateFollowOrbits(ctx, orbits, instant) {
  const { states } = ctx
  const instant$1 = instant || !orbits.some(o => o.duration > 0)
  if (instant$1) {
    for (const o of orbits) {
      const st = ensureState(states, o.followerId)
      st.tx = o.endTx
      st.ty = o.endTy
      const el = findMotionPart(ctx.container, o.followerId, ctx.partAliases)
      const g = ctx.geom.get(o.followerId)
      if (el && g) {
        setMotionTransition(el, 0, null, true)
        applyState(el, st, g)
      }
    }
    return Promise.resolve()
  }
  const maxDuration = Math.max(...orbits.map(o => o.duration || 0))
  const ease = easingFn(orbits.find(o => o.duration > 0)?.easing)
  return new Promise((resolve) => {
    const start = performance.now()
    let rafId = 0
    let timeoutId = 0
    const finish = () => {
      clearTimeout(timeoutId)
      resolve()
    }
    const tick = (now) => {
      const t = Math.min(1, (now - start) / maxDuration)
      const k = ease(t)
      for (const o of orbits) {
        const st = ensureState(states, o.followerId)
        const cur = rotatePointAround(o.leaderCenter, o.startCenter, o.delta * k)
        st.tx = o.startTx + (cur.x - o.startCenter.x)
        st.ty = o.startTy + (cur.y - o.startCenter.y)
        const el = findMotionPart(ctx.container, o.followerId, ctx.partAliases)
        const g = ctx.geom.get(o.followerId)
        if (el && g) {
          el.style.transition = 'none'
          applyState(el, st, g)
        }
      }
      if (t >= 1) {
        finish()
        return
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    // rAF 兜底：后台/隐藏 tab 中 rAF 不触发，await 会永久挂起并卡死后续 phase。
    // 超时后按 wall clock 直接推进到终态（tick 内 t>=1 会写终值并 finish）。
    timeoutId = setTimeout(() => {
      cancelAnimationFrame(rafId)
      tick(performance.now())
    }, maxDuration + 800)
  })
}

// ============================================================
// 主入口
// ============================================================

/**
 * 按 phase 播放已解析的 rules（模板已由 useExprEval.resolveMotionRule 替换完成）
 * @param {object} options
 * @param {Element} options.container SVG 容器（内联 SVG 的父 div）
 * @param {object[]} options.rules 已 resolveMotionRule 的规则
 * @param {object} [options.params] text 模板参数
 * @param {'animate'|'instant'} [options.mode='animate'] instant 用于历史回放 seek
 * @param {boolean} [options.reset=true] false 时保留已有变换和文字（连播/增量）
 * @param {object} [options.partAliases] ext.part_aliases 注入的部件别名
 * @param {Function} [options.onWarn] (msg) => void
 * @param {Function} [options.onClearTransforms] reset 时额外清理回调
 */
export async function playMotion({
  container,
  rules,
  params = {},
  mode = 'animate',
  reset = true,
  partAliases = {},
  offsetMode = 'relative',
  onWarn,
  onClearTransforms,
} = {}) {
  const empty = { ok: false, playedPids: new Set(), hasText: false }
  if (!container) return { ...empty, reason: 'container' }
  const svg = container.querySelector('svg')
  if (!svg) return { ...empty, reason: 'svg' }

  const matchedRules = Array.isArray(rules) ? rules : []
  if (matchedRules.length === 0) return { ...empty, reason: 'no-rules' }

  const instant = mode === 'instant'

  if (reset) {
    resetMotionState(container)
    if (typeof onClearTransforms === 'function') onClearTransforms()
    if (!instant) {
      await nextTick()
      await sleep(0)
    }
  }

  const geom = measureSvg(container, onWarn)
  if (!geom) return { ...empty, reason: 'geometry' }
  const states = getStateMap(container)

  const orderedRules = matchedRules
    .map((rule, order) => ({
      rule,
      order,
      phase: Number.isFinite(rule.phase) ? Math.max(0, Math.floor(rule.phase)) : 0,
    }))
    .sort((a, b) => a.phase - b.phase || a.order - b.order)

  const ctx = { container, geom, states, partAliases, params, onWarn, offsetMode }
  const playedPids = new Set()

  const phases = new Map()
  for (const item of orderedRules) {
    if (!phases.has(item.phase)) phases.set(item.phase, [])
    phases.get(item.phase).push(item)
  }

  for (const phase of [...phases.keys()].sort((a, b) => a - b)) {
    const phaseItems = phases.get(phase) || []
    const followPlans = collectPhaseFollowPlans(ctx, phaseItems, orderedRules, phase)
    const followPids = new Set(followPlans.map(p => p.followerId))
    // 记录本 phase 起始角度（follow delta 的基准）
    const leaderStartAngles = new Map()
    for (const [pid, st] of states.entries()) leaderStartAngles.set(pid, st.rotate || 0)

    let maxDuration = 0

    // 1) 非跟随动作：计算终态并应用（rotate+follow 的自转部分跳过）
    for (const { rule } of phaseItems) {
      const pid = rule.target_part_id
      const actions = Array.isArray(rule.actions) ? rule.actions : []
      if (actions.length === 0) continue
      const el = pid ? findMotionPart(container, pid, partAliases) : null
      if (pid && !el) {
        onWarn?.(`部件「${pid}」在 SVG 中未找到`)
        // 无目标 text 动作仍然落（target_part_id 为空的信息文字）
        for (const action of actions) {
          if (action?.type === 'text') applyActionToState(ctx, pid, null, null, action)
        }
        continue
      }
      playedPids.add(pid)
      const state = ensureState(states, pid)
      const g = geom.get(pid)
      // 纯 visibility/opacity/text 规则不改写 transform：applyState 会 consolidate()
      // 掉部件的静态 transform 属性并强设 transform-box:fill-box，带静态 rotate 的
      // 部件（如状态覆盖层）会被错误换算原点而飞出画面
      const affectsTransform = actions.some(a =>
        a && ['offset', 'rotate', 'scale', 'snap', 'move_to'].includes(a.type))
      for (const action of actions) {
        if (!action) continue
        const duration = instant ? 0 : (action.duration || 0)
        maxDuration = Math.max(maxDuration, duration)
        if (action.type === 'rotate' && (action.follow_part_id || followPids.has(pid))) continue
        if (el) setMotionTransition(el, duration, action.easing, instant)
        applyActionToState(ctx, pid, el, state, action)
      }
      if (el && g && affectsTransform) applyState(el, state, g)
    }

    // 2) 跟随：算轨道 → 终态写入 state → 逐帧或瞬时应用
    if (followPlans.length > 0) {
      const orbits = followPlans
        .map(plan => computeFollowOrbit(ctx, plan, leaderStartAngles))
        .filter(Boolean)
      // 先固定到当前位置，避免主动件已经开始转、从动件还停留在上一 phase 终态
      for (const o of orbits) {
        const el = findMotionPart(container, o.followerId, partAliases)
        const g = geom.get(o.followerId)
        const st = ensureState(states, o.followerId)
        if (el && g) {
          el.style.transition = 'none'
          applyState(el, st, g)
        }
      }
      await animateFollowOrbits(ctx, orbits, instant)
    }

    if (!instant && maxDuration > 0) await sleep(maxDuration)
  }

  const hasText = orderedRules.some(({ rule }) => (rule.actions || []).some(a => a?.type === 'text'))
  return { ok: true, playedPids, hasText }
}

export default {
  playMotion,
  sleep,
  easingToCss,
  clearMotionTexts,
  fillSvgMultilineText,
  appendMotionText,
  findMotionPart,
  resetMotionState,
  applyMotionBaseVisibility,
  invalidateMotionGeometry,
}
