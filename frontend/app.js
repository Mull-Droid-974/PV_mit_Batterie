// State
let currentPeriod = "7d";
let currentData = null;
let currentSim = null;
const charts = {};

// Chart instances — destroy before recreating
function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

// Period buttons
document.getElementById("period-bar").addEventListener("click", (e) => {
  const btn = e.target.closest(".period-btn");
  if (!btn) return;
  document.querySelectorAll(".period-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  currentPeriod = btn.dataset.period;
  loadData();
});

// Preset battery buttons
document.querySelector(".preset-btns").addEventListener("click", (e) => {
  const btn = e.target.closest(".preset-btn");
  if (!btn) return;
  document.querySelectorAll(".preset-btn").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  document.getElementById("cap-input").value = btn.dataset.cap;
});

// Simulate button
document.getElementById("simulate-btn").addEventListener("click", runSimulation);

async function loadData() {
  const resp = await fetch(`/api/data?period=${currentPeriod}`);
  currentData = await resp.json();
  renderEnergyOverview(currentData);
  renderEnergyFlow(currentData);
  renderDailyProfile(currentData);
  document.getElementById("last-sync").textContent =
    `Daten bis: ${new Date().toLocaleDateString("de-CH")}`;
  if (currentSim) runSimulation();
}

function renderEnergyOverview(data) {
  const s = data.summary;
  const totalConsumption = s.self_consumption_kwh + s.grid_consumption_kwh;
  const selfConsRate = s.pv_production_kwh > 0
    ? (s.self_consumption_kwh / s.pv_production_kwh * 100).toFixed(1)
    : "—";
  const autarkyRate = totalConsumption > 0
    ? (s.self_consumption_kwh / totalConsumption * 100).toFixed(1)
    : "—";

  document.getElementById("eo-consumption").textContent = `${totalConsumption.toFixed(1)} kWh`;
  document.getElementById("eo-production").textContent = `${s.pv_production_kwh.toFixed(1)} kWh`;
  document.getElementById("eo-selfcons").textContent = selfConsRate !== "—" ? `${selfConsRate} %` : "—";
  document.getElementById("eo-autarky").textContent = autarkyRate !== "—" ? `${autarkyRate} %` : "—";
}

async function runSimulation() {
  const capacity_kwh = parseFloat(document.getElementById("cap-input").value);
  const efficiency = parseFloat(document.getElementById("eff-input").value) / 100;
  const investment_chf = parseFloat(document.getElementById("inv-input").value);

  const resp = await fetch("/api/simulate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ period: currentPeriod, capacity_kwh, efficiency, investment_chf }),
  });
  currentSim = await resp.json();
  renderStats(currentSim);
  renderAmortisation(currentSim);
}

function renderStats(sim) {
  const wo = sim.without_battery;
  const wb = sim.with_battery;
  const fmt = (v) => `${v.toFixed(1)} kWh`;
  const fmtCHF = (v) => `CHF ${v.toFixed(2)}`;

  document.getElementById("wo-grid").textContent = fmt(wo.grid_consumption_kwh);
  document.getElementById("wo-feed").textContent = fmt(wo.grid_feed_in_kwh);
  document.getElementById("wo-cost").textContent = fmtCHF(wo.grid_cost_chf);
  document.getElementById("wo-rev").textContent = fmtCHF(wo.feed_in_revenue_chf);
  document.getElementById("wo-net").textContent = fmtCHF(wo.net_cost_chf);

  document.getElementById("wb-grid").textContent = fmt(wb.grid_consumption_kwh);
  document.getElementById("wb-feed").textContent = fmt(wb.grid_feed_in_kwh);
  document.getElementById("wb-cost").textContent = fmtCHF(wb.grid_cost_chf);
  document.getElementById("wb-rev").textContent = fmtCHF(wb.feed_in_revenue_chf);
  document.getElementById("wb-net").textContent = fmtCHF(wb.net_cost_chf);

  const roi = sim.roi;
  document.getElementById("roi-annual").textContent = `CHF ${roi.annual_savings_chf.toFixed(0)}/Jahr`;
  document.getElementById("roi-payback").textContent =
    roi.payback_years === Infinity ? "∞" : `${roi.payback_years} Jahre`;
  document.getElementById("roi-period").textContent = `CHF ${roi.period_savings_chf.toFixed(2)}`;
  document.getElementById("roi-highlight").style.display = "flex";
}

function renderDailyProfile(data) {
  destroyChart("daily-profile");
  if (!data.hourly || data.hourly.length === 0) return;

  // Average by hour-of-day
  const hourBuckets = Array.from({ length: 24 }, () => ({ pv: 0, consumption: 0, count: 0 }));
  for (const r of data.hourly) {
    const h = new Date(r.timestamp).getHours();
    hourBuckets[h].pv += r.pv_production;
    hourBuckets[h].consumption += r.self_consumption + r.grid_consumption;
    hourBuckets[h].count += 1;
  }
  const labels = hourBuckets.map((_, i) => `${i}:00`);
  const pvAvg = hourBuckets.map(b => b.count ? +(b.pv / b.count).toFixed(3) : 0);
  const consAvg = hourBuckets.map(b => b.count ? +(b.consumption / b.count).toFixed(3) : 0);

  const ctx = document.getElementById("chart-daily-profile").getContext("2d");
  charts["daily-profile"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "PV-Produktion (kWh)", data: pvAvg, borderColor: "#f59e0b", backgroundColor: "rgba(245,158,11,0.1)", fill: true, tension: 0.4 },
        { label: "Verbrauch (kWh)", data: consAvg, borderColor: "#6366f1", backgroundColor: "rgba(99,102,241,0.1)", fill: true, tension: 0.4 },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "top" } } },
  });
}

function renderEnergyFlow(data) {
  destroyChart("energy-flow");
  if (!data.daily || data.daily.length === 0) return;

  const labels = data.daily.map(d => d.date);
  const ctx = document.getElementById("chart-energy-flow").getContext("2d");
  charts["energy-flow"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        { label: "Eigenverbrauch (kWh)", data: data.daily.map(d => +d.self_consumption.toFixed(2)), backgroundColor: "#f59e0b" },
        { label: "Einspeisung (kWh)", data: data.daily.map(d => +d.grid_feed_in.toFixed(2)), backgroundColor: "#10b981" },
        { label: "Netzbezug (kWh)", data: data.daily.map(d => +d.grid_consumption.toFixed(2)), backgroundColor: "#6366f1" },
      ],
    },
    options: { responsive: true, scales: { x: { stacked: true }, y: { stacked: false } }, plugins: { legend: { position: "top" } } },
  });
}

function renderAmortisation(sim) {
  destroyChart("amortisation");
  const roi = sim.roi;
  if (!roi || roi.annual_savings_chf <= 0) return;

  const years = Math.min(Math.ceil(roi.payback_years) + 5, 30);
  const labels = Array.from({ length: years + 1 }, (_, i) => `Jahr ${i}`);
  const cumSavings = labels.map((_, i) => +(i * roi.annual_savings_chf).toFixed(2));
  const investLine = labels.map(() => sim.battery.investment_chf);

  document.getElementById("chart-amort-card").style.display = "block";
  const ctx = document.getElementById("chart-amortisation").getContext("2d");
  charts["amortisation"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        { label: "Kumulierte Ersparnis (CHF)", data: cumSavings, borderColor: "#10b981", backgroundColor: "rgba(16,185,129,0.1)", fill: true, tension: 0.3 },
        { label: "Investition (CHF)", data: investLine, borderColor: "#ef4444", borderDash: [6, 3], pointRadius: 0 },
      ],
    },
    options: { responsive: true, plugins: { legend: { position: "top" } } },
  });
}

// Init
loadData();
