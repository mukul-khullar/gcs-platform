PROJECT: MAVLink GCS+ companion intelligence. Four owners: sim/ (T1), bridge/ (T2), optimizer/ (T3), web/ (T4). Edit ONLY the folder named in the task.
CONTRACTS: /contracts is the source of truth. Never edit it without being asked.
CONVENTIONS: SI units on the wire: MAVLink-native NED/FRD; names carry units (speed_mps, alt_rel_m, angle_rad); every frame has t_wall_ms and t_boot_ms.
SAFETY: The AI is advisory. No raw MAVLink passthrough. Commands are allow-listed and confirm-gated. Never weaken geofence/validator/command-gateway code without an explicit instruction.
STACK: Python 3.11, FastAPI, pydantic v2, pytest, ruff, mypy strict; TypeScript 5, React 18, Vite, three.js (r3f), MapLibre, zod, Vitest, Playwright.
WORKFLOW: Write failing tests first; run "make test lint typecheck" before saying you are done; keep diffs under 400 lines; list assumptions and open questions at the end.
VERSIONS: Pin all dependencies; do not upgrade anything unless asked.
