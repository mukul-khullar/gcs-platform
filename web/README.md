# Northstar flight status

The dashboard connects to `ws://localhost:8000/ws/telemetry` by default. Start the fixture-backed mock server in one terminal:

```powershell
cd tools\mock_server
pnpm start -- --loop
```

Then start the dashboard in another:

```powershell
cd web
pnpm dev
```

Set `VITE_TELEMETRY_WS_URL` to override the WebSocket URL. Telemetry frames are validated with the contract schema and kept in a mutable in-memory store; vehicle status, health and crew-warning items are held in Zustand.

The PFD renders directly from the mutable frame store and dims attitude/position values after one second without a matching frame. The MapLibre tactical map uses a local vector grid with no basemap tiles. Its default geofence and no-fly areas are illustrative demo geometry; provide mission geometry through the `TacticalMap` props for operational use. The CWS latches health and anomaly annunciators until acknowledgement; recovered health alerts remain visible until acknowledged, and severity escalations re-alarm. The systems panel displays EKF variance thresholds (0.5, 0.8, 1.0) and battery, GPS, and link health. Run `pnpm test` for CWS reducer and PFD math tests.

Flight commands use `/api/v1/command/prepare` followed by the selected command endpoint with the bridge-issued confirmation token; the UI exposes ARM, AUTO mode, and RTL only. Mission planning uses the clearly labeled demo profile and waits for proposal details on telemetry. Proposals are drawn on the map and cannot be uploaded when violations exist or more than 60 seconds have elapsed since receipt. Command, planning, upload, and CWS acknowledgement actions appear in the in-memory audit panel. The Vite development server proxies `/api` to `http://localhost:8000`; it does not replace bridge-side command validation or approval.
