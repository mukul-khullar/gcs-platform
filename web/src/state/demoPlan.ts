import type { PlanRequest } from './operationsApi'

export const DEMO_GEOFENCE: [number, number][] = [
  [31.63, 74.868],
  [31.638, 74.868],
  [31.638, 74.877],
  [31.63, 74.877],
]

export const DEMO_NO_FLY_ZONES = [[
  [31.6355, 74.8738],
  [31.6365, 74.8738],
  [31.6365, 74.8748],
  [31.6355, 74.8748],
]] as [number, number][][]

export function buildDemoPlanRequest(start: { lat_deg: number; lon_deg: number; alt_rel_m: number }): PlanRequest {
  return {
    request_id: crypto.randomUUID(),
    vehicle: { cruise_mps: 8, battery_wh: 120, reserve_pct: 20 },
    start,
    goals: [{
      lat_deg: start.lat_deg + 0.001,
      lon_deg: start.lon_deg + 0.001,
      alt_rel_m: Math.max(start.alt_rel_m, 30),
    }],
    constraints: {
      geofence: DEMO_GEOFENCE.map(([lat, lon]) => [lat, lon]),
      no_fly: DEMO_NO_FLY_ZONES.map((polygon) => ({
        polygon: polygon.map(([lat, lon]) => [lat, lon]),
        floor_m: 0,
        ceil_m: 120,
      })),
      min_alt_m: 20,
      max_alt_m: 60,
      max_waypoints: 20,
    },
    environment: { wind_from_deg: 0, wind_mps: 0 },
  }
}
