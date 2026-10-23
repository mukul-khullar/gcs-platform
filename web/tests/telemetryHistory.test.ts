import { describe, expect, it } from 'vitest'
import { appendPositionSample, visiblePositionHistory } from '../src/state/telemetryHistory'

const position = (alt_rel_m: number, velocity: [number, number, number]) => ({
  v: 1 as const,
  seq: 1,
  sysid: 1,
  t_wall_ms: 1000,
  t_boot_ms: 1000,
  type: 'telemetry.position' as const,
  data: {
    lat_deg: 0,
    lon_deg: 0,
    alt_msl_m: alt_rel_m,
    alt_rel_m,
    vel_ned_mps: velocity,
    heading_deg: 0,
  },
})

describe('telemetry history', () => {
  it('records measured altitude and horizontal ground speed', () => {
    const samples = appendPositionSample([], position(32, [3, 4, 12]), 500)

    expect(samples).toEqual([{
      receivedAtMs: 500,
      alt_rel_m: 32,
      speed_mps: 5,
      lat_deg: 0,
      lon_deg: 0,
    }])
  })

  it('bounds retained samples and selects the requested time window', () => {
    const samples = [0, 1000, 2000, 3000].reduce(
      (history, time) => appendPositionSample(history, position(time, [1, 0, 0]), time, 3),
      [] as ReturnType<typeof appendPositionSample>,
    )

    expect(samples.map((sample) => sample.receivedAtMs)).toEqual([1000, 2000, 3000])
    expect(visiblePositionHistory(samples, 3000, 1).map((sample) => sample.receivedAtMs)).toEqual([2000, 3000])
  })
})
