"""FastAPI service exposing the optimizer on port 8100."""

from fastapi import FastAPI

from .models import PlanRequest, PlanResponse
from .planners.astar import plan

app = FastAPI(title="Trajectory Optimizer")


@app.post("/plan", response_model=PlanResponse)
def create_plan(request: PlanRequest) -> PlanResponse:
    """Return a validated route proposal for a contract plan request."""
    return plan(request)


@app.get("/health")
def health() -> dict[str, str]:
    """Report optimizer service readiness."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("trajopt.api:app", host="0.0.0.0", port=8100)
