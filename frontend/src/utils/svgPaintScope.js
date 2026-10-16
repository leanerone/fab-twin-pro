/**
 * SVG paint server 作用域隔离
 *
 * 同一页面可能同时挂载多份同一 SVG（模型编辑器预览 / 动画调试 / 看板 / 机台详情），
 * 导致 id 重复。fill/stroke="url(#xxx)" 永远解析到文档中第一个匹配 id，
 * 若第一个副本处于隐藏（display:none）状态，渐变/图案引用会失效（填充变白）。
 *
 * 该函数给 defs 中 paint server（渐变/图案/滤镜等）的 id 加上调用级唯一前缀，
 * 并同步改写 SVG 文本内所有 url(#id) 引用，使每份内联 SVG 自洽。
 * 元素动画 id（如 Group1_CST_TOPVIEW）不受影响。
 */

let scopeCounter = 0

// paint server / 引用型容器标签
const PAINT_TAGS = 'linearGradient|radialGradient|pattern|filter|clipPath|mask|marker'

export function scopeSvgPaintIds(svgText) {
  if (!svgText || !svgText.includes('url(#')) return svgText
  const uid = 'psc' + (++scopeCounter) + '_'

  // 1. 收集 paint server id
  const ids = new Set()
  const idRe = new RegExp('<(?:' + PAINT_TAGS + ')\\b[^>]*?\\bid="([^"]+)"', 'g')
  let m
  while ((m = idRe.exec(svgText)) !== null) ids.add(m[1])
  if (!ids.size) return svgText

  // 2. 两遍替换：先打占位，避免新前缀与原文冲突
  let out = svgText
  for (const id of ids) {
    out = out.split('url(#' + id + ')').join('url(#\0' + id + ')')
    out = out.split('id="' + id + '"').join('id="\0' + id + '"')
  }
  out = out.split('\0').join(uid)
  return out
}
