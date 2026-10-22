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

.PHONY: sim-up sim-down
sim-up:
	docker compose up --build --detach --wait --wait-timeout 60 sitl

sim-down:
	docker compose stop sitl
