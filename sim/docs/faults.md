# SITL fault injection

`simctl fault` targets local SITL at `udpin:127.0.0.1:14551` and reads every `SIM_*` parameter using
`PARAM_REQUEST_READ` before writing. Unsupported parameters report `AUTOPILOT_VERSION` (or that it
is unavailable). Activation waits five seconds for telemetry and restores originals if verification
fails; Python method handles expose `clear()` to restore pre-fault values. Install from the repository root:

```powershell
python -m pip install -e sim
simctl fault gps_loss --on
simctl fault gps_loss --off
```

Use `--connection` for another local SITL port. `--off` restores neutral
values (battery voltage resets to 12.6 V); `handle.clear()` preserves the
starting configuration.

| Fault | Parameters / activation | Expected telemetry signature within 5 s |
|---|---|---|
| `gps_loss` | `SIM_GPS_DISABLE=1` | `GPS_RAW_INT.fix_type` or `satellites_visible` decreases |
| `compass_offset(x,y,z)` | `SIM_MAG1_OFS_X/Y/Z` (legacy `SIM_MAG_OFS_X/Y/Z`) | `EKF_STATUS_REPORT.compass_variance` or flags change |
| `vibration(level)` | `SIM_ACC_RND=level` (m/s^2; default 3) | `VIBRATION.vibration_x/y/z` rises |
| `baro_drift(rate)` | `SIM_BARO_DRIFT=rate` (m/s; legacy `SIM_BAR2/3_DRIFT`) | EKF vertical variance or flags change |
| `battery_sag(v)` | `SIM_BATT_VOLTAGE=v` (V; default 9) | `SYS_STATUS.voltage_battery` falls |
| `rc_loss` | `SIM_RC_FAIL=1` | RC channel data/count or `RADIO_STATUS.rssi` changes |

Signatures are fault-specific: battery and RC use direct status telemetry, not EKF/VIBRATION. Tests use fake MAVLink; live timing needs a running SITL.
