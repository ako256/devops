"""Integration tests for BTMS FastAPI REST endpoints."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check_endpoint():
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "Microchannel BTMS" in data["app"]


def test_get_current_telemetry():
    response = client.get("/api/telemetry/current")
    assert response.status_code == 200
    data = response.json()
    assert "derived" in data
    assert "safety" in data
    assert "raw" in data
    assert len(data["raw"]["cell_temperatures"]) == 24


def test_get_telemetry_history():
    response = client.get("/api/telemetry/history?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_ingest_external_telemetry():
    payload = {
        "timestamp": "2026-10-05T12:00:00Z",
        "cell_temperatures": [28.0] * 24,
        "t_coolant_in": 24.0,
        "t_coolant_out": 27.5,
        "coolant_flow_rate": 1.5,
        "current": 45.0,
        "voltage": 96.0,
        "soc": 75.0
    }
    response = client.post("/api/telemetry/ingest", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["derived"]["t_max"] == 28.0
    assert data["derived"]["delta_t"] == 0.0
    assert data["safety"]["level"] == "OPTIMAL"


def test_simulation_control_cycle_and_speed():
    # Set cycle
    res_cycle = client.post("/api/simulation/control", json={"command": "set_cycle", "cycle": "US06"})
    assert res_cycle.status_code == 200

    # Set speed
    res_speed = client.post("/api/simulation/control", json={"command": "set_speed", "speed_multiplier": 2.0})
    assert res_speed.status_code == 200

    # Check status
    res_status = client.get("/api/simulation/status")
    assert res_status.status_code == 200
    assert res_status.json()["active_cycle"] == "US06"
    assert res_status.json()["speed_multiplier"] == 2.0


def test_simulation_fault_injection():
    # Inject hotspot
    res_fault = client.post("/api/simulation/fault", json={
        "fault_type": "hotspot",
        "target_cell_id": 14,
        "severity": 2.0
    })
    assert res_fault.status_code == 200
    assert "hotspot" in res_fault.json()["active_faults"]

    # Clear faults
    res_clear = client.post("/api/simulation/fault", json={"fault_type": "clear"})
    assert res_clear.status_code == 200
    assert len(res_clear.json()["active_faults"]) == 0
