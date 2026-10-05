"""API routes for telemetry retrieval, history, and external ingestion."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException, Query

from app.models.telemetry import RawTelemetryPayload, ProcessedTelemetryFrame
from app.services.simulator import btms_simulator

router = APIRouter(prefix="/api/telemetry", tags=["Telemetry"])


@router.get("/current", response_model=ProcessedTelemetryFrame)
def get_current_telemetry():
    """Get latest live telemetry frame with derived metrics and safety status."""
    if btms_simulator.history:
        return btms_simulator.history[-1]
    # If no history yet, advance one step
    return btms_simulator.step_physics(dt=0.0)


@router.get("/history", response_model=List[ProcessedTelemetryFrame])
def get_telemetry_history(limit: int = Query(60, ge=1, le=300)):
    """Get historical telemetry frames for dashboard charts."""
    return btms_simulator.history[-limit:]


@router.post("/ingest", response_model=ProcessedTelemetryFrame)
async def ingest_external_telemetry(payload: RawTelemetryPayload):
    """
    Ingest external sensor telemetry from real hardware, lab bench, or CSV replayer.
    Computes derived thermal-hydraulic indicators and broadcasts to dashboard.
    """
    if len(payload.cell_temperatures) == 0:
        raise HTTPException(status_code=400, detail="cell_temperatures array cannot be empty")

    frame = btms_simulator.ingest_external_telemetry(payload)
    await btms_simulator.broadcast_frame(frame)
    return frame
