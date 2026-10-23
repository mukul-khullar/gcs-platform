import { describe, expect, it } from 'vitest'
import { toLocalNed } from '../src/simulator/liveSceneMath'

describe('live scene local coordinates', () => {
  it('projects latitude and longitude changes into local north/east metres', () => {
    const point = toLocalNed(31.635, 74.8733, 31.634, 74.8723)

    expect(point.north_m).toBeCloseTo(111.2, 0)
    expect(point.east_m).toBeCloseTo(94.8, 0)
  })
})
