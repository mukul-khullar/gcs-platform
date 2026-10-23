import { describe, expect, it } from 'vitest'
import {
  DEFAULT_ROUTE,
  advanceSimulation,
  initialSimulationState,
  nedToThree,
  startSimulation,
} from './simulation'

describe('simulation coordinate conversion', () => {
  it('maps MAVLink NED coordinates to Three.js east/up/south axes', () => {
    expect(nedToThree({ north_m: 12, east_m: 4, down_m: -8 })).toEqual([4, 8, -12])
  })
})

describe('simulated vehicle progression', () => {
  it('advances along its route and reports consistent heading and speed', () => {
    const running = startSimulation(initialSimulationState())
    const advanced = advanceSimulation(running, 1)

    expect(advanced.position_ned_m.north_m).toBeCloseTo(4)
    expect(advanced.position_ned_m.east_m).toBeCloseTo(0)
    expect(advanced.position_ned_m.down_m).toBe(-8)
    expect(advanced.speed_mps).toBeCloseTo(4)
    expect(advanced.heading_deg).toBeCloseTo(0)
    expect(advanced.elapsed_s).toBeCloseTo(1)
  })

  it('does not advance a paused simulation', () => {
    const initial = initialSimulationState()
    expect(advanceSimulation(initial, 5)).toEqual(initial)
  })

  it('stops at the end of the route', () => {
    const initial = startSimulation(initialSimulationState())
    const totalDistance = DEFAULT_ROUTE.slice(1).reduce((distance, point, index) => {
      const previous = DEFAULT_ROUTE[index]
      return distance + Math.hypot(point.north_m - previous.north_m, point.east_m - previous.east_m)
    }, 0)
    const finished = advanceSimulation(initial, totalDistance / 4 + 1)

    expect(finished.running).toBe(false)
    expect(finished.complete).toBe(true)
    expect(finished.waypoint_index).toBe(DEFAULT_ROUTE.length - 1)
    expect(finished.position_ned_m.north_m).toBeCloseTo(0)
    expect(finished.position_ned_m.east_m).toBeCloseTo(0)
    expect(finished.trail_ned_m.length).toBeGreaterThan(1)
  })
})
