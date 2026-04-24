// State
let comparisonData = null;
const charts = {};
let financeVisible = false;

// ─── Helpers ────────────────────────────────────────────────────────────────

function destroyChart(id) {
  if (charts[id]) { charts[id].destroy(); delete charts[id]; }
}

function fmtDate(iso) {
  if (!iso) return '—';
  const [, m, d] = iso.split('-');
  return `${d}.${m}.`;
}

function fmtKwh(value) {
  return value !== null && value !== undefined
    ? `${value.toFixed(1)} kWh`
    : '—';
}

// ─── Period selection ────────────────────────────────────────────────────────

function selectPeriod(p) {
  document.querySelectorAll('.period-btn').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.period === p);
  });
  loadComparison(p);
}

// ─── Data loading ────────────────────────────────────────────────────────────

async function loadComparison(period) {
  try {
    const resp = await fetch(`/api/comparison?period=${period}`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    comparisonData = await resp.json();
    renderKpis(comparisonData);
    renderCharts(comparisonData);
    renderFinance(comparisonData);
    renderTotalBar(comparisonData);
    document.getElementById('last-updated').textContent =
      new Date().toLocaleTimeString('de-CH');
  } catch (err) {
    console.error('Failed to load comparison:', err);
    document.getElementById('last-updated').textContent = 'Fehler beim Laden';
  }
}

// ─── KPI cards ───────────────────────────────────────────────────────────────

function renderKpis(data) {
  const south = data.south;
  const north = data.north_estimate;

  document.getElementById('kpi-south').textContent = fmtKwh(south.total_kwh);
  document.getElementById('kpi-south-sub').textContent = `${south.kwp} kWp · ${south.modules != null ? south.modules + ' Module' : 'SSW-Seite'}`;

  document.getElementById('kpi-north').textContent = fmtKwh(north.total_kwh);
  document.getElementById('kpi-north-sub').textContent = `${north.kwp} kWp · ${north.modules != null ? north.modules + ' Module' : 'Nord-Schätzung'}`;

  document.getElementById('kpi-total').textContent = fmtKwh(data.combined_total_kwh);
  document.getElementById('kpi-total-sub').textContent =
    `+${data.gain_pct != null ? data.gain_pct.toFixed(1) : '—'}% gegenüber SSW allein`;
}

// ─── Charts ──────────────────────────────────────────────────────────────────

function renderCharts(data) {
  renderSingleChart('south', data.south.daily, '#3b82f6', 'SSW (kWh)');
  renderSingleChart('north', data.north_estimate.daily, '#f59e0b', 'Nordseite (kWh)');
}

function renderSingleChart(side, daily, color, label) {
  destroyChart(side);

  const labels = daily.map(d => fmtDate(d.date));
  const values = daily.map(d => +(d.kwh != null ? d.kwh.toFixed(2) : 0));

  const ctx = document.getElementById(`chart-${side}`).getContext('2d');
  charts[side] = new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [
        {
          label,
          data: values,
          backgroundColor: color,
          borderRadius: 4,
        },
      ],
    },
    options: {
      responsive: true,
      plugins: {
        legend: { position: 'top' },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.parsed.y.toFixed(1)} kWh`,
          },
        },
      },
      scales: {
        x: {
          ticks: { maxRotation: 45, font: { size: 11 } },
        },
        y: {
          beginAtZero: true,
          title: { display: true, text: 'kWh' },
        },
      },
    },
  });
}

// ─── Finance panel ───────────────────────────────────────────────────────────

function renderFinance(data) {
  const fin = data.financial;
  if (!fin) return;

  document.getElementById('fin-extra-kwh').textContent =
    fin.annual_extra_kwh != null ? fin.annual_extra_kwh.toFixed(0) : '—';
  document.getElementById('fin-self').textContent =
    fin.annual_self_consumption_savings_chf != null
      ? fin.annual_self_consumption_savings_chf.toFixed(0)
      : '—';
  document.getElementById('fin-feed').textContent =
    fin.annual_feed_in_revenue_chf != null
      ? fin.annual_feed_in_revenue_chf.toFixed(0)
      : '—';
  document.getElementById('fin-total').textContent =
    fin.annual_total_chf != null ? fin.annual_total_chf.toFixed(0) : '—';

  calcPayback();
}

// ─── Toggle finance panel ────────────────────────────────────────────────────

function toggleFinance() {
  financeVisible = !financeVisible;
  const panel = document.getElementById('finance-panel');
  const btn = document.getElementById('chf-toggle-btn');

  panel.classList.toggle('visible', financeVisible);
  btn.classList.toggle('active', financeVisible);
  btn.textContent = financeVisible ? 'CHF-Analyse ausblenden' : 'CHF-Analyse einblenden';
}

// ─── Live payback calculation ─────────────────────────────────────────────────

function calcPayback() {
  const investment = parseFloat(document.getElementById('investment-input').value);
  const result = document.getElementById('payback-result');

  if (!comparisonData || !comparisonData.financial) {
    result.textContent = '—';
    return;
  }

  const annualTotal = comparisonData.financial.annual_total_chf;

  if (!investment || investment <= 0 || !annualTotal || annualTotal <= 0) {
    result.textContent = 'Amortisation: —';
    return;
  }

  const years = investment / annualTotal;
  result.textContent = `Amortisation: ${years.toFixed(1)} Jahre`;
}

// ─── Total bar ────────────────────────────────────────────────────────────────

function renderTotalBar(data) {
  const periodDays = data.period_days;
  let labelText = 'Gesamt';
  if (periodDays === 1) labelText = 'Gesamt (1 Tag)';
  else if (periodDays === 7) labelText = 'Gesamt (7 Tage)';
  else if (periodDays === 30) labelText = 'Gesamt (30 Tage)';
  else if (periodDays > 0) labelText = `Gesamt (${periodDays} Tage)`;

  document.getElementById('total-bar-label').textContent = labelText;
  document.getElementById('total-bar-combined').textContent = fmtKwh(data.combined_total_kwh);
  document.getElementById('total-bar-south').textContent =
    `SSW: ${data.south.total_kwh != null ? data.south.total_kwh.toFixed(1) : '—'} kWh`;
  document.getElementById('total-bar-gain').textContent =
    data.gain_pct != null ? `+${data.gain_pct.toFixed(1)}%` : '—';
}

// ─── Init ─────────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  selectPeriod('7d');
});
