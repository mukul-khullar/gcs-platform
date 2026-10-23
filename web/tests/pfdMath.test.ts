import { describe, expect, it } from 'vitest'
import { pitchToPixels, wrapAngleRad } from '../src/instruments/pfdMath'

describe('PFD math', () => {
  it('converts pitch radians to pixels with positive pitch downward', () => {
    expect(pitchToPixels(0.1, 100)).toBe(10)
    expect(pitchToPixels(-0.1, 100)).toBe(-10)
  })

  it('normalizes angles into the signed pi range', () => {
    expect(wrapAngleRad(0)).toBe(0)
    expect(wrapAngleRad(Math.PI + 0.1)).toBeCloseTo(-Math.PI + 0.1)
    expect(wrapAngleRad(-Math.PI - 0.1)).toBeCloseTo(Math.PI - 0.1)
    expect(wrapAngleRad(4 * Math.PI)).toBe(0)
  })
})
