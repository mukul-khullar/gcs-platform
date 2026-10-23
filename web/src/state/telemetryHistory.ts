import type { TelemetryFrame } from './protocol'

export type PositionSample = {
  receivedAtMs: number
  alt_rel_m: number
  speed_mps: number
  lat_deg: number
  lon_deg: number
}

type PositionFrame = Extract<TelemetryFrame, { type: 'telemetry.position' }>

export function appendPositionSample(
  history: PositionSample[],
  frame: PositionFrame,
  receivedAtMs: number,
  limit = 3600,
): PositionSample[] {
  const [north_mps, east_mps] = frame.data.vel_ned_mps
  history.push({
    receivedAtMs,
    alt_rel_m: frame.data.alt_rel_m,
    speed_mps: Math.hypot(north_mps, east_mps),
    lat_deg: frame.data.lat_deg,
    lon_deg: frame.data.lon_deg,
  })
  if (history.length > limit) history.splice(0, history.length - limit)
  return history
}

export function visiblePositionHistory(
  history: PositionSample[],
  nowMs: number,
  windowSeconds: number,
): PositionSample[] {
  const oldestMs = nowMs - windowSeconds * 1000
  return history.filter((sample) => sample.receivedAtMs >= oldestMs && sample.receivedAtMs <= nowMs)
}
