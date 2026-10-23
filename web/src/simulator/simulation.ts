export type NEDPoint = {
  north_m: number
  east_m: number
  down_m: number
}

export type RoutePoint = {
  north_m: number
  east_m: number
  alt_rel_m: number
}

export type SimulationState = {
  running: boolean
  complete: boolean
  elapsed_s: number
  distance_m: number
  position_ned_m: NEDPoint
  speed_mps: number
  heading_deg: number
  attitude_rad: {
    roll_rad: number
    pitch_rad: number
    yaw_rad: number
  }
  waypoint_index: number
  battery_pct: number
  trail_ned_m: NEDPoint[]
}

export const SIMULATION_SPEED_MPS = 4
export const DEFAULT_ROUTE: readonly RoutePoint[] = [
  { north_m: 0, east_m: 0, alt_rel_m: 8 },
  { north_m: 18, east_m: 0, alt_rel_m: 8 },
  { north_m: 18, east_m: 18, alt_rel_m: 8 },
  { north_m: 0, east_m: 18, alt_rel_m: 8 },
  { north_m: 0, east_m: 0, alt_rel_m: 8 },
]

export function nedToThree({ north_m, east_m, down_m }: NEDPoint): [number, number, number] {
  return [east_m, -down_m, -north_m]
}

export function initialSimulationState(): SimulationState {
  const first = DEFAULT_ROUTE[0]
  return {
    running: false,
    complete: false,
    elapsed_s: 0,
    distance_m: 0,
    position_ned_m: {
      north_m: first.north_m,
      east_m: first.east_m,
      down_m: -first.alt_rel_m,
    },
    speed_mps: 0,
    heading_deg: 0,
    attitude_rad: { roll_rad: 0, pitch_rad: 0, yaw_rad: 0 },
    waypoint_index: 0,
    battery_pct: 100,
    trail_ned_m: [{
      north_m: first.north_m,
      east_m: first.east_m,
      down_m: -first.alt_rel_m,
    }],
  }
}

export function startSimulation(state: SimulationState): SimulationState {
  return { ...state, running: true }
}

export function pauseSimulation(state: SimulationState): SimulationState {
  return { ...state, running: false, speed_mps: 0 }
}

function routeLength(): number {
  return DEFAULT_ROUTE.slice(1).reduce((distance, point, index) => {
    const previous = DEFAULT_ROUTE[index]
    return distance + Math.hypot(point.north_m - previous.north_m, point.east_m - previous.east_m)
  }, 0)
}

export function advanceSimulation(state: SimulationState, delta_s: number): SimulationState {
  if (!state.running || delta_s <= 0 || !Number.isFinite(delta_s)) return state

  const totalDistance = routeLength()
  const distance_m = Math.min(totalDistance, state.distance_m + delta_s * SIMULATION_SPEED_MPS)
  let remaining = distance_m
  let waypoint_index = 0
  let position = DEFAULT_ROUTE[0]
  let heading_rad = 0

  for (let index = 1; index < DEFAULT_ROUTE.length; index += 1) {
    const start = DEFAULT_ROUTE[index - 1]
    const end = DEFAULT_ROUTE[index]
    const northDelta = end.north_m - start.north_m
    const eastDelta = end.east_m - start.east_m
    const legLength = Math.hypot(northDelta, eastDelta)
    if (remaining <= legLength || index === DEFAULT_ROUTE.length - 1) {
      const fraction = legLength === 0 ? 0 : Math.min(1, remaining / legLength)
      position = {
        north_m: start.north_m + northDelta * fraction,
        east_m: start.east_m + eastDelta * fraction,
        alt_rel_m: start.alt_rel_m + (end.alt_rel_m - start.alt_rel_m) * fraction,
      }
      waypoint_index = fraction >= 1 ? index : index - 1
      heading_rad = Math.atan2(eastDelta, northDelta)
      break
    }
    remaining -= legLength
  }

  const elapsed_s = distance_m / SIMULATION_SPEED_MPS
  const finished = distance_m >= totalDistance
  const heading_deg = (heading_rad * 180 / Math.PI + 360) % 360
  return {
    running: finished ? false : state.running,
    complete: finished,
    elapsed_s,
    distance_m,
    position_ned_m: {
      north_m: position.north_m,
      east_m: position.east_m,
      down_m: -position.alt_rel_m,
    },
    speed_mps: finished ? 0 : SIMULATION_SPEED_MPS,
    heading_deg,
    attitude_rad: {
      roll_rad: 0.04 * Math.sin(elapsed_s * 1.4),
      pitch_rad: 0.02 * Math.sin(elapsed_s * 0.8),
      yaw_rad: heading_rad,
    },
    waypoint_index,
    battery_pct: Math.max(0, 100 - elapsed_s * 0.03),
    trail_ned_m: [...state.trail_ned_m, {
      north_m: position.north_m,
      east_m: position.east_m,
      down_m: -position.alt_rel_m,
    }].slice(-1200),
  }
}
