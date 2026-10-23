import { useEffect, useRef } from 'react'
import { telemetryFrames, useTelemetryStore } from '../state/telemetryStore'
import { pitchToPixels, wrapAngleRad } from './pfdMath'

const staleAfterMs = 1000
const font = '10px "SFMono-Regular", Consolas, monospace'

function line(c: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number, color: string, width = 1) {
  c.strokeStyle = color
  c.lineWidth = width
  c.beginPath()
  c.moveTo(x1, y1)
  c.lineTo(x2, y2)
  c.stroke()
}

function text(c: CanvasRenderingContext2D, value: string, x: number, y: number, color: string, align: CanvasTextAlign = 'center') {
  c.fillStyle = color
  c.font = font
  c.textAlign = align
  c.fillText(value, x, y)
}

function draw(canvas: HTMLCanvasElement, now: number) {
  const c = canvas.getContext('2d')
  const { width, height } = canvas.getBoundingClientRect()
  if (!c || !width || !height) return
  const dpr = Math.min(window.devicePixelRatio || 1, 2)
  if (canvas.width !== Math.round(width * dpr) || canvas.height !== Math.round(height * dpr)) {
    canvas.width = Math.round(width * dpr)
    canvas.height = Math.round(height * dpr)
  }
  c.setTransform(dpr, 0, 0, dpr, 0, 0)
  c.clearRect(0, 0, width, height)
  const { attitude, attitudeReceivedAt, position, positionReceivedAt } = telemetryFrames
  const attitudeFresh = !!attitude && attitudeReceivedAt !== null && now - attitudeReceivedAt <= staleAfterMs
  const positionFresh = !!position && positionReceivedAt !== null && now - positionReceivedAt <= staleAfterMs
  const headingFresh = position ? positionFresh : attitudeFresh
  const cx = width / 2
  const cy = height * 0.49
  const radius = Math.min(width * 0.31, height * 0.32, 128)
  const pitch = attitude?.data.pitch_rad ?? 0
  const roll = attitude?.data.roll_rad ?? 0
  const heading = position?.data.heading_deg ?? ((attitude?.data.yaw_rad ?? 0) * 180) / Math.PI
  const speed = position ? Math.hypot(position.data.vel_ned_mps[0], position.data.vel_ned_mps[1]) : null
  const altitude = position?.data.alt_rel_m ?? null
  const accent = '#4f5559'
  const bright = '#303438'
  const muted = '#777d81'
  c.fillStyle = '#f4f5f5'
  c.fillRect(0, 0, width, height)
  text(c, 'ATTITUDE / FRD', 14, 18, accent, 'left')
  text(c, 'HDG °', width - 14, 18, muted, 'right')

  const tapeW = Math.min(width * 0.48, 260)
  const tapeX = cx - tapeW / 2
  c.save()
  c.globalAlpha = headingFresh ? 1 : 0.3
  c.fillStyle = '#eceeef'
  c.fillRect(tapeX, 36, tapeW, 38)
  c.strokeStyle = '#c5c9cb'
  c.strokeRect(tapeX, 36, tapeW, 38)
  c.beginPath()
  c.rect(tapeX, 36, tapeW, 38)
  c.clip()
  for (let offset = -35; offset <= 35; offset += 5) {
    const value = (Math.round(heading + offset) + 360) % 360
    const x = cx + offset * 3.2
    const major = value % 10 === 0
    line(c, x, 74, x, 74 - (major ? 9 : 5), major ? muted : '#aeb3b6')
    if (major) text(c, String(value).padStart(3, '0'), x, 51, bright)
  }
  c.restore()
  c.save()
  c.globalAlpha = headingFresh ? 1 : 0.3
  line(c, cx - 5, 36, cx, 42, accent, 2)
  line(c, cx, 42, cx + 5, 36, accent, 2)
  text(c, String(Math.round((heading + 360) % 360)).padStart(3, '0'), 14, 59, accent, 'left')
  c.restore()

  const horizonW = Math.min(width - 148, 270)
  const horizonH = Math.min(height * 0.47, 174)
  const horizonX = cx - horizonW / 2
  const horizonY = cy - horizonH / 2
  c.save()
  c.globalAlpha = attitudeFresh ? 1 : 0.15
  c.beginPath()
  c.rect(horizonX, horizonY, horizonW, horizonH)
  c.clip()
  c.translate(cx, cy)
  c.rotate(-roll)
  const pitchPx = pitchToPixels(pitch, horizonH / (Math.PI / 2))
  c.translate(0, pitchPx)
  c.fillStyle = '#d9dfe1'
  c.fillRect(-width, -height, width * 2, height)
  c.fillStyle = '#c4c9cb'
  c.fillRect(-width, 0, width * 2, height)
  line(c, -width, 0, width, 0, bright, 2)
  for (let mark = -30; mark <= 30; mark += 10) {
    if (!mark) continue
    const y = -pitchToPixels((mark * Math.PI) / 180, horizonH / (Math.PI / 2))
    const w = mark % 20 ? 26 : 42
    line(c, -w, y, -8, y, bright)
    line(c, 8, y, w, y, bright)
    text(c, String(Math.abs(mark)), -w - 10, y + 3, bright)
    text(c, String(Math.abs(mark)), w + 10, y + 3, bright)
  }
  c.restore()
  c.strokeStyle = '#aeb3b6'
  c.strokeRect(horizonX, horizonY, horizonW, horizonH)
  line(c, cx - 32, cy, cx - 9, cy, bright, 2)
  line(c, cx + 9, cy, cx + 32, cy, bright, 2)
  line(c, cx, cy - 5, cx, cy + 5, bright, 2)

  c.save()
  c.globalAlpha = attitudeFresh ? 1 : 0.3
  c.translate(cx, cy)
  for (let degree = -60; degree <= 60; degree += 30) {
    const angle = (degree * Math.PI) / 180 - Math.PI / 2
    line(c, Math.cos(angle) * (radius - 7), Math.sin(angle) * (radius - 7), Math.cos(angle) * radius, Math.sin(angle) * radius, muted)
  }
  c.rotate(-roll)
  c.fillStyle = '#d28a18'
  c.beginPath()
  c.moveTo(0, -radius + 2)
  c.lineTo(-5, -radius + 11)
  c.lineTo(5, -radius + 11)
  c.fill()
  c.restore()

  const tapeY = cy - 40
  const drawTape = (x: number, title: string, value: number | null, fresh: boolean, unit: string) => {
    c.save()
    c.globalAlpha = fresh ? 1 : 0.3
    c.fillStyle = '#eceeef'
    c.fillRect(x, tapeY, 58, 80)
    c.strokeStyle = '#c5c9cb'
    c.strokeRect(x, tapeY, 58, 80)
    text(c, title, x + 29, tapeY - 7, muted)
    text(c, value === null ? '---' : value.toFixed(1), x + 29, cy + 4, bright)
    text(c, unit, x + 29, cy + 19, accent)
    c.restore()
  }
  drawTape(12, 'SPD', speed, positionFresh, 'm/s')
  drawTape(width - 70, 'ALT REL', altitude, positionFresh, 'm')
  c.save()
  c.globalAlpha = attitudeFresh ? 1 : 0.3
  text(c, `PITCH ${pitch >= 0 ? '+' : ''}${((pitch * 180) / Math.PI).toFixed(1)}°`, 14, height - 12, muted, 'left')
  text(c, `ROLL ${((wrapAngleRad(roll) * 180) / Math.PI).toFixed(1)}°`, width - 14, height - 12, muted, 'right')
  c.restore()
  text(c, useTelemetryStore.getState().mode.toUpperCase(), cx, height - 12, accent)
}

export function Pfd() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    let active = true
    let frame = 0
    const observer = new ResizeObserver(() => draw(canvas, performance.now()))
    observer.observe(canvas)
    const render = (now: number) => {
      if (!active) return
      draw(canvas, now)
      frame = requestAnimationFrame(render)
    }
    frame = requestAnimationFrame(render)
    return () => {
      active = false
      cancelAnimationFrame(frame)
      observer.disconnect()
    }
  }, [])

  return <canvas ref={canvasRef} className="pfd-canvas" role="img" aria-label="Primary flight display: artificial horizon, heading, speed, altitude and flight mode">
    Live attitude and position instruments.
  </canvas>
}
