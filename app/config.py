"""Configuration parameters and physical constants for the Microchannel BTMS."""

from pydantic import BaseModel


class CoolantProperties(BaseModel):
    """Thermophysical properties for 50/50 Water-Ethylene Glycol mixture."""
    density_kg_m3: float = 1060.0             # kg/m^3
    specific_heat_j_kg_k: float = 3500.0      # J/(kg*K)
    viscosity_pa_s: float = 0.0025            # Pa*s at ~30-40°C
    nominal_flow_rate_l_min: float = 1.2      # Nominal pump flow in L/min


class MicrochannelGeometry(BaseModel):
    """Geometric specifications of microchannel cooling plates."""
    hydraulic_diameter_m: float = 0.0012      # 1.2 mm hydraulic diameter
    channel_width_m: float = 0.0010           # 1.0 mm
    channel_height_m: float = 0.0015          # 1.5 mm
    channels_per_module: int = 16             # 16 microchannels per module plate
    module_count: int = 4                     # 4 cooling modules
    cells_per_module: int = 6                 # 6 cells per module (24 cells total)
    total_cells: int = 24


class ThermalSafetyThresholds(BaseModel):
    """Safety classification thresholds for battery thermal management."""
    optimal_max_temp_c: float = 35.0          # Below 35°C is optimal
    warning_temp_c: float = 40.0              # Above 40°C warrants flow rate increase
    critical_temp_c: float = 50.0             # Above 50°C indicates runaway hazard
    max_allowable_gradient_c: float = 5.0     # Delta T <= 5°C required for cell longevity
    warning_gradient_c: float = 3.5           # Delta T > 3.5°C triggers non-uniformity warning


class SystemSettings(BaseModel):
    """Global microservice configuration."""
    app_name: str = "Microchannel BTMS Monitor"
    app_version: str = "1.0.0"
    telemetry_broadcast_interval_s: float = 1.0
    history_retention_points: int = 300       # Keep last 300 data points in memory
    coolant: CoolantProperties = CoolantProperties()
    geometry: MicrochannelGeometry = MicrochannelGeometry()
    thresholds: ThermalSafetyThresholds = ThermalSafetyThresholds()


settings = SystemSettings()
