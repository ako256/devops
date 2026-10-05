"""Pydantic schemas and data contracts for BTMS telemetry and control."""

from typing import List, Optional
from pydantic import BaseModel, Field


class RawTelemetryPayload(BaseModel):
    """Raw sensor readings ingested from battery pack and cooling unit."""
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    cell_temperatures: List[float] = Field(..., description="Array of module cell temperatures in °C")
    t_coolant_in: float = Field(..., description="Coolant inlet temperature in °C")
    t_coolant_out: float = Field(..., description="Coolant outlet temperature in °C")
    coolant_flow_rate: float = Field(..., description="Volumetric flow rate in L/min")
    current: float = Field(..., description="Operating discharge/charge current in Amperes")
    voltage: float = Field(..., description="Pack terminal voltage in Volts")
    soc: float = Field(..., ge=0.0, le=100.0, description="State of Charge percentage")


class DerivedMetrics(BaseModel):
    """Derived thermal-hydraulic and electrical metrics."""
    t_max: float = Field(..., description="Maximum cell temperature in °C")
    t_min: float = Field(..., description="Minimum cell temperature in °C")
    t_avg: float = Field(..., description="Pack mean cell temperature in °C")
    delta_t: float = Field(..., description="Cell-to-cell thermal gradient in °C")
    is_uniform: bool = Field(..., description="Thermal uniformity compliance (Delta_T <= 5°C)")
    heat_dissipated_w: float = Field(..., description="Rate of heat removal by coolant Q_dot in Watts")
    heat_generated_w: float = Field(..., description="Rate of internal heat generation Q_gen in Watts")
    reynolds_number: float = Field(..., description="Microchannel Reynolds number")
    flow_regime: str = Field(..., description="Flow regime: Laminar / Transitional / Turbulent")
    electrical_power_kw: float = Field(..., description="Operating electrical load in kW")
    cooling_efficiency_ratio: float = Field(..., description="Cooling effectiveness ratio (Q_dissipated / Q_gen)")


class SafetyStatus(BaseModel):
    """Safety state classification and actionable alerts."""
    level: str = Field(..., description="OPTIMAL, WARNING / HIGH LOAD, or CRITICAL / THERMAL HAZARD")
    badge_color: str = Field(..., description="emerald, amber, or rose")
    is_alarm_triggered: bool = Field(..., description="True if critical runaway or severe gradient detected")
    triggers: List[str] = Field(default_factory=list, description="List of threshold violations")
    recommended_action: str = Field(..., description="Recommended control or safety intervention")


class ProcessedTelemetryFrame(BaseModel):
    """Unified telemetry packet dispatched to dashboard clients."""
    timestamp: str
    cycle_time_s: float
    drive_cycle_name: str
    raw: RawTelemetryPayload
    derived: DerivedMetrics
    safety: SafetyStatus
    cell_count: int = 24
    module_count: int = 4


class SimulationControlRequest(BaseModel):
    """Control payload for simulation execution."""
    command: str = Field(..., description="'start', 'pause', 'resume', 'reset', 'set_speed', 'set_cycle'")
    cycle: Optional[str] = Field(None, description="'WLTP', 'US06', 'FAST_CHARGE', 'STEADY_CRUISE'")
    speed_multiplier: Optional[float] = Field(None, ge=0.1, le=10.0)


class FaultInjectionRequest(BaseModel):
    """Simulated thermal and hydraulic anomaly injection payload."""
    fault_type: str = Field(..., description="'hotspot', 'channel_blockage', 'pump_failure', 'clear'")
    target_cell_id: Optional[int] = Field(None, ge=1, le=24, description="1-indexed cell identifier")
    target_module_id: Optional[int] = Field(None, ge=1, le=4, description="1-indexed module identifier")
    severity: Optional[float] = Field(1.0, ge=0.1, le=3.0, description="Fault severity multiplier")
