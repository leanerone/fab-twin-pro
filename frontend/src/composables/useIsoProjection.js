import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'

export function useIsoProjection() {
  const ISO_ANGLE_X = 30 * Math.PI / 180
  const ISO_ANGLE_Y = 45 * Math.PI / 180

  function isoProject(x, y, z, scale = 30, offsetX = 0, offsetY = 0) {
    const cosX = Math.cos(ISO_ANGLE_X)
    const cosY = Math.cos(ISO_ANGLE_Y)
    const sinX = Math.sin(ISO_ANGLE_X)
    const sinY = Math.sin(ISO_ANGLE_Y)

    const screenX = (x - y) * cosY * scale + offsetX
    const screenY = (x + y) * sinY * sinX * scale - z * cosX * scale + offsetY

    return { x: screenX, y: screenY }
  }

  function isoProjectRect(x, y, z, width, depth, height, scale, offsetX, offsetY) {
    const p1 = isoProject(x, y, z, scale, offsetX, offsetY)
    const p2 = isoProject(x + width, y, z, scale, offsetX, offsetY)
    const p3 = isoProject(x + width, y + depth, z, scale, offsetX, offsetY)
    const p4 = isoProject(x, y + depth, z, scale, offsetX, offsetY)
    const p5 = isoProject(x, y, z + height, scale, offsetX, offsetY)
    const p6 = isoProject(x + width, y, z + height, scale, offsetX, offsetY)
    const p7 = isoProject(x + width, y + depth, z + height, scale, offsetX, offsetY)
    const p8 = isoProject(x, y + depth, z + height, scale, offsetX, offsetY)
    return { p1, p2, p3, p4, p5, p6, p7, p8 }
  }

  function drawIsoBox(ctx, x, y, z, width, depth, height, scale, offsetX, offsetY, color = '#4a5568') {
    const { p1, p2, p3, p4, p5, p6, p7, p8 } = isoProjectRect(x, y, z, width, depth, height, scale, offsetX, offsetY)

    ctx.strokeStyle = shadeColor(color, 0.7)
    ctx.lineWidth = 1

    ctx.fillStyle = shadeColor(color, 0.65)
    ctx.beginPath()
    ctx.moveTo(p1.x, p1.y)
    ctx.lineTo(p4.x, p4.y)
    ctx.lineTo(p8.x, p8.y)
    ctx.lineTo(p5.x, p5.y)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    ctx.fillStyle = shadeColor(color, 0.85)
    ctx.beginPath()
    ctx.moveTo(p2.x, p2.y)
    ctx.lineTo(p3.x, p3.y)
    ctx.lineTo(p7.x, p7.y)
    ctx.lineTo(p6.x, p6.y)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    ctx.fillStyle = shadeColor(color, 1.1)
    ctx.beginPath()
    ctx.moveTo(p5.x, p5.y)
    ctx.lineTo(p6.x, p6.y)
    ctx.lineTo(p7.x, p7.y)
    ctx.lineTo(p8.x, p8.y)
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
  }

  function drawIsoCylinder(ctx, cx, y, z, radius, height, scale, offsetX, offsetY, color = '#4a5568', segments = 24) {
    const topPoints = []
    const bottomPoints = []
    for (let i = 0; i < segments; i++) {
      const angle = (i / segments) * Math.PI * 2
      const px = cx + Math.cos(angle) * radius
      const pz = z
      const py = y + Math.sin(angle) * radius
      const top = isoProject(px, py, pz + height, scale, offsetX, offsetY)
      const bottom = isoProject(px, py, pz, scale, offsetX, offsetY)
      topPoints.push(top)
      bottomPoints.push(bottom)
    }

    ctx.strokeStyle = shadeColor(color, 0.5)
    ctx.lineWidth = 1

    ctx.fillStyle = shadeColor(color, 0.65)
    ctx.beginPath()
    for (let i = 0; i < segments; i++) {
      const idx = i
      if (i === 0) ctx.moveTo(bottomPoints[idx].x, bottomPoints[idx].y)
      else ctx.lineTo(bottomPoints[idx].x, bottomPoints[idx].y)
    }
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    ctx.fillStyle = shadeColor(color, 0.85)
    ctx.beginPath()
    for (let i = 0; i < segments; i++) {
      if (i === 0) ctx.moveTo(bottomPoints[i].x, bottomPoints[i].y)
      else ctx.lineTo(bottomPoints[i].x, bottomPoints[i].y)
    }
    for (let i = segments - 1; i >= 0; i--) {
      ctx.lineTo(topPoints[i].x, topPoints[i].y)
    }
    ctx.closePath()
    ctx.fill()
    ctx.stroke()

    ctx.fillStyle = shadeColor(color, 1.1)
    ctx.beginPath()
    for (let i = 0; i < segments; i++) {
      if (i === 0) ctx.moveTo(topPoints[i].x, topPoints[i].y)
      else ctx.lineTo(topPoints[i].x, topPoints[i].y)
    }
    ctx.closePath()
    ctx.fill()
    ctx.stroke()
  }

  function shadeColor(hex, factor) {
    const c = hex.replace('#', '')
    const r = parseInt(c.slice(0, 2), 16)
    const g = parseInt(c.slice(2, 4), 16)
    const b = parseInt(c.slice(4, 6), 16)
    const nr = Math.max(0, Math.min(255, Math.round(r * factor)))
    const ng = Math.max(0, Math.min(255, Math.round(g * factor)))
    const nb = Math.max(0, Math.min(255, Math.round(b * factor)))
    return `rgb(${nr}, ${ng}, ${nb})`
  }

  function easeInOut(t) {
    return t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2
  }

  function lerp(a, b, t) {
    return a + (b - a) * Math.max(0, Math.min(1, t))
  }

  return {
    isoProject,
    isoProjectRect,
    drawIsoBox,
    drawIsoCylinder,
    shadeColor,
    easeInOut,
    lerp,
    ISO_ANGLE_X,
    ISO_ANGLE_Y,
  }
}
