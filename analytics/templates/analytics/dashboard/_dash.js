// Shared helpers for every dashboard page. Included inline by base.html (there is no static-file serving).
const QUESTIONS = JSON.parse(document.getElementById('questions-data').textContent);

const nf = new Intl.NumberFormat('en-US', { maximumFractionDigits: 2 });
const nf1 = new Intl.NumberFormat('en-US', { maximumFractionDigits: 1 });
const fmtPct = v => nf1.format(v) + '%';
const ratioPct = (a, b) => (b ? a / b * 100 : 0);
const plural = (n, word) => `${nf.format(n)} ${word}${n === 1 ? '' : 's'}`;
const total = arr => arr.reduce((a, b) => a + b, 0);
const argMax = arr => arr.reduce((best, v, i) => (v > arr[best] ? i : best), 0);

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const FULL_DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];
const HOURS = Array.from({ length: 24 }, (_, h) => h);
const hourLabel = h => String(h).padStart(2, '0') + ':00';
const prettify = s => String(s).toLowerCase().replace(/_/g, ' ').replace(/^\w/, c => c.toUpperCase());
const esc = s => String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const strong = s => '<strong>' + esc(s) + '</strong>';
function fmtMinutes(m) {
  if (m < 60) return nf.format(m) + ' min';
  if (m < 1440) return nf.format(m / 60) + ' h';
  return nf.format(m / 1440) + ' days';
}

const css = name => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
const series = n => css('--series-' + n);
const el = id => document.getElementById(id);

function setStatus(text, isError) {
  const node = el('status');
  if (!node) return;
  node.textContent = text;
  node.className = 'status' + (isError ? ' error' : '');
}
function setAnswer(html) { el('answer-text').innerHTML = html; }
function tiles(id, items) {
  el(id).innerHTML = items.map(t =>
    `<div class="tile"><div class="label">${esc(t.label)}</div><div class="value">${t.value}</div>` +
    (t.hint ? `<div class="hint">${t.hint}</div>` : '') + '</div>').join('');
}
function insights(id, items) {
  el(id).innerHTML = items.filter(Boolean).map(i => `<li>${i}</li>`).join('') || '<li>Not enough data yet.</li>';
}
function table(id, headers, rows) {
  const head = headers.map((h, i) => `<th${i ? ' class="num"' : ''}>${esc(h)}</th>`).join('');
  const body = rows.map(r => '<tr>' + r.map((c, i) => `<td${i ? ' class="num"' : ''}>${esc(c)}</td>`).join('') + '</tr>').join('');
  el(id).innerHTML = `<thead><tr>${head}</tr></thead><tbody>${body}</tbody>`;
}

// Charts
const charts = {};
function draw(id, config) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(el(id), config);
}
function themeDefaults() {
  Chart.defaults.color = css('--text-secondary');
  Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
  Chart.defaults.borderColor = css('--grid');
}
function axes(opts = {}) {
  const grid = { color: css('--grid') };
  const whole = opts.counts ? { ticks: { precision: 0 } } : {};  // counts are integers: no 0.1 ticks
  return {
    x: { grid: opts.horizontal ? grid : { display: false }, beginAtZero: true, ...(opts.horizontal && whole), ...opts.x },
    y: { grid: opts.horizontal ? { display: false } : grid, beginAtZero: true, ...(!opts.horizontal && whole), ...opts.y },
  };
}
function baseOptions(extra = {}) {
  const { legend = true, horizontal = false, counts = false, scales, plugins, ...rest } = extra;
  return {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: horizontal ? 'y' : 'x',
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { display: legend, position: 'top', align: 'start', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true } }, ...plugins },
    scales: scales || axes({ horizontal, counts }),
    ...rest,
  };
}
const bar = (label, data, n, extra = {}) => ({ label, data, backgroundColor: series(n), borderRadius: 4, maxBarThickness: 36, ...extra });
const line = (label, data, n, extra = {}) => ({ label, data, borderColor: series(n), backgroundColor: series(n), borderWidth: 2, pointRadius: 3, ...extra });

// Heatmap: rows x columns of counts, one hue, light to dark. `tip(r, c, v)` gives the hover text.
function heatmap(id, { rowLabels, colLabels, matrix, color, tip, colEvery = 1, unit = '' }) {
  const max = Math.max(0, ...matrix.flat());
  const shade = t => `color-mix(in srgb, ${color} ${Math.round(14 + t * 86)}%, transparent)`;
  let html = `<div class="heat" style="grid-template-columns: max-content repeat(${colLabels.length}, minmax(0, 1fr))"><div></div>`;
  html += colLabels.map((c, i) => `<div class="heat-col">${i % colEvery === 0 ? esc(c) : ''}</div>`).join('');
  matrix.forEach((row, r) => {
    html += `<div class="heat-row">${esc(rowLabels[r])}</div>`;
    row.forEach((v, c) => {
      const text = tip(r, c, v);
      html += `<div class="heat-cell" style="background:${v ? shade(v / max) : 'var(--grid)'}" data-tip="${esc(text)}" aria-label="${esc(text)}"></div>`;
    });
  });
  html += '</div><div class="heat-legend">Fewer ' +
    [0, .25, .5, .75, 1].map(t => `<i style="background:${shade(t)}"></i>`).join('') +
    ` More (max ${nf.format(max)}${unit})</div>`;
  el(id).innerHTML = html;
}
document.addEventListener('mouseover', e => {
  const cell = e.target.closest && e.target.closest('[data-tip]');
  const tipNode = el('tip');
  if (!cell) { tipNode.style.display = 'none'; return; }
  tipNode.textContent = cell.dataset.tip;
  tipNode.style.display = 'block';
});
document.addEventListener('mousemove', e => {
  const tipNode = el('tip');
  tipNode.style.left = Math.min(e.clientX + 12, window.innerWidth - 270) + 'px';
  tipNode.style.top = (e.clientY + 14) + 'px';
});

// Activity (BQ5): the endpoint returns Django weekdays (1 = Sunday) and UTC hours.
// Shifting by a whole-hour offset moves the hour and, across midnight, the weekday.
function activityGrids(d, offset) {
  const grid = () => Array.from({ length: 7 }, () => Array(24).fill(0));
  const out = { pub: grid(), brw: grid() };
  const add = (g, rows) => rows.forEach(r => {
    let day = r.day_of_week - 1, hour = r.hour + Math.round(offset);
    if (hour < 0) { hour += 24; day = (day + 6) % 7; } else if (hour >= 24) { hour -= 24; day = (day + 1) % 7; }
    g[day][hour] += r.total;
  });
  add(out.pub, d.publishing_activity);
  add(out.brw, d.browsing_activity);
  return out;
}
const perDay = g => g.map(row => total(row));
const perHour = g => HOURS.map(h => g.reduce((sum, row) => sum + row[h], 0));
const campusShort = () => `campus time, UTC${CAMPUS_OFFSET < 0 ? '−' : '+'}${Math.abs(CAMPUS_OFFSET)}`;
const campusLabel = () => `Campus time (UTC${CAMPUS_OFFSET < 0 ? '−' : '+'}${Math.abs(CAMPUS_OFFSET)})`;

// BQ12 helper: per-point totals for an optional hour.
function pointTotals(rows, hour) {
  const byPoint = new Map();
  rows.forEach(r => {
    const p = byPoint.get(r.meeting_point_id) || { id: r.meeting_point_id, name: r.name, lat: r.lat, lng: r.lng, monitored: r.is_monitored, total: 0 };
    if (hour === '' || hour === null || r.hour === Number(hour)) p.total += r.total;
    byPoint.set(r.meeting_point_id, p);
  });
  return [...byPoint.values()].sort((a, b) => b.total - a.total || a.name.localeCompare(b.name));
}

// One-line answers, used by the overview cards and by the "Answer" box of each question page.
const HEADLINES = {
  2(d) {
    const a = d.views_before_contact, b = d.views_before_exchange;
    if (!a.total_users_analyzed && !b.total_users_analyzed) return 'No buyer has contacted a seller or completed an exchange yet.';
    if (!a.total_users_analyzed) return `No buyer has contacted a seller yet. A typical buyer views ${strong(nf.format(b.median))} distinct listings before completing an exchange (median).`;
    let text = `A typical buyer views ${strong(nf.format(a.median))} distinct listings before contacting a seller`;
    text += b.total_users_analyzed ? ` and ${strong(nf.format(b.median))} before completing an exchange (medians).` : ' (median). No exchange has been completed yet.';
    return text;
  },
  4(d) {
    if (!d.conversations_analyzed) return 'No conversation has reached a meeting point agreement yet.';
    return `Buyer and seller exchange ${strong(nf.format(d.messages_before_agreement.median))} messages over ${strong(fmtMinutes(d.minutes_to_agreement.median))} (medians) before agreeing on a meeting point.`;
  },
  5(d) {
    const g = activityGrids(d, CAMPUS_OFFSET);
    if (!total(perHour(g.pub)) && !total(perHour(g.brw))) return 'No activity recorded yet.';
    const peak = grid => `${strong(hourLabel(argMax(perHour(grid))))} on ${strong(FULL_DAYS[argMax(perDay(grid))])}`;
    return `Students publish most at ${peak(g.pub)} and browse most at ${peak(g.brw)} (${campusShort()}).`;
  },
  6(d) {
    const rows = d.data;
    if (!rows.length) return 'No listings yet.';
    const byListings = [...rows].sort((a, b) => b.total_listings - a.total_listings)[0];
    const byExchanges = [...rows].sort((a, b) => b.completed_exchanges - a.completed_exchanges)[0];
    return `${strong(prettify(byListings.category))} has the most listings (${nf.format(byListings.total_listings)}); ` +
      (byExchanges.completed_exchanges ? `${strong(prettify(byExchanges.category))} has the most completed exchanges (${nf.format(byExchanges.completed_exchanges)}).` : 'no exchange has been completed yet.');
  },
  7(d) {
    if (!d.wishlist_items) return 'No wishlist items yet.';
    if (!d.items_with_smart_match) return `${strong(nf.format(d.buyers_with_wishlist))} buyers saved ${strong(nf.format(d.wishlist_items))} items, but none received a Smart Match yet.`;
    return `${strong(fmtPct(d.conversion_rate * 100))} of wishlist items that got a Smart Match were bought afterwards (${nf.format(d.purchased_after_smart_match)} of ${nf.format(d.items_with_smart_match)}), from ${nf.format(d.buyers_with_wishlist)} buyers.`;
  },
  12(d) {
    if (d.available === false) return 'Meeting point data is not available yet.';
    if (!d.data.length) return 'No completed exchange with a meeting point yet.';
    const points = pointTotals(d.data, '');
    const hours = HOURS.map(h => d.data.filter(r => r.hour === h).reduce((s, r) => s + r.total, 0));
    const all = total(points.map(p => p.total));
    return `${strong(points[0].name)} is the busiest meeting point (${nf.format(points[0].total)} of ${plural(all, 'exchange')}), and exchanges peak at ${strong(hourLabel(argMax(hours)))} (campus time).`;
  },
};

// Fetch the page's endpoint, render, and re-render when the OS theme changes. Resolves to a redraw function.
async function start(render) {
  let data;
  try {
    const response = await fetch(ENDPOINT);
    if (!response.ok) throw new Error('HTTP ' + response.status);
    data = await response.json();
  } catch (error) {
    setStatus('Could not load this question (' + error.message + ').', true);
    setAnswer('The data for this question could not be loaded.');
    return () => {};
  }
  setStatus('');
  const redraw = () => { themeDefaults(); render(data); };
  redraw();
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redraw);
  return redraw;
}
