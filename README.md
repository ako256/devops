# Microchannel Battery Thermal Management System (BTMS) Monitoring Dashboard

A lightweight, microservice-driven monitoring dashboard for an Electric Vehicle (EV) **Microchannel Battery Thermal Management System (BTMS)**. 

The system ingests real-time operational telemetry, evaluates battery thermal health and uniformity, calculates fluid heat dissipation and microchannel hydraulic regimes, surfaces safety warnings (including thermal runaway risks), and renders an interactive 2D pack heatmap and synchronized live charts.

Entirely containerized using **Podman** and built on a high-performance **FastAPI** backend with asynchronous WebSocket telemetry broadcast.

---

## Architecture Overview

```
                           +--------------------------------------+
                           |   Telemetry Producer / Simulator     |
                           |  - WLTP / US06 / 3C Fast Charge      |
                           |  - Real-time Nodal Thermal Physics   |
                           |  - Interactive Fault Injector        |
                           +-------------------+------------------+
                                               |
                                               v
+---------------------------------------------------------------------------------+
|                       FastAPI Microservice Backend                              |
|                                                                                 |
|  [Ingestion & Broker]       [Physics & Derived Indicators]   [Safety Evaluator] |
|  - REST /api/telemetry      - Q_dot = m_dot * Cp * Delta_T   - Optimal (<35°C)  |
|  - REST /api/simulation     - Reynolds Number (Laminar)      - Warning (>40°C)  |
|  - WebSocket /ws/telemetry  - Thermal Gradient Delta_T <= 5° - Critical (>50°C) |
+----------------------------------------+----------------------------------------+
                                         | (Sub-second WebSocket Stream)
                                         v
+---------------------------------------------------------------------------------+
|                       Frontend Monitoring Dashboard UI                          |
|                                                                                 |
|  [Real-Time KPI Cards]    [2D Cell Pack Heatmap]    [Live Charts (Chart.js)]   |
|  - T_max, T_min, T_avg    - 24 Cells / 4 Modules    - Thermal Profiles          |
|  - Delta_T Uniformity     - Dynamic Thermal Gradient - Heat Dissipated vs Gen   |
|  - Coolant Q_dot & Flow   - Microchannel Flow Lines  - Current & Pack SoC       |
|  - Reynolds Re & Regime   - Interactive Cell Modal   - Control & Fault Toolbar  |
+---------------------------------------------------------------------------------+
```

---

## Physics & Engineering Equations

### 1. Coolant Heat Dissipation Rate
The rate of thermal energy extracted by the microchannel coolant flow:
$$\dot{Q}_{\text{dissipated}} = \dot{m} \cdot C_p \cdot (T_{\text{coolant\_out}} - T_{\text{coolant\_in}})$$
where:
- $\dot{m}$ is the coolant mass flow rate: $\dot{m} = \frac{\dot{V} \cdot 10^{-3}}{60} \cdot \rho$ (kg/s)
- $C_p = 3500\,\text{J/(kg}\cdot\text{K)}$ (for 50/50 Water-Ethylene Glycol)
- $\rho = 1060\,\text{kg/m}^3$

### 2. Microchannel Hydraulic Dynamics (Reynolds Number)
Flow velocity inside individual parallel microchannels:
$$v = \frac{\dot{V}}{N_{\text{channels}} \cdot A_{\text{channel}}}$$
$$Re = \frac{\rho \cdot v \cdot D_h}{\mu}$$
where $D_h = 1.2\,\text{mm}$ is the hydraulic diameter.
- **Laminar Regime**: $Re < 2300$ (typical for microchannel laminar heat transfer)
- **Transitional / Turbulent**: $Re \ge 2300$

### 3. Thermal Uniformity Factor
$$\Delta T = \max(T_{\text{cells}}) - \min(T_{\text{cells}})$$
- **Uniform (Pass)**: $\Delta T \le 5.0^\circ\text{C}$
- **Hazardous Non-Uniformity**: $\Delta T > 5.0^\circ\text{C}$

### 4. Safety State Machine
- **`OPTIMAL`**: $T_{\text{max}} \le 35^\circ\text{C}$ and $\Delta T \le 3.5^\circ\text{C}$.
- **`WARNING / HIGH LOAD`**: $40^\circ\text{C} < T_{\text{max}} \le 50^\circ\text{C}$ or $3.5^\circ\text{C} < \Delta T \le 5.0^\circ\text{C}$ $\rightarrow$ Advisory: ramp coolant flow to $\ge 2.0\,\text{L/min}$.
- **`CRITICAL / THERMAL HAZARD`**: $T_{\text{max}} > 50^\circ\text{C}$ or $\Delta T > 5.0^\circ\text{C}$ $\rightarrow$ Emergency: audible/visual alarms, contactor trip warning.

---

## Quick Start with Podman

### 1. Launch in Podman
Run the automated deployment script:
```bash
./run-podman.sh
```
Or manually:
```bash
podman build -t btms-dashboard:latest -f Containerfile .
podman run -d --name btms-monitor -p 8000:8000 btms-dashboard:latest
```

### 2. Access the Dashboard
- **Web UI**: [http://localhost:8000](http://localhost:8000)
- **Interactive REST Swagger Docs**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check Probe**: [http://localhost:8000/api/health](http://localhost:8000/api/health)

### 3. Stop Container
```bash
./stop-podman.sh
```

---

## Running Locally (without Container)

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run unit & integration tests
pytest tests/ -v

# 4. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## Interactive Dashboard Features

1. **Top KPI Gauges**: Real-time readouts of $T_{\text{max}}$, $T_{\text{avg}}$, $\Delta T$, $\dot{Q}_{\text{dissipated}}$, Reynolds number $Re$, and Pack SoC.
2. **2D Battery Pack Heatmap**:
   - 24 cells organized across 4 cooling modules.
   - Dynamic interpolated color mapping from cool cyan ($<22^\circ\text{C}$) to emerald, amber, and red ($>45^\circ\text{C}$).
   - Click any cell to inspect its thermal offset from pack mean and cooling status.
3. **Synchronized Real-Time Charts**:
   - Pack temperature curves vs. coolant inlet/outlet temperatures.
   - Rate of heat removed ($\dot{Q}_{\text{cool}}$) vs. internal heat generation ($\dot{Q}_{\text{gen}}$).
   - Discharge current ($I$) and State of Charge ($SoC$).
4. **Drive Cycle Switcher**:
   - **WLTP**: Transient urban/suburban/highway profile.
   - **US06**: High-speed, high-acceleration aggressive discharge.
   - **3C Fast Charge**: High current DC fast charging.
   - **Steady Cruise**: Steady state mild thermal dissipation.
5. **Interactive Fault Injection**:
   - `🔥 Hotspot Runaway (#14)`: Simulates cell #14 internal short circuit, demonstrating instantaneous critical alarm triggering.
   - `⚠️ Channel Blockage (Mod 2)`: Simulates microchannel plate clogging, triggering the $\Delta T > 5^\circ\text{C}$ non-uniformity warning.
   - `🛑 Pump Trip`: Simulates coolant pump loss of prime.
   - `✅ Clear Faults`: Restores nominal baseline flow.
