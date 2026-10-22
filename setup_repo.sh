# 1. Create the monorepo directory structure
mkdir -p contracts/schemas contracts/openapi contracts/fixtures \
         sim/docker sim/scenarios sim/simctl sim/corpus sim/replay \
         bridge/config bridge/ml bridge/src/bridge \
         optimizer/bench optimizer/src/trajopt \
         web/src \
         tools/mock_server

# 2. Create the root .gitignore file
cat << 'EOF' > .gitignore
# Python (Bridge & Optimizer)
__pycache__/
*.pyc
.venv/
venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/

# Node.js & TypeScript (Frontend & Mock Server)
node_modules/
.vite/
.next/

# Flight Logs, Recordings & Large Binaries (Keep out of git)
data/logs/*.mcap
*.tlog
*.bin
sim/corpus/manifest.json.lock

# IDEs and Operating System Files
.DS_Store
.vscode/
.idea/
*.swp
*.swo

# Environment Variables & Local Secrets
.env
.env.local
EOF

# 3. Create the root Makefile
cat << 'EOF' > Makefile
.PHONY: bootstrap test lint typecheck up down

bootstrap:
	@echo "Bootstrapping development environment..."
	git config core.hooksPath .githooks || true
	# Add your virtual environment & pnpm setup steps here

up:
	docker compose up -d

down:
	docker compose down

test:
	@echo "Running test suites..."

lint:
	@echo "Running linters..."

typecheck:
	@echo "Running type checkers..."
EOF

# 4. Create the docker-compose.yml placeholder
cat << 'EOF' > docker-compose.yml
version: '3.8'

services:
  sitl:
    image: python:3.11-slim
    container_name: gcs_sitl
    ports:
      - "14551:14551/udp"
      - "14552:14552/udp"
      - "8200:8200"
    command: echo "SITL placeholder container"

  bridge:
    image: python:3.11-slim
    container_name: gcs_bridge
    ports:
      - "8000:8000"
    command: echo "Bridge placeholder container"

  optimizer:
    image: python:3.11-slim
    container_name: gcs_optimizer
    ports:
      - "8100:8100"
    command: echo "Optimizer placeholder container"

  web:
    image: node:20-alpine
    container_name: gcs_web
    ports:
      - "8080:8080"
      - "5173:5173"
    command: echo "Web UI placeholder container"
EOF

# 5. Create the shared AGENTS.md primer
cat << 'EOF' > AGENTS.md
PROJECT: MAVLink GCS+ companion intelligence. Four owners: sim/ (T1), bridge/ (T2), optimizer/ (T3), web/ (T4). Edit ONLY the folder named in the task.
CONTRACTS: /contracts is the source of truth. Never edit it without being asked.
CONVENTIONS: SI units on the wire: MAVLink-native NED/FRD; names carry units (speed_mps, alt_rel_m, angle_rad); every frame has t_wall_ms and t_boot_ms.
SAFETY: The AI is advisory. No raw MAVLink passthrough. Commands are allow-listed and confirm-gated. Never weaken geofence/validator/command-gateway code without an explicit instruction.
STACK: Python 3.11, FastAPI, pydantic v2, pytest, ruff, mypy strict; TypeScript 5, React 18, Vite, three.js (r3f), MapLibre, zod, Vitest, Playwright.
WORKFLOW: Write failing tests first; run "make test lint typecheck" before saying you are done; keep diffs under 400 lines; list assumptions and open questions at the end.
VERSIONS: Pin all dependencies; do not upgrade anything unless asked.
EOF

# 6. Create the CODEOWNERS file (Update usernames/emails as needed)
cat << 'EOF' > CODEOWNERS
# Global contract requires unanimous agreement
/contracts/ @mukulkhullar

# Vertical Ownership Slices
/sim/ @mukulkhullar
/bridge/ @mukulkhullar
/optimizer/ @mukulkhullar
/web/ @mukulkhullar
EOF

# 7. Create an initial README.md
cat << 'EOF' > README.md
# MAVLink Ground Control Station & Companion Intelligence Layer

Custom MAVLink ground control station with a companion-computer intelligence layer built for ArduPilot SITL simulation[cite: 3].

## Quick Start

1. Clone the repository and bootstrap the environment:
   ```bash
   git clone <your-repo-url> gcs-platform && cd gcs-platform
   make bootstrap