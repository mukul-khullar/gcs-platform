.PHONY: generate-models test lint typecheck

generate-models:
	uv run --locked --group dev datamodel-codegen --input schemas/telemetry_frame.json --input-file-type jsonschema --output src/bridge/generated_models.py --output-model-type pydantic_v2.BaseModel --disable-timestamp --use-standard-collections --use-annotated
	uv run --locked --group dev ruff format src/bridge/generated_models.py

test:
	uv run --locked --group dev pytest

lint:
	uv run --locked --group dev ruff check src tests
	uv run --locked --group dev ruff format --check src tests

typecheck:
	uv run --locked --group dev mypy --strict src
