"""API routes for controlling the BTMS simulator and fault injection engine."""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException

from app.models.telemetry import SimulationControlRequest, FaultInjectionRequest
from app.services.simulator import btms_simulator

router = APIRouter(prefix="/api/simulation", tags=["Simulation"])


@router.get("/status")
def get_simulation_status() -> Dict[str, Any]:
    """Retrieve current simulation state and active faults."""
    return {
        "is_running": btms_simulator.is_running,
        "active_cycle": btms_simulator.cycle_name,
        "speed_multiplier": btms_simulator.speed_multiplier,
        "cycle_time_s": round(btms_simulator.cycle_time_s, 1),
        "active_faults": btms_simulator.active_faults,
        "active_websocket_clients": len(btms_simulator.active_websockets),
    }


@router.post("/control")
def control_simulation(request: SimulationControlRequest) -> Dict[str, Any]:
    """Execute control action on simulation engine."""
    cmd = request.command.lower()
    
    if cmd == "pause":
        btms_simulator.is_running = False
    elif cmd in ["start", "resume"]:
        btms_simulator.is_running = True
    elif cmd == "reset":
        btms_simulator.cycle_time_s = 0.0
        btms_simulator.cell_temperatures = [26.5 + (i * 0.1) for i in range(btms_simulator.num_cells)]
        btms_simulator.active_faults.clear()
        btms_simulator.is_running = True
    elif cmd == "set_cycle":
        if not request.cycle:
            raise HTTPException(status_code=400, detail="Missing 'cycle' parameter")
        btms_simulator.set_drive_cycle(request.cycle.upper())
    elif cmd == "set_speed":
        if request.speed_multiplier is None:
            raise HTTPException(status_code=400, detail="Missing 'speed_multiplier'")
        btms_simulator.set_speed(request.speed_multiplier)
    else:
        raise HTTPException(status_code=400, detail=f"Unknown command: '{request.command}'")

    return {
        "status": "success",
        "command": cmd,
        "simulation_state": get_simulation_status(),
    }


@router.post("/fault")
def inject_fault(request: FaultInjectionRequest) -> Dict[str, Any]:
    """Inject or clear physical BTMS thermal-hydraulic anomalies."""
    result = btms_simulator.inject_fault(request)
    return {
        "status": "success",
        "action": result,
        "active_faults": btms_simulator.active_faults,
    }
