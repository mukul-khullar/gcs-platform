# optimizer

Owner: T3

## Trajectory validation

`src/trajopt/models.py` defines the Pydantic v2 request and response models from
the shared contract. `geo.py` projects geodetic latitude/longitude into a local
east/north ENU frame in metres, centered at the request start. `validate.py`
checks waypoint paths against the geofence, no-fly volumes, altitude limits,
and maximum waypoint count. Segments are interpolated at no more than 1 m
spacing, including altitude.

`planners/astar.py` searches a 5 m east/north grid with 8-connected movement.
Altitude is interpolated between each leg's endpoints; no-fly polygons are
blocked only between their configured floor and ceiling. The wind penalty is
added to distance as a squared headwind-to-cruise-speed ratio. Since the
request contract has no vehicle power model, `energy_wh` is an explicit 1 Wh/km
distance proxy scaled by headwind, not a physical battery-consumption estimate.
The API validates the complete final path (including the start point) before
returning it; failed validation produces `infeasible` and the validator's
violations.

Geofence boundary points are accepted as inside. No-fly polygon edges and the
floor/ceiling are treated as occupied. Altitude constraints and no-fly floors
and ceilings are interpreted as `alt_rel_m`.

## Development

From this directory:

```powershell
python -m pip install -r requirements-dev.txt
$env:PYTHONPATH = "src"
python -m pytest
```

Run the API on port 8100 with:

```powershell
$env:PYTHONPATH = "src"
python -m trajopt.api
```
