"""Physics and thermal-hydraulic calculation engine for Microchannel BTMS."""

import math
from typing import Dict, Any, Tuple
from app.config import settings


def flow_rate_l_min_to_mass_flow_kg_s(flow_rate_l_min: float, density_kg_m3: float = settings.coolant.density_kg_m3) -> float:
    """Convert volumetric flow rate (L/min) to mass flow rate (kg/s)."""
    if flow_rate_l_min <= 0:
        return 0.0
    volumetric_m3_s = (flow_rate_l_min * 1e-3) / 60.0
    return volumetric_m3_s * density_kg_m3


def calculate_heat_dissipation(
    flow_rate_l_min: float,
    t_coolant_in: float,
    t_coolant_out: float,
    density_kg_m3: float = settings.coolant.density_kg_m3,
    specific_heat_j_kg_k: float = settings.coolant.specific_heat_j_kg_k
) -> float:
    """
    Calculate the rate of heat removed by coolant:
    Q_dot = m_dot * Cp * (T_coolant_out - T_coolant_in)

    Returns:
        Heat dissipation in Watts (W).
    """
    mass_flow = flow_rate_l_min_to_mass_flow_kg_s(flow_rate_l_min, density_kg_m3)
    delta_t_coolant = t_coolant_out - t_coolant_in
    q_dot = mass_flow * specific_heat_j_kg_k * delta_t_coolant
    return max(0.0, round(q_dot, 2))


def calculate_reynolds_number(
    flow_rate_l_min: float,
    density_kg_m3: float = settings.coolant.density_kg_m3,
    viscosity_pa_s: float = settings.coolant.viscosity_pa_s,
    hydraulic_diam_m: float = settings.geometry.hydraulic_diameter_m,
    total_channels: int = settings.geometry.channels_per_module * settings.geometry.module_count
) -> Tuple[float, str]:
    """
    Calculate the Reynolds number inside microchannel flow passages:
    Re = (rho * v * Dh) / mu

    Returns:
        (Re, regime_string)
    """
    if flow_rate_l_min <= 0 or total_channels <= 0:
        return 0.0, "Static (No Flow)"

    volumetric_m3_s = (flow_rate_l_min * 1e-3) / 60.0
    channel_volumetric = volumetric_m3_s / total_channels
    # Cross-sectional area of one microchannel
    area_channel = settings.geometry.channel_width_m * settings.geometry.channel_height_m
    velocity_m_s = channel_volumetric / area_channel

    re = (density_kg_m3 * velocity_m_s * hydraulic_diam_m) / viscosity_pa_s
    re_rounded = round(re, 1)

    if re_rounded < 2300:
        regime = "Laminar"
    elif re_rounded <= 4000:
        regime = "Transitional"
    else:
        regime = "Turbulent"

    return re_rounded, regime


def calculate_battery_heat_generation(
    current_a: float,
    internal_resistance_ohm: float = 0.036,  # 24 cells * ~1.5 mOhm
    t_avg_c: float = 25.0
) -> float:
    """
    Estimate internal heat generation using Joule heating + entropic contribution:
    Q_gen = I^2 * R + I * T * (dU/dT)
    """
    joule_heat = (current_a ** 2) * internal_resistance_ohm
    # Reversible heat: I * T_kelvin * entropic_coeff (-0.22 mV/K typical for Li-ion)
    t_kelvin = t_avg_c + 273.15
    entropic_coeff_v_k = -0.00022
    entropic_heat = current_a * t_kelvin * entropic_coeff_v_k

    total_gen = joule_heat + entropic_heat
    return max(0.0, round(total_gen, 2))
