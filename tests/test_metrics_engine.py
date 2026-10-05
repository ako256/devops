"""Unit tests for telemetry metrics engine and safety threshold evaluations."""

import pytest
from app.models.telemetry import RawTelemetryPayload
from app.services.metrics_engine import evaluate_safety_status, process_telemetry


def test_safety_status_optimal():
    # Nominal temperatures: T_max = 32°C, Delta_T = 2.0°C
    status = evaluate_safety_status(t_max=32.0, delta_t=2.0)
    assert status.level == "OPTIMAL"
    assert status.badge_color == "emerald"
    assert status.is_alarm_triggered is False
    assert len(status.triggers) == 0


def test_safety_status_warning_high_load():
    # Elevated temperature: T_max = 42°C (exceeds 40°C threshold)
    status = evaluate_safety_status(t_max=42.0, delta_t=2.5)
    assert status.level == "WARNING / HIGH LOAD"
    assert status.badge_color == "amber"
    assert status.is_alarm_triggered is False
    assert any("elevated above warning limit" in t for t in status.triggers)
    assert "Request coolant pump flow rate increase" in status.recommended_action


def test_safety_status_critical_temperature_overheat():
    # Critical temperature: T_max = 52.5°C (> 50°C)
    status = evaluate_safety_status(t_max=52.5, delta_t=3.0)
    assert status.level == "CRITICAL / THERMAL HAZARD"
    assert status.badge_color == "rose"
    assert status.is_alarm_triggered is True
    assert any("exceeds critical safety limit of 50.0°C" in t for t in status.triggers)
    assert "contactor trip" in status.recommended_action.lower()


def test_safety_status_critical_gradient_violation():
    # Pack non-uniformity: Delta_T = 6.2°C (> 5.0°C limit) even if T_max is only 38°C
    status = evaluate_safety_status(t_max=38.0, delta_t=6.2)
    assert status.level == "CRITICAL / THERMAL HAZARD"
    assert status.badge_color == "rose"
    assert status.is_alarm_triggered is True
    assert any("tolerance limit of 5.0°C" in t for t in status.triggers)


def test_process_telemetry_derived_indicators():
    temps = [25.0, 26.0, 27.0, 28.0, 31.0] # T_min = 25.0, T_max = 31.0, Delta_T = 6.0
    payload = RawTelemetryPayload(
        timestamp="2026-10-05T12:00:00Z",
        cell_temperatures=temps,
        t_coolant_in=23.0,
        t_coolant_out=26.5,
        coolant_flow_rate=1.5,
        current=40.0,
        voltage=95.0,
        soc=80.0
    )

    frame = process_telemetry(payload, cycle_time_s=15.0, cycle_name="TEST_CYCLE")

    assert frame.derived.t_max == 31.0
    assert frame.derived.t_min == 25.0
    assert frame.derived.delta_t == 6.0
    assert frame.derived.is_uniform is False  # > 5.0°C
    assert frame.derived.electrical_power_kw == 3.8 # (95V * 40A) / 1000 = 3.8 kW
    assert frame.derived.heat_dissipated_w > 0
    assert frame.safety.level == "CRITICAL / THERMAL HAZARD"
