"""Unit tests for BTMS physics calculations and microchannel fluid dynamics."""

import pytest
from app.services.physics import (
    flow_rate_l_min_to_mass_flow_kg_s,
    calculate_heat_dissipation,
    calculate_reynolds_number,
    calculate_battery_heat_generation,
)


def test_mass_flow_conversion():
    # 1.2 L/min with density 1060 kg/m^3
    # Volumetric m^3/s = (1.2 * 1e-3) / 60 = 2e-5 m^3/s
    # Mass flow = 2e-5 * 1060 = 0.0212 kg/s
    m_dot = flow_rate_l_min_to_mass_flow_kg_s(1.2, density_kg_m3=1060.0)
    assert pytest.approx(m_dot, rel=1e-3) == 0.0212

    # Zero or negative flow
    assert flow_rate_l_min_to_mass_flow_kg_s(0.0) == 0.0
    assert flow_rate_l_min_to_mass_flow_kg_s(-1.0) == 0.0


def test_heat_dissipation_formula():
    """
    Q_dot = m_dot * Cp * (T_out - T_in)
    For 1.2 L/min, m_dot = 0.0212 kg/s
    Cp = 3500 J/(kg*K)
    Delta_T = 3.0°C (e.g. 27°C - 24°C)
    Q_dot = 0.0212 * 3500 * 3.0 = 222.6 Watts
    """
    q_dot = calculate_heat_dissipation(
        flow_rate_l_min=1.2,
        t_coolant_in=24.0,
        t_coolant_out=27.0,
        density_kg_m3=1060.0,
        specific_heat_j_kg_k=3500.0,
    )
    assert pytest.approx(q_dot, abs=1.0) == 222.6

    # When T_out <= T_in (no cooling removal)
    q_zero = calculate_heat_dissipation(
        flow_rate_l_min=1.2,
        t_coolant_in=25.0,
        t_coolant_out=25.0,
    )
    assert q_zero == 0.0


def test_reynolds_number_microchannels():
    # Standard flow rate 1.2 L/min in microchannels should be laminar (Re < 2300)
    re, regime = calculate_reynolds_number(flow_rate_l_min=1.2)
    assert re > 0
    assert regime == "Laminar"
    assert re < 2300

    # No flow
    re_zero, regime_zero = calculate_reynolds_number(flow_rate_l_min=0.0)
    assert re_zero == 0.0
    assert regime_zero == "Static (No Flow)"


def test_battery_heat_generation():
    # 50A current with 0.036 Ohm internal resistance: I^2 * R = 2500 * 0.036 = 90 W
    q_gen = calculate_battery_heat_generation(current_a=50.0, internal_resistance_ohm=0.036, t_avg_c=25.0)
    assert q_gen > 0.0
    assert pytest.approx(q_gen, rel=0.1) == 90.0
