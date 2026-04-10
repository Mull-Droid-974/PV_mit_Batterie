// State
let forecastData = null;
let historicalData = null;
let selectedDay = 0;
const charts = {};

function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

async function loadForecast() {
  try {
    const resp = await fetch("/api/forecast");
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    forecastData = data.forecast;
    historicalData = data.historical;

    renderWeatherStrip();
    renderBarChart();
    selectDay(0);

    document.getElementById("last-updated").textContent =
      `Aktualisiert: ${new Date().toLocaleTimeString("de-CH")}`;
  } catch (err) {
    console.error("Failed to load forecast:", err);
    document.getElementById("last-updated").textContent = "Fehler beim Laden";
  }
}

function renderWeatherStrip() {
  const strip = document.getElementById("weather-strip");
  const days = ["So", "Mo", "Di", "Mi", "Do", "Fr", "Sa"];
  strip.innerHTML = forecastData.map((d, i) => {
    const date = new Date(d.date + "T12:00:00");
    const label = `${days[date.getDay()]} ${date.getDate()}.${date.getMonth() + 1}.`;
    return `
      <div class="weather-day${i === 0 ? " active" : ""}" onclick="selectDay(${i})">
        <div class="wd-date">${label}</div>
        <div class="wd-pv">${d.pv_kwh.toFixed(1)} kWh</div>
        <div class="wd-meta">
          ☁ ${d.cloud_cover_pct}%<br>
          🌧 ${d.precipitation_mm.toFixed(1)} mm<br>
          🌡 ${d.temp_min}–${d.temp_max}°C
        </div>
      </div>`;
  }).join("");
}

function renderBarChart() {
  destroyChart("forecast-bar");
  const labels = forecastData.map(d => {
    const date = new Date(d.date + "T12:00:00");
    return `${date.getDate()}.${date.getMonth() + 1}.`;
  });
  const pvData = forecastData.map(d => +d.pv_kwh.toFixed(1));
  const histData = historicalData.map(h => h.pv_kwh !== null ? +h.pv_kwh.toFixed(1) : null);

  const ctx = document.getElementById("chart-forecast-bar").getContext("2d");
  charts["forecast-bar"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Prognose (kWh)",
          data: pvData,
          backgroundColor: "#3b82f6",
          borderRadius: 4,
        },
        {
          label: "Vorjahr gleiche Tage (kWh)",
          data: histData,
          backgroundColor: "rgba(107,114,128,0.3)",
          borderColor: "#6b7280",
          borderWidth: 1,
          borderDash: [4, 2],
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "top" } },
      scales: { y: { beginAtZero: true, title: { display: true, text: "kWh" } } },
    },
  });
}

function selectDay(index) {
  if (!forecastData || index < 0 || index >= forecastData.length) return;
  selectedDay = index;
  document.querySelectorAll(".weather-day").forEach((el, i) => {
    el.classList.toggle("active", i === index);
  });
  const day = forecastData[index];
  const date = new Date(day.date + "T12:00:00");
  const days = ["Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"];
  document.getElementById("detail-title").textContent =
    `Stündlicher Verlauf — ${days[date.getDay()]}, ${date.getDate()}.${date.getMonth() + 1}.${date.getFullYear()}`;
  renderHourlyDetail(day);
  renderPrecipitation(day);
}

function renderHourlyDetail(day) {
  destroyChart("hourly-detail");
  const labels = day.hourly.map(h => h.hour);
  const pvData = day.hourly.map(h => h.pv_kwh);
  const tempData = day.hourly.map(h => h.temp_c);

  const ctx = document.getElementById("chart-hourly").getContext("2d");
  charts["hourly-detail"] = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "PV-Produktion (kWh/h)",
          data: pvData,
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245,158,11,0.1)",
          fill: true,
          tension: 0.4,
          yAxisID: "y",
        },
        {
          label: "Temperatur (°C)",
          data: tempData,
          borderColor: "#ef4444",
          borderDash: [4, 2],
          fill: false,
          tension: 0.4,
          yAxisID: "y1",
          pointRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      interaction: { mode: "index" },
      plugins: { legend: { position: "top" } },
      scales: {
        y: { beginAtZero: true, title: { display: true, text: "kWh/h" } },
        y1: {
          position: "right",
          title: { display: true, text: "°C" },
          grid: { drawOnChartArea: false },
        },
      },
    },
  });
}

function renderPrecipitation(day) {
  destroyChart("precip");
  const labels = day.hourly.map(h => h.hour);
  const precipData = day.hourly.map(h => h.precipitation_mm);

  const ctx = document.getElementById("chart-precip").getContext("2d");
  charts["precip"] = new Chart(ctx, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          label: "Niederschlag (mm/h)",
          data: precipData,
          backgroundColor: "#6366f1",
          borderRadius: 2,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: { legend: { position: "top" } },
      scales: { y: { beginAtZero: true, title: { display: true, text: "mm" } } },
    },
  });
}

// Init
loadForecast();
