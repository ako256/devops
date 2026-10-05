"""Main FastAPI microservice application entrypoint for Microchannel BTMS."""

import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import settings
from app.api.routes_telemetry import router as telemetry_router
from app.api.routes_simulation import router as simulation_router
from app.services.simulator import btms_simulator


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager: starts background simulation loop on startup."""
    # Seed initial frame
    btms_simulator.step_physics(dt=0.0)
    btms_simulator.start_background_loop()
    yield
    btms_simulator.stop_background_loop()


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Microservice backend for Microchannel Battery Thermal Management System (BTMS) monitoring",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(telemetry_router)
app.include_router(simulation_router)


@app.get("/api/health", tags=["Health"])
def health_check():
    """Health check endpoint for container probes."""
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
        "active_sim_cycle": btms_simulator.cycle_name,
        "connected_clients": len(btms_simulator.active_websockets),
    }


@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint streaming live BTMS telemetry frames directly to clients.
    """
    await btms_simulator.register_websocket(websocket)
    # Send immediate latest frame on connect
    if btms_simulator.history:
        await websocket.send_text(btms_simulator.history[-1].model_dump_json())

    try:
        while True:
            # Keep connection alive & listen for client ping or incoming commands
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        await btms_simulator.unregister_websocket(websocket)
    except Exception:
        await btms_simulator.unregister_websocket(websocket)


# Mount static frontend directory
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_index():
        return FileResponse(os.path.join(static_dir, "index.html"))
