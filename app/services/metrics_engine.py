"""Telemetry metrics aggregation and safety threshold classification engine."""

from datetime import datetime, timezone
from typing import List

from app.config import settings
from app.models.telemetry import (
    RawTelemetryPayload,
    DerivedMetrics,
    SafetyStatus,
    ProcessedTelemetryFrame,
)
from app.services.physics import (
    calculate_heat_dissipation,
    calculate_reynolds_number,
    calculate_battery_heat_generation,
)


def evaluate_safety_status(t_max: float, delta_t: float) -> SafetyStatus:
    """
    Evaluate multi-tier safety status based on T_max and Delta_T.
    
    Rules:
    - CRITICAL / THERMAL HAZARD:
      T_max > 50°C OR Delta_T > 5°C -> Triggers immediate alarm.
    - WARNING / HIGH LOAD:
      T_max > 40°C OR Delta_T > 3.5°C -> Requests pump flow increase.
    - OPTIMAL:
      T_max <= 40°C AND Delta_T <= 3.5°C -> Nominal operation.
    """
    triggers: List[str] = []
    crit_temp = settings.thresholds.critical_temp_c
    crit_gradient = settings.thresholds.max_allowable_gradient_c
    warn_temp = settings.thresholds.warning_temp_c
    warn_gradient = settings.thresholds.warning_gradient_c

    is_critical = False
    if t_max > crit_temp:
        is_critical = True
        triggers.append(f"T_max ({t_max:.1f}°C) exceeds critical safety limit of {crit_temp}°C (Thermal Runaway Risk)")
    if delta_t > crit_gradient:
        is_critical = True
        triggers.append(f"Thermal gradient ΔT ({delta_t:.1f}°C) exceeds pack tolerance limit of {crit_gradient}°C")

    if is_critical:
        return SafetyStatus(
            level="CRITICAL / THERMAL HAZARD",
            badge_color="rose",
            is_alarm_triggered=True,
            triggers=triggers,
            recommended_action="EMERGENCY: Immediate high-rate coolant bypass & electrical contactor trip sequence recommended."
        )

    is_warning = False
    if t_max > warn_temp:
        is_warning = True
        triggers.append(f"T_max ({t_max:.1f}°C) elevated above warning limit of {warn_temp}°C")
    if delta_t > warn_gradient:
        is_warning = True
        triggers.append(f"Thermal gradient ΔT ({delta_t:.1f}°C) elevated above nominal limit of {warn_gradient}°C")

    if is_warning:
        return SafetyStatus(
            level="WARNING / HIGH LOAD",
            badge_color="amber",
            is_alarm_triggered=False,
            triggers=triggers,
            recommended_action="ADVISORY: Request coolant pump flow rate increase (ramp to >= 2.0 L/min)."
        )

    return SafetyStatus(
        level="OPTIMAL",
        badge_color="emerald",
        is_alarm_triggered=False,
        triggers=[],
        recommended_action="NOMINAL: Thermal metrics within design envelope. Maintaining baseline microchannel flow."
    )


def process_telemetry(
    raw: RawTelemetryPayload,
    cycle_time_s: float = 0.0,
    cycle_name: str = "LIVE_INGEST"
) -> ProcessedTelemetryFrame:
    """Process raw sensor payload into full derived metrics and safety status."""
    temps = raw.cell_temperatures
    if not temps:
        temps = [25.0]

    t_max = round(max(temps), 2)
    t_min = round(min(temps), 2)
    t_avg = round(sum(temps) / len(temps), 2)
    delta_t = round(t_max - t_min, 2)
    is_uniform = delta_t <= settings.thresholds.max_allowable_gradient_c

    heat_dissipated = calculate_heat_dissipation(
        flow_rate_l_min=raw.coolant_flow_rate,
        t_coolant_in=raw.t_coolant_in,
        t_coolant_out=raw.t_coolant_out,
    )

    re_number, regime = calculate_reynolds_number(
        flow_rate_l_min=raw.coolant_flow_rate,
    )

    heat_generated = calculate_battery_heat_generation(
        current_a=raw.current,
        t_avg_c=t_avg,
    )

    power_kw = round((raw.voltage * raw.current) / 1000.0, 2)
    cop = round(heat_dissipated / max(1.0, heat_generated), 2)

    derived = DerivedMetrics(
        t_max=t_max,
        t_min=t_min,
        t_avg=t_avg,
        delta_t=delta_t,
        is_uniform=is_uniform,
        heat_dissipated_w=heat_dissipated,
        heat_generated_w=heat_generated,
        reynolds_number=re_number,
        flow_regime=regime,
        electrical_power_kw=power_kw,
        cooling_efficiency_ratio=cop,
    )

    safety = evaluate_safety_status(t_max=t_max, delta_t=delta_t)

    now_iso = raw.timestamp or datetime.now(timezone.utc).isoformat()

    return ProcessedTelemetryFrame(
        timestamp=now_iso,
        cycle_time_s=cycle_time_s,
        drive_cycle_name=cycle_name,
        raw=raw,
        derived=derived,
        safety=safety,
        cell_count=len(temps),
        module_count=settings.geometry.module_count,
    )
