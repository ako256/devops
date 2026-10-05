"""Real-time physics simulator and telemetry generator for Microchannel BTMS."""

import asyncio
import math
import random
from datetime import datetime, timezone
from typing import List, Dict, Optional, Set
from fastapi import WebSocket

from app.config import settings
from app.models.telemetry import (
    RawTelemetryPayload,
    ProcessedTelemetryFrame,
    FaultInjectionRequest,
)
from app.services.metrics_engine import process_telemetry


class BTMSSimulator:
    """Simulates physical battery pack thermal behavior under dynamic drive cycles."""

    def __init__(self):
        self.num_cells = settings.geometry.total_cells  # 24 cells
        self.modules = settings.geometry.module_count    # 4 modules
        self.cells_per_module = settings.geometry.cells_per_module # 6

        # Physical cell states (°C)
        self.cell_temperatures: List[float] = [26.5 + (i * 0.1) for i in range(self.num_cells)]
        # Intrinsic cell resistances with slight random manufacturing variation (~1.5 mOhm)
        self.cell_resistances: List[float] = [0.00145 + (0.0001 * (i % 5) / 5) for i in range(self.num_cells)]
        
        # Thermal mass per cell: mass * specific heat (kg * J/(kg*K)) ~ 0.9kg * 900 J/(kg*K) = 810 J/K
        self.cell_thermal_mass: float = 810.0

        # Coolant parameters
        self.t_coolant_in: float = 23.5
        self.t_coolant_out: float = 26.2
        self.coolant_flow_rate: float = settings.coolant.nominal_flow_rate_l_min # 1.2 L/min
        
        # Electrical states
        self.voltage: float = 96.0
        self.current: float = 32.0
        self.soc: float = 85.0

        # Simulation state
        self.cycle_name: str = "WLTP"
        self.cycle_time_s: float = 0.0
        self.is_running: bool = True
        self.speed_multiplier: float = 1.0
        
        # Fault injection state
        self.active_faults: Dict[str, any] = {}

        # History buffer (ring buffer)
        self.history: List[ProcessedTelemetryFrame] = []
        self.max_history: int = settings.history_retention_points

        # Connected WebSocket clients
        self.active_websockets: Set[WebSocket] = set()
        self._background_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def set_drive_cycle(self, cycle_name: str):
        """Switch active drive cycle."""
        valid_cycles = ["WLTP", "US06", "FAST_CHARGE", "STEADY_CRUISE"]
        if cycle_name in valid_cycles:
            self.cycle_name = cycle_name
            self.cycle_time_s = 0.0

    def set_speed(self, speed: float):
        """Set simulation speed multiplier."""
        self.speed_multiplier = max(0.2, min(5.0, speed))

    def inject_fault(self, request: FaultInjectionRequest):
        """Inject or clear physical BTMS faults."""
        if request.fault_type == "clear":
            self.active_faults.clear()
            self.coolant_flow_rate = settings.coolant.nominal_flow_rate_l_min
            return {"status": "cleared", "active_faults": []}

        if request.fault_type == "hotspot":
            target = request.target_cell_id if request.target_cell_id is not None else 14
            self.active_faults["hotspot"] = {
                "cell_index": target - 1,
                "severity": request.severity or 1.5,
                "description": f"Internal micro-short in Cell #{target}"
            }
        elif request.fault_type == "channel_blockage":
            module = request.target_module_id if request.target_module_id is not None else 2
            self.active_faults["blockage"] = {
                "module_index": module - 1,
                "severity": request.severity or 1.2,
                "description": f"Particulate blockage in Module #{module} microchannel plate"
            }
        elif request.fault_type == "pump_failure":
            self.active_faults["pump_failure"] = {
                "description": "Primary coolant circulation pump cavitation/loss of prime"
            }

        return {"status": "injected", "active_faults": list(self.active_faults.keys())}

    def _get_cycle_current(self, t: float) -> float:
        """Compute discharge or charge current based on cycle and elapsed time."""
        if self.cycle_name == "WLTP":
            # WLTP transient profile approximation with urban stop-and-go and highway phases
            base = 25.0 + 20.0 * math.sin(t * 0.1) + 15.0 * math.sin(t * 0.03)
            accel_spikes = 35.0 if (int(t) % 20 < 4) else 0.0
            return max(5.0, base + accel_spikes)

        elif self.cycle_name == "US06":
            # US06 aggressive high-speed, high-acceleration cycle
            base = 55.0 + 40.0 * math.sin(t * 0.15)
            hard_accel = 70.0 if (int(t) % 12 < 3) else 0.0
            regen_brake = -20.0 if (int(t) % 15 == 10) else 0.0
            return max(-20.0, base + hard_accel + regen_brake)

        elif self.cycle_name == "FAST_CHARGE":
            # High rate 3C charging (-120A) with slight taper above 80% SoC
            taper = max(0.5, (100.0 - self.soc) / 20.0) if self.soc > 80 else 1.0
            return -120.0 * taper

        elif self.cycle_name == "STEADY_CRUISE":
            return 28.0 + 3.0 * math.sin(t * 0.05)

        return 30.0

    def step_physics(self, dt: float = 1.0) -> ProcessedTelemetryFrame:
        """Advance physical simulation step by dt seconds."""
        effective_dt = dt * self.speed_multiplier
        self.cycle_time_s += effective_dt

        # Compute current and pack electrical state
        self.current = round(self._get_cycle_current(self.cycle_time_s), 1)
        
        # State of Charge integration: current (A) * dt (h) / Capacity (Ah)
        # 50 Ah nominal pack capacity
        amp_hours = (self.current * effective_dt) / 3600.0
        self.soc = max(5.0, min(100.0, self.soc - (amp_hours / 50.0) * 100.0))

        # Pack voltage calculation (nominal 96V nominal, drops with SoC and IR drop)
        ocv = 84.0 + (self.soc / 100.0) * 16.0  # 84V to 100V
        total_r = sum(self.cell_resistances)
        self.voltage = round(ocv - (self.current * total_r), 2)

        # Coolant flow handling
        if "pump_failure" in self.active_faults:
            self.coolant_flow_rate = max(0.05, self.coolant_flow_rate * 0.9)
        else:
            # Automatic pump controller: ramp flow if pack gets warm
            max_t = max(self.cell_temperatures)
            if max_t > 40.0:
                target_flow = min(2.5, settings.coolant.nominal_flow_rate_l_min * 1.8)
            else:
                target_flow = settings.coolant.nominal_flow_rate_l_min
            # Smooth flow rate adjustment
            self.coolant_flow_rate = round(self.coolant_flow_rate + (target_flow - self.coolant_flow_rate) * 0.1, 2)

        # Inflow coolant temperature
        self.t_coolant_in = round(23.0 + 1.5 * math.sin(self.cycle_time_s * 0.01), 2)

        # Heat transfer coefficient per cell contact with microchannel cold plate
        # Based on flow rate and channel design
        base_h = 28.0 * (self.coolant_flow_rate / settings.coolant.nominal_flow_rate_l_min) ** 0.8

        total_heat_removed = 0.0

        # Update each cell temperature
        for i in range(self.num_cells):
            module_id = i // self.cells_per_module

            # Heat generated by cell: I^2 * R
            r_cell = self.cell_resistances[i]
            q_gen = (self.current ** 2) * r_cell

            # Inject hotspot runaway fault if active
            if "hotspot" in self.active_faults and i == self.active_faults["hotspot"]["cell_index"]:
                severity = self.active_faults["hotspot"]["severity"]
                # Internal short adds large localized thermal generation
                q_gen += 45.0 * severity

            # Heat removed by microchannel cold plate
            cell_h = base_h
            if "blockage" in self.active_faults and module_id == self.active_faults["blockage"]["module_index"]:
                # Blockage drastically degrades cooling in this module
                cell_h *= (1.0 / (self.active_faults["blockage"]["severity"] * 2.5))

            delta_t_cell_coolant = max(0.0, self.cell_temperatures[i] - self.t_coolant_in)
            q_cool = cell_h * delta_t_cell_coolant
            total_heat_removed += q_cool

            # Heat conduction between adjacent neighbor cells
            q_cond = 0.0
            if i > 0:
                q_cond += 1.8 * (self.cell_temperatures[i - 1] - self.cell_temperatures[i])
            if i < self.num_cells - 1:
                q_cond += 1.8 * (self.cell_temperatures[i + 1] - self.cell_temperatures[i])

            # Energy balance: dT = (Q_gen - Q_cool + Q_cond) * dt / (m * Cp)
            net_q = q_gen - q_cool + q_cond
            dt_temp = (net_q * effective_dt) / self.cell_thermal_mass
            
            # Apply update with ambient dissipation
            new_temp = self.cell_temperatures[i] + dt_temp
            self.cell_temperatures[i] = round(max(20.0, new_temp), 2)

        # Compute coolant outlet temperature from total heat removed
        # Q_dot = m_dot * Cp * delta_t_coolant
        mass_flow = (self.coolant_flow_rate * 1e-3 / 60.0) * settings.coolant.density_kg_m3
        if mass_flow > 0:
            coolant_temp_rise = total_heat_removed / (mass_flow * settings.coolant.specific_heat_j_kg_k)
            self.t_coolant_out = round(self.t_coolant_in + coolant_temp_rise, 2)
        else:
            self.t_coolant_out = round(self.t_coolant_in + 12.0, 2)

        # Build raw payload and process frame
        raw_payload = RawTelemetryPayload(
            timestamp=datetime.now(timezone.utc).isoformat(),
            cell_temperatures=list(self.cell_temperatures),
            t_coolant_in=self.t_coolant_in,
            t_coolant_out=self.t_coolant_out,
            coolant_flow_rate=self.coolant_flow_rate,
            current=self.current,
            voltage=self.voltage,
            soc=round(self.soc, 1)
        )

        frame = process_telemetry(
            raw=raw_payload,
            cycle_time_s=round(self.cycle_time_s, 1),
            cycle_name=self.cycle_name
        )

        # Save to rolling history buffer
        self.history.append(frame)
        if len(self.history) > self.max_history:
            self.history.pop(0)

        return frame

    def ingest_external_telemetry(self, raw: RawTelemetryPayload) -> ProcessedTelemetryFrame:
        """Ingest external sensor data from hardware / CSV replay."""
        frame = process_telemetry(raw=raw, cycle_time_s=round(self.cycle_time_s, 1), cycle_name="EXTERNAL_INGEST")
        self.history.append(frame)
        if len(self.history) > self.max_history:
            self.history.pop(0)
        return frame

    async def register_websocket(self, websocket: WebSocket):
        """Add active WebSocket connection."""
        await websocket.accept()
        async with self._lock:
            self.active_websockets.add(websocket)

    async def unregister_websocket(self, websocket: WebSocket):
        """Remove disconnected WebSocket."""
        async with self._lock:
            self.active_websockets.discard(websocket)

    async def broadcast_frame(self, frame: ProcessedTelemetryFrame):
        """Send frame to all active WebSocket clients."""
        if not self.active_websockets:
            return

        payload_json = frame.model_dump_json()
        disconnected = set()

        async with self._lock:
            for ws in self.active_websockets:
                try:
                    await ws.send_text(payload_json)
                except Exception:
                    disconnected.add(ws)

            for ws in disconnected:
                self.active_websockets.discard(ws)

    async def run_simulation_loop(self):
        """Background continuous streaming loop."""
        while True:
            try:
                if self.is_running:
                    frame = self.step_physics(dt=1.0)
                    await self.broadcast_frame(frame)
                await asyncio.sleep(settings.telemetry_broadcast_interval_s)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[BTMS Simulator Error]: {e}")
                await asyncio.sleep(1.0)

    def start_background_loop(self):
        """Start the async simulation task."""
        if self._background_task is None or self._background_task.done():
            self._background_task = asyncio.create_task(self.run_simulation_loop())

    def stop_background_loop(self):
        """Cancel the async simulation task."""
        if self._background_task and not self._background_task.done():
            self._background_task.cancel()


# Global simulator singleton
btms_simulator = BTMSSimulator()
