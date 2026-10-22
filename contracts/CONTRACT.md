# Hackathon contract v1 (change only by agreement in the group chat)

## Conventions
- SI units: metres, seconds, radians, m/s. Degrees only for lat/lon (`lat_deg`, `lon_deg`).
- Frames: NED / FRD, as MAVLink. T4 converts to three.js in ONE function.
- Every frame has `t_wall_ms` (bridge receive time) and `t_boot_ms` (vehicle clock).
- Altitude names state the datum: `alt_msl_m`, `alt_rel_m`.

## WebSocket: ws://localhost:8000/ws/telemetry
Envelope: {"v":1,"type":"<topic>","seq":int,"sysid":1,"t_wall_ms":int,"t_boot_ms":int,"data":{...}}

| type | rate | data |
|---|---|---|
| telemetry.attitude | 20 Hz | roll_rad, pitch_rad, yaw_rad, rates_rps[3] |
| telemetry.position | 10 Hz | lat_deg, lon_deg, alt_msl_m, alt_rel_m, vel_ned_mps[3], heading_deg |
| vehicle.status | on change + 1 Hz | armed, mode, system_status, mission_seq |
| health.summary | 1 Hz + on change | overall, subsystems{ekf,gps,vibe,batt,link}: {state, reasons[]} |
| anomaly.event | on event | id, severity, signals[], score, explanation |
| mission.proposal | on event | proposal_id, waypoints[], metrics, violations[], explain[] |
| mission.state | on change | proposal_id, state(uploading|accepted|failed), items_sent, items_total, error |

State values: GO | CAUTION | WARNING | CRITICAL.

## Bridge REST (:8000)
- GET  /api/v1/state                       latest snapshot of every topic
- POST /api/v1/command/prepare             {action, params} -> {confirm_token, expires_s, summary}
- POST /api/v1/command/{arm|disarm|mode|takeoff|land|rtl}   {confirm_token, params}
- POST /api/v1/mission/plan                PlanRequest -> {proposal_id}  (also emits mission.proposal)
- POST /api/v1/mission/upload              {proposal_id, approved_by}  (refused if violations exist)
No raw MAVLink passthrough. Tokens are single use, 60 s TTL.

## Optimizer REST (:8100, called only by the bridge)
POST /plan  PlanRequest -> PlanResponse        GET /health

PlanRequest: {request_id, vehicle:{cruise_mps, battery_wh, reserve_pct}, start:{lat_deg,lon_deg,alt_rel_m},
  goals:[{lat_deg,lon_deg,alt_rel_m}], constraints:{geofence:[[lat,lon]], no_fly:[{polygon:[[lat,lon]],floor_m,ceil_m}],
  min_alt_m, max_alt_m, max_waypoints}, environment:{wind_from_deg, wind_mps}}
PlanResponse: {request_id, status:ok|infeasible|error, waypoints:[{seq,lat_deg,lon_deg,alt_rel_m,speed_mps}],
  metrics:{length_m,eta_s,energy_wh,min_clearance_m}, violations:[{code,message}], explain:[str], solve_ms}

## Sim REST (:8200)
POST /fault {fault: gps_loss|vibration|wind, on: bool, value?}   POST /reset   GET /status

## Ports
SITL out -> bridge UDP 14551 | bridge 8000 | optimizer 8100 | sim api 8200 | web 5173
