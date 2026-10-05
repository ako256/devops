/**
 * Microchannel BTMS Real-Time Dashboard Client
 * Handles WebSocket telemetry streaming, Chart.js updates, 2D heatmaps, and simulation control.
 */

(function () {
  'use strict';

  // State
  let ws = null;
  let isPaused = false;
  let chartTemperatures = null;
  let chartPower = null;
  let chartElectrical = null;
  let selectedCellIndex = null;
  let currentFrame = null;

  const MAX_CHART_POINTS = 60;

  // DOM Elements
  const dom = {
    connDot: document.getElementById('conn-dot'),
    connText: document.getElementById('conn-text'),
    safetyBadge: document.getElementById('safety-status-badge'),
    valSafetyStatus: document.getElementById('val-safety-status'),
    badgeDot: document.getElementById('badge-dot'),
    valCycleName: document.getElementById('val-cycle-name'),
    valCycleTime: document.getElementById('val-cycle-time'),

    // Alert Banner
    alertBanner: document.getElementById('alert-banner'),
    alertTitle: document.getElementById('alert-title'),
    alertDesc: document.getElementById('alert-desc'),
    alertRecommendation: document.getElementById('alert-recommendation'),
    btnAckAlert: document.getElementById('btn-ack-alert'),

    // KPI Cards
    cardTmax: document.getElementById('card-tmax'),
    kpiTmax: document.getElementById('kpi-tmax'),
    kpiTmaxBadge: document.getElementById('kpi-tmax-badge'),
    kpiTmin: document.getElementById('kpi-tmin'),
    kpiTavg: document.getElementById('kpi-tavg'),

    cardDeltat: document.getElementById('card-deltat'),
    kpiDeltat: document.getElementById('kpi-deltat'),
    kpiGradientBadge: document.getElementById('kpi-gradient-badge'),
    kpiGradientStatus: document.getElementById('kpi-gradient-status'),

    kpiQdot: document.getElementById('kpi-qdot'),
    kpiQgen: document.getElementById('kpi-qgen'),
    kpiCop: document.getElementById('kpi-cop'),

    kpiDeltaCoolant: document.getElementById('kpi-delta-coolant'),
    kpiTIn: document.getElementById('kpi-t-in'),
    kpiTOut: document.getElementById('kpi-t-out'),

    kpiFlowRate: document.getElementById('kpi-flow-rate'),
    kpiFlowRegime: document.getElementById('kpi-flow-regime'),
    kpiRe: document.getElementById('kpi-re'),

    kpiCurrent: document.getElementById('kpi-current'),
    kpiPower: document.getElementById('kpi-power'),
    kpiSoc: document.getElementById('kpi-soc'),

    // Flow line temps
    flowTin: document.getElementById('flow-tin'),
    flowTout: document.getElementById('flow-tout'),

    // Diagnostics
    diagUniformity: document.getElementById('diag-uniformity'),
    diagRe: document.getElementById('diag-re'),
    diagCop: document.getElementById('diag-cop'),
    diagPwr: document.getElementById('diag-pwr'),
    chkTmaxIcon: document.getElementById('chk-tmax-icon'),
    chkDeltaIcon: document.getElementById('chk-delta-icon'),
    chkFlowIcon: document.getElementById('chk-flow-icon'),

    // Grids
    gridModules: [
      document.getElementById('grid-module-1'),
      document.getElementById('grid-module-2'),
      document.getElementById('grid-module-3'),
      document.getElementById('grid-module-4'),
    ],

    // Controls
    btnToggleSim: document.getElementById('btn-toggle-sim'),
    btnResetSim: document.getElementById('btn-reset-sim'),
    btnFaultHotspot: document.getElementById('btn-fault-hotspot'),
    btnFaultBlockage: document.getElementById('btn-fault-blockage'),
    btnFaultPump: document.getElementById('btn-fault-pump'),
    btnFaultClear: document.getElementById('btn-fault-clear'),
    btnCustomInject: document.getElementById('btn-custom-inject'),

    // Modal
    cellModal: document.getElementById('cell-modal'),
    cellBackdrop: document.getElementById('cell-modal-backdrop'),
    btnCloseModal: document.getElementById('btn-close-modal'),
    modalCellId: document.getElementById('modal-cell-id'),
    modalCellTemp: document.getElementById('modal-cell-temp'),
    modalCellModule: document.getElementById('modal-cell-module'),
    modalCellOffset: document.getElementById('modal-cell-offset'),
    modalCellCooling: document.getElementById('modal-cell-cooling'),
  };

  /**
   * Interpolate color between blue (cold), green (nominal), yellow (warning), and red (hazard).
   */
  function getTemperatureColor(temp) {
    if (temp <= 22) return '#38bdf8'; // Cyan
    if (temp <= 35) {
      // 22°C to 35°C: Cyan to Emerald
      const factor = (temp - 22) / 13;
      return interpolateRgb([56, 189, 248], [16, 185, 129], factor);
    }
    if (temp <= 45) {
      // 35°C to 45°C: Emerald to Amber
      const factor = (temp - 35) / 10;
      return interpolateRgb([16, 185, 129], [245, 158, 11], factor);
    }
    // > 45°C: Amber to Rose/Red
    const factor = Math.min(1.0, (temp - 45) / 10);
    return interpolateRgb([245, 158, 11], [239, 68, 68], factor);
  }

  function interpolateRgb(rgb1, rgb2, factor) {
    const r = Math.round(rgb1[0] + factor * (rgb2[0] - rgb1[0]));
    const g = Math.round(rgb1[1] + factor * (rgb2[1] - rgb1[1]));
    const b = Math.round(rgb1[2] + factor * (rgb2[2] - rgb1[2]));
    return `rgb(${r}, ${g}, ${b})`;
  }

  /**
   * Build 2D pack heatmap DOM elements.
   */
  function initializeHeatmap() {
    for (let modIdx = 0; modIdx < 4; modIdx++) {
      const container = dom.gridModules[modIdx];
      container.innerHTML = '';
      for (let c = 0; c < 6; c++) {
        const cellId = modIdx * 6 + c + 1;
        const cellEl = document.createElement('div');
        cellEl.className = 'cell-node';
        cellEl.id = `cell-node-${cellId}`;
        cellEl.innerHTML = `
          <div class="cell-id">#${cellId < 10 ? '0' + cellId : cellId}</div>
          <div class="cell-temp" id="temp-val-${cellId}">--.-°</div>
        `;
        cellEl.addEventListener('click', () => openCellInspection(cellId - 1));
        container.appendChild(cellEl);
      }
    }
  }

  function openCellInspection(cellIndex) {
    selectedCellIndex = cellIndex;
    updateCellModal();
    dom.cellModal.style.display = 'block';
    dom.cellBackdrop.style.display = 'block';
  }

  function closeCellInspection() {
    dom.cellModal.style.display = 'none';
    dom.cellBackdrop.style.display = 'none';
    selectedCellIndex = null;
  }

  function updateCellModal() {
    if (selectedCellIndex === null || !currentFrame) return;
    const cellId = selectedCellIndex + 1;
    const temp = currentFrame.raw.cell_temperatures[selectedCellIndex];
    const modNum = Math.floor(selectedCellIndex / 6) + 1;
    const offset = (temp - currentFrame.derived.t_avg).toFixed(2);

    dom.modalCellId.textContent = `#${cellId}`;
    dom.modalCellTemp.textContent = `${temp.toFixed(1)} °C`;
    dom.modalCellModule.textContent = `Module ${modNum} (Cold Plate ${modNum})`;
    dom.modalCellOffset.textContent = `${offset > 0 ? '+' : ''}${offset} °C`;

    if (temp > 50) {
      dom.modalCellCooling.textContent = 'CRITICAL OVERHEAT';
      dom.modalCellCooling.style.color = '#ef4444';
    } else if (temp > 40) {
      dom.modalCellCooling.textContent = 'HIGH THERMAL LOAD';
      dom.modalCellCooling.style.color = '#f59e0b';
    } else {
      dom.modalCellCooling.textContent = 'Nominal Microchannel Flow';
      dom.modalCellCooling.style.color = '#34d399';
    }
  }

  /**
   * Initialize Chart.js instances.
   */
  function initializeCharts() {
    const commonOptions = {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'monospace', size: 10 } }
        },
        y: {
          grid: { color: 'rgba(255, 255, 255, 0.05)' },
          ticks: { color: '#64748b', font: { family: 'monospace', size: 10 } }
        }
      },
      plugins: {
        legend: {
          labels: { color: '#94a3b8', font: { family: 'sans-serif', size: 11 }, boxWidth: 12 }
        }
      }
    };

    // 1. Temperature Chart
    const ctxTemp = document.getElementById('chart-temperatures').getContext('2d');
    chartTemperatures = new Chart(ctxTemp, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'T_max', borderColor: '#ef4444', backgroundColor: 'rgba(239, 68, 68, 0.1)', data: [], tension: 0.2, borderWidth: 2 },
          { label: 'T_avg', borderColor: '#10b981', data: [], tension: 0.2, borderWidth: 1.5 },
          { label: 'Coolant Out', borderColor: '#f59e0b', borderDash: [4, 4], data: [], tension: 0.2, borderWidth: 1.5 },
          { label: 'Coolant In', borderColor: '#38bdf8', borderDash: [4, 4], data: [], tension: 0.2, borderWidth: 1.5 },
        ]
      },
      options: commonOptions
    });

    // 2. Power Chart
    const ctxPower = document.getElementById('chart-power').getContext('2d');
    chartPower = new Chart(ctxPower, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Heat Removed Q̇_cool (W)', borderColor: '#38bdf8', backgroundColor: 'rgba(56, 189, 248, 0.1)', fill: true, data: [], tension: 0.2, borderWidth: 2 },
          { label: 'Heat Generated Q̇_gen (W)', borderColor: '#c084fc', data: [], tension: 0.2, borderWidth: 1.5 },
        ]
      },
      options: commonOptions
    });

    // 3. Electrical Chart
    const ctxElec = document.getElementById('chart-electrical').getContext('2d');
    chartElectrical = new Chart(ctxElec, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          { label: 'Current (A)', borderColor: '#38bdf8', yAxisID: 'yCurrent', data: [], tension: 0.2, borderWidth: 2 },
          { label: 'SoC (%)', borderColor: '#34d399', yAxisID: 'ySoc', borderDash: [3, 3], data: [], tension: 0.2, borderWidth: 1.5 },
        ]
      },
      options: {
        ...commonOptions,
        scales: {
          x: commonOptions.scales.x,
          yCurrent: {
            type: 'linear',
            position: 'left',
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: { color: '#38bdf8', font: { family: 'monospace', size: 10 } }
          },
          ySoc: {
            type: 'linear',
            position: 'right',
            min: 0,
            max: 100,
            grid: { drawOnChartArea: false },
            ticks: { color: '#34d399', font: { family: 'monospace', size: 10 } }
          }
        }
      }
    });
  }

  /**
   * Update UI with new telemetry frame.
   */
  function updateDashboard(frame) {
    currentFrame = frame;

    // Header info
    dom.valCycleName.textContent = frame.drive_cycle_name;
    dom.valCycleTime.textContent = `${frame.cycle_time_s.toFixed(1)}s`;

    // Safety Status Badge
    const safety = frame.safety;
    dom.valSafetyStatus.textContent = safety.level;
    dom.safetyBadge.className = 'badge badge-pulse';

    if (safety.level === 'CRITICAL / THERMAL HAZARD') {
      dom.safetyBadge.classList.add('badge-critical');
      dom.badgeDot.style.color = '#ef4444';
      dom.cardTmax.className = 'kpi-card critical';
      dom.cardDeltat.className = 'kpi-card critical';
    } else if (safety.level === 'WARNING / HIGH LOAD') {
      dom.safetyBadge.classList.add('badge-warning');
      dom.badgeDot.style.color = '#f59e0b';
      dom.cardTmax.className = 'kpi-card warning';
      dom.cardDeltat.className = 'kpi-card warning';
    } else {
      dom.safetyBadge.classList.add('badge-optimal');
      dom.badgeDot.style.color = '#10b981';
      dom.cardTmax.className = 'kpi-card';
      dom.cardDeltat.className = 'kpi-card';
    }

    // Safety Alert Banner
    if (safety.level === 'CRITICAL / THERMAL HAZARD') {
      dom.alertBanner.className = 'critical-mode';
      dom.alertTitle.textContent = 'CRITICAL THERMAL HAZARD DETECTED!';
      dom.alertDesc.textContent = safety.triggers.join(' | ');
      dom.alertRecommendation.textContent = safety.recommended_action;
    } else if (safety.level === 'WARNING / HIGH LOAD') {
      dom.alertBanner.className = 'warning-mode';
      dom.alertTitle.textContent = 'THERMAL LOAD WARNING';
      dom.alertDesc.textContent = safety.triggers.join(' | ');
      dom.alertRecommendation.textContent = safety.recommended_action;
    } else {
      dom.alertBanner.className = '';
      dom.alertBanner.style.display = 'none';
    }

    // KPI Values
    const d = frame.derived;
    const r = frame.raw;

    dom.kpiTmax.textContent = d.t_max.toFixed(1);
    dom.kpiTmin.textContent = d.t_min.toFixed(1);
    dom.kpiTavg.textContent = d.t_avg.toFixed(1);

    if (d.t_max > 50) {
      dom.kpiTmaxBadge.textContent = 'RUNAWAY RISK';
      dom.kpiTmaxBadge.style.color = '#f87171';
      dom.kpiTmaxBadge.style.background = 'rgba(239, 68, 68, 0.2)';
    } else if (d.t_max > 40) {
      dom.kpiTmaxBadge.textContent = 'HIGH LOAD';
      dom.kpiTmaxBadge.style.color = '#fbbf24';
      dom.kpiTmaxBadge.style.background = 'rgba(245, 158, 11, 0.2)';
    } else {
      dom.kpiTmaxBadge.textContent = '< 35°C NOMINAL';
      dom.kpiTmaxBadge.style.color = '#34d399';
      dom.kpiTmaxBadge.style.background = 'rgba(16, 185, 129, 0.2)';
    }

    dom.kpiDeltat.textContent = d.delta_t.toFixed(1);
    if (d.is_uniform) {
      dom.kpiGradientBadge.textContent = 'UNIFORM';
      dom.kpiGradientBadge.style.color = '#34d399';
      dom.kpiGradientStatus.textContent = 'PASS (ΔT ≤ 5°C)';
      dom.kpiGradientStatus.style.color = '#34d399';
    } else {
      dom.kpiGradientBadge.textContent = 'NON-UNIFORM';
      dom.kpiGradientBadge.style.color = '#f87171';
      dom.kpiGradientStatus.textContent = 'FAIL (ΔT > 5°C)';
      dom.kpiGradientStatus.style.color = '#f87171';
    }

    dom.kpiQdot.textContent = Math.round(d.heat_dissipated_w);
    dom.kpiQgen.textContent = Math.round(d.heat_generated_w);
    dom.kpiCop.textContent = d.cooling_efficiency_ratio.toFixed(2);

    const deltaCoolant = (r.t_coolant_out - r.t_coolant_in).toFixed(2);
    dom.kpiDeltaCoolant.textContent = `+${deltaCoolant}`;
    dom.kpiTIn.textContent = r.t_coolant_in.toFixed(1);
    dom.kpiTOut.textContent = r.t_coolant_out.toFixed(1);

    dom.flowTin.textContent = r.t_coolant_in.toFixed(1);
    dom.flowTout.textContent = r.t_coolant_out.toFixed(1);

    dom.kpiFlowRate.textContent = r.coolant_flow_rate.toFixed(2);
    dom.kpiFlowRegime.textContent = d.flow_regime.toUpperCase();
    dom.kpiRe.textContent = Math.round(d.reynolds_number);

    dom.kpiCurrent.textContent = r.current.toFixed(1);
    dom.kpiPower.textContent = d.electrical_power_kw.toFixed(1);
    dom.kpiSoc.textContent = Math.round(r.soc);

    // Diagnostics panel
    dom.diagUniformity.textContent = d.is_uniform ? `Pass (ΔT = ${d.delta_t}°C)` : `Fail (ΔT = ${d.delta_t}°C)`;
    dom.diagUniformity.style.color = d.is_uniform ? '#34d399' : '#f87171';
    dom.diagRe.textContent = `${Math.round(d.reynolds_number)} (${d.flow_regime})`;
    dom.diagCop.textContent = `${(d.cooling_efficiency_ratio * 100).toFixed(0)}%`;
    dom.diagPwr.textContent = `${d.electrical_power_kw.toFixed(1)} kW`;

    // Checklist
    updateCheckItem(dom.chkTmaxIcon, d.t_max <= 50.0);
    updateCheckItem(dom.chkDeltaIcon, d.is_uniform);
    updateCheckItem(dom.chkFlowIcon, r.coolant_flow_rate > 0.4);

    // 2D Heatmap Update
    for (let i = 0; i < r.cell_temperatures.length; i++) {
      const cellId = i + 1;
      const cellTemp = r.cell_temperatures[i];
      const cellNode = document.getElementById(`cell-node-${cellId}`);
      const tempVal = document.getElementById(`temp-val-${cellId}`);

      if (cellNode && tempVal) {
        tempVal.textContent = `${cellTemp.toFixed(1)}°`;
        const color = getTemperatureColor(cellTemp);
        cellNode.style.borderColor = color;
        cellNode.style.backgroundColor = `${color}25`; // 15% opacity tint
        if (cellTemp > 50) {
          cellNode.style.boxShadow = `0 0 12px ${color}`;
        } else {
          cellNode.style.boxShadow = 'none';
        }
      }
    }

    if (selectedCellIndex !== null) {
      updateCellModal();
    }

    // Append to charts
    appendChartData(frame);
  }

  function updateCheckItem(iconEl, passed) {
    if (passed) {
      iconEl.className = 'check-icon pass';
      iconEl.textContent = '✓';
    } else {
      iconEl.className = 'check-icon fail';
      iconEl.textContent = '✕';
    }
  }

  function appendChartData(frame) {
    const timeLabel = `${frame.cycle_time_s.toFixed(0)}s`;

    // 1. Temperature Chart
    chartTemperatures.data.labels.push(timeLabel);
    chartTemperatures.data.datasets[0].data.push(frame.derived.t_max);
    chartTemperatures.data.datasets[1].data.push(frame.derived.t_avg);
    chartTemperatures.data.datasets[2].data.push(frame.raw.t_coolant_out);
    chartTemperatures.data.datasets[3].data.push(frame.raw.t_coolant_in);

    if (chartTemperatures.data.labels.length > MAX_CHART_POINTS) {
      chartTemperatures.data.labels.shift();
      chartTemperatures.data.datasets.forEach(ds => ds.data.shift());
    }
    chartTemperatures.update();

    // 2. Power Chart
    chartPower.data.labels.push(timeLabel);
    chartPower.data.datasets[0].data.push(frame.derived.heat_dissipated_w);
    chartPower.data.datasets[1].data.push(frame.derived.heat_generated_w);

    if (chartPower.data.labels.length > MAX_CHART_POINTS) {
      chartPower.data.labels.shift();
      chartPower.data.datasets.forEach(ds => ds.data.shift());
    }
    chartPower.update();

    // 3. Electrical Chart
    chartElectrical.data.labels.push(timeLabel);
    chartElectrical.data.datasets[0].data.push(frame.raw.current);
    chartElectrical.data.datasets[1].data.push(frame.raw.soc);

    if (chartElectrical.data.labels.length > MAX_CHART_POINTS) {
      chartElectrical.data.labels.shift();
      chartElectrical.data.datasets.forEach(ds => ds.data.shift());
    }
    chartElectrical.update();
  }

  /**
   * Preload historical telemetry data.
   */
  async function fetchHistoricalData() {
    try {
      const res = await fetch('/api/telemetry/history?limit=40');
      if (res.ok) {
        const history = await res.json();
        history.forEach(frame => {
          updateDashboard(frame);
        });
      }
    } catch (err) {
      console.warn('Could not load history:', err);
    }
  }

  /**
   * WebSocket Connection Setup with auto-reconnect.
   */
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

    dom.connText.textContent = 'Connecting...';
    dom.connDot.className = 'conn-dot';

    ws = new WebSocket(wsUrl);

    ws.onopen = function () {
      dom.connText.textContent = 'WS LIVE (1 Hz)';
      dom.connDot.className = 'conn-dot online';
    };

    ws.onmessage = function (event) {
      try {
        const data = JSON.parse(event.data);
        if (data && data.derived) {
          updateDashboard(data);
        }
      } catch (err) {
        console.error('Failed to parse frame:', err);
      }
    };

    ws.onclose = function () {
      dom.connText.textContent = 'Disconnected (Reconnecting...)';
      dom.connDot.className = 'conn-dot';
      setTimeout(connectWebSocket, 2000);
    };

    ws.onerror = function () {
      ws.close();
    };
  }

  /**
   * Simulation & Fault Control Helpers
   */
  async function sendSimControl(payload) {
    try {
      const res = await fetch('/api/simulation/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      return await res.json();
    } catch (err) {
      console.error('Control error:', err);
    }
  }

  async function sendFaultInjection(payload) {
    try {
      const res = await fetch('/api/simulation/fault', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      return await res.json();
    } catch (err) {
      console.error('Fault error:', err);
    }
  }

  /**
   * Wire Event Listeners
   */
  function setupEventListeners() {
    // Cycle buttons
    document.querySelectorAll('[data-cycle]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-cycle]').forEach(b => b.classList.remove('btn-active'));
        btn.classList.add('btn-active');
        const cycle = btn.getAttribute('data-cycle');
        sendSimControl({ command: 'set_cycle', cycle: cycle });
      });
    });

    // Speed buttons
    document.querySelectorAll('[data-speed]').forEach(btn => {
      btn.addEventListener('click', () => {
        document.querySelectorAll('[data-speed]').forEach(b => b.classList.remove('btn-active'));
        btn.classList.add('btn-active');
        const speed = parseFloat(btn.getAttribute('data-speed'));
        sendSimControl({ command: 'set_speed', speed_multiplier: speed });
      });
    });

    // Playback
    dom.btnToggleSim.addEventListener('click', () => {
      isPaused = !isPaused;
      dom.btnToggleSim.textContent = isPaused ? '▶ Resume' : '⏸ Pause';
      sendSimControl({ command: isPaused ? 'pause' : 'resume' });
    });

    dom.btnResetSim.addEventListener('click', () => {
      sendSimControl({ command: 'reset' });
    });

    // Fault Injection
    dom.btnFaultHotspot.addEventListener('click', () => {
      sendFaultInjection({
        fault_type: 'hotspot',
        target_cell_id: 14,
        severity: 2.0
      });
    });

    dom.btnFaultBlockage.addEventListener('click', () => {
      sendFaultInjection({
        fault_type: 'channel_blockage',
        target_module_id: 2,
        severity: 1.8
      });
    });

    dom.btnFaultPump.addEventListener('click', () => {
      sendFaultInjection({
        fault_type: 'pump_failure'
      });
    });

    dom.btnFaultClear.addEventListener('click', () => {
      sendFaultInjection({
        fault_type: 'clear'
      });
    });

    // Ack button
    dom.btnAckAlert.addEventListener('click', () => {
      dom.alertBanner.style.display = 'none';
    });

    // Modal close
    dom.btnCloseModal.addEventListener('click', closeCellInspection);
    dom.cellBackdrop.addEventListener('click', closeCellInspection);

    // External sensor push
    dom.btnCustomInject.addEventListener('click', async () => {
      const customPayload = {
        cell_temperatures: Array(24).fill(28.0).map((t, i) => i === 13 ? 52.4 : t + (i * 0.1)),
        t_coolant_in: 24.0,
        t_coolant_out: 29.5,
        coolant_flow_rate: 1.4,
        current: 65.0,
        voltage: 94.5,
        soc: 72.0
      };

      try {
        const res = await fetch('/api/telemetry/ingest', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(customPayload)
        });
        if (res.ok) {
          const frame = await res.json();
          updateDashboard(frame);
          alert('External sensor payload ingested successfully!');
        }
      } catch (err) {
        alert('Ingestion error: ' + err);
      }
    });
  }

  // Initialize
  document.addEventListener('DOMContentLoaded', () => {
    initializeHeatmap();
    initializeCharts();
    setupEventListeners();
    fetchHistoricalData();
    connectWebSocket();
  });
})();
