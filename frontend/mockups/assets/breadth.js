/* breadth.js — extracted from breadth.html inline script (V2FE-4) */
(function () {
  'use strict';

  // ── Tab switching ─────────────────────────────────────────────────────────
  function switchTab(btn, tabId) {
    var bar = document.getElementById('sim-tab-bar');
    if (bar) {
      var btns = bar.querySelectorAll('.tab-btn');
      btns.forEach(function (b) { b.classList.remove('active'); });
    }
    btn.classList.add('active');
    var panels = document.querySelectorAll('.tab-panel');
    panels.forEach(function (p) { p.classList.remove('active'); });
    var panel = document.getElementById('panel-' + tabId);
    if (panel) panel.classList.add('active');
  }

  // Expose to inline onclick (no Math.random)
  window.switchTab = switchTab;

  // ── Formatting helpers (Indian lakh/crore formatting only) ─────────────
  function fmtCount(n) {
    if (n === null || n === undefined) return '—';
    return String(n);
  }

  function fmtPct(count, total) {
    if (count === null || count === undefined) return '—';
    var pct = (count / total) * 100;
    return pct.toFixed(1) + '%';
  }

  function pctClass(count, total) {
    var pct = (count / total) * 100;
    if (pct >= 60) return 'hero-card__pct--high';
    if (pct >= 40) return 'hero-card__pct--mid';
    return 'hero-card__pct--low';
  }

  function fmtDate(d) {
    // Convert YYYY-MM-DD to DD-MMM-YYYY (IST display)
    if (!d) return '—';
    var parts = d.split('-');
    if (parts.length !== 3) return d;
    var months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
    var mo = months[parseInt(parts[1], 10) - 1] || parts[1];
    return parts[2] + '-' + mo + '-' + parts[0];
  }

  function fmtRupees(n) {
    // Indian lakh/crore formatting
    if (n === null || n === undefined) return '—';
    if (n >= 10000000) {
      return '₹' + (n / 10000000).toFixed(2) + ' Cr';
    }
    if (n >= 100000) {
      return '₹' + (n / 100000).toFixed(2) + ' L';
    }
    return '₹' + n.toLocaleString('en-IN');
  }

  // ── Regime classification ─────────────────────────────────────────────────
  function classifyRegime(ema21, dma50, dma200) {
    var avg = (ema21 + dma50 + dma200) / 3;
    if (avg >= 350) return 'bullish';
    if (avg <= 150) return 'bearish';
    return 'neutral';
  }

  // ── Event type display ────────────────────────────────────────────────────
  var EVENT_LABELS = {
    'entered_ob':         'Entered OB',
    'exited_ob':          'Exited OB',
    'entered_os':         'Entered OS',
    'exited_os':          'Exited OS',
    'crossed_midline_up': 'Crossed Midline ↑',
    'crossed_midline_dn': 'Crossed Midline ↓'
  };

  function eventChipClass(evType) {
    if (evType === 'entered_ob' || evType === 'exited_ob') return 'ev-chip--ob';
    if (evType === 'entered_os' || evType === 'exited_os') return 'ev-chip--os';
    return 'ev-chip--mid';
  }

  // ── Populate headline counts from latest data point ───────────────────────
  function populateHero(latestRow, dataAsOf) {
    var total = latestRow.universe_size || 500;
    var ema21 = latestRow.ema21_count;
    var dma50  = latestRow.dma50_count;
    var dma200 = latestRow.dma200_count;

    // Hero counts
    var el;
    el = document.getElementById('count-ema21');  if (el) el.textContent = fmtCount(ema21);
    el = document.getElementById('count-dma50');   if (el) el.textContent = fmtCount(dma50);
    el = document.getElementById('count-dma200');  if (el) el.textContent = fmtCount(dma200);

    // Percentages
    var p21El = document.getElementById('pct-ema21');
    var p50El = document.getElementById('pct-dma50');
    var p200El = document.getElementById('pct-dma200');
    if (p21El) {
      p21El.textContent = fmtPct(ema21, total);
      p21El.className = 'hero-card__pct ' + pctClass(ema21, total);
    }
    if (p50El) {
      p50El.textContent = fmtPct(dma50, total);
      p50El.className = 'hero-card__pct ' + pctClass(dma50, total);
    }
    if (p200El) {
      p200El.textContent = fmtPct(dma200, total);
      p200El.className = 'hero-card__pct ' + pctClass(dma200, total);
    }

    // KPI tiles
    var k21 = document.getElementById('kpi-pct-ema21');
    var k50  = document.getElementById('kpi-pct-dma50');
    var k200 = document.getElementById('kpi-pct-dma200');
    if (k21) k21.textContent = fmtPct(ema21, total);
    if (k50) k50.textContent = fmtPct(dma50, total);
    if (k200) k200.textContent = fmtPct(dma200, total);

    // Regime band
    var regime = classifyRegime(ema21, dma50, dma200);
    el = document.getElementById('regime-state');
    if (el) {
      el.textContent = regime.charAt(0).toUpperCase() + regime.slice(1);
      el.className = 'regime-band__state regime-band__state--' + regime;
    }
    el = document.getElementById('rb-ema21');  if (el) el.textContent = fmtCount(ema21);
    el = document.getElementById('rb-dma50');   if (el) el.textContent = fmtCount(dma50);
    el = document.getElementById('rb-dma200');  if (el) el.textContent = fmtCount(dma200);
    el = document.getElementById('rb-asof');    if (el) el.textContent = fmtDate(dataAsOf);

    // Describe block
    el = document.getElementById('describe-regime'); if (el) el.textContent = regime;
    el = document.getElementById('desc-ema21');  if (el) el.textContent = fmtCount(ema21);
    el = document.getElementById('desc-dma50');  if (el) el.textContent = fmtCount(dma50);
    el = document.getElementById('desc-dma200'); if (el) el.textContent = fmtCount(dma200);
    el = document.getElementById('describe-asof'); if (el) el.textContent = fmtDate(dataAsOf);

    // Footer
    el = document.getElementById('footer-data-as-of'); if (el) el.textContent = fmtDate(dataAsOf);
  }

  // ── Populate KPI deltas from two most recent rows ─────────────────────────
  function populateDeltas(latestRow, prevRow) {
    if (!prevRow) return;
    var total = latestRow.universe_size || 500;
    var pairs = [
      { id: 'kpi-delta-ema21', cur: latestRow.ema21_count, prev: prevRow.ema21_count },
      { id: 'kpi-delta-dma50',  cur: latestRow.dma50_count,  prev: prevRow.dma50_count },
      { id: 'kpi-delta-dma200', cur: latestRow.dma200_count, prev: prevRow.dma200_count }
    ];
    pairs.forEach(function (p) {
      var el = document.getElementById(p.id);
      if (!el) return;
      var delta = p.cur - p.prev;
      var sign = delta >= 0 ? '+' : '';
      el.textContent = sign + delta + ' vs prior day';
      el.className = 'kpi-tile__delta kpi-tile__delta--' + (delta >= 0 ? 'pos' : 'neg');
    });
  }

  // ── Build oscillator SVG polyline ─────────────────────────────────────────
  function buildOscillatorLine(series, fieldName, lineId, color) {
    var lineEl = document.getElementById(lineId);
    if (!lineEl || !series || series.length === 0) return;

    var W = 900, H = 200;
    var maxVal = 500;

    var pts = series.map(function (row, i) {
      var x = (i / (series.length - 1)) * W;
      var val = row[fieldName] || 0;
      var y = H - (val / maxVal) * H;
      return x.toFixed(1) + ',' + y.toFixed(1);
    });

    lineEl.setAttribute('points', pts.join(' '));
    lineEl.setAttribute('stroke', color);
  }

  // ── Build event dots on oscillator ───────────────────────────────────────
  function buildEventDots(series, events, svgGroupId) {
    var grp = document.getElementById(svgGroupId);
    if (!grp || !events || !series || series.length === 0) return;

    var W = 900, H = 200, maxVal = 500;

    // Build date-to-index map
    var dateMap = {};
    series.forEach(function (row, i) { dateMap[row.date] = i; });

    events.forEach(function (ev) {
      var idx = dateMap[ev.date];
      if (idx === undefined) return;
      var x = (idx / (series.length - 1)) * W;
      var y = H - ((ev.value || 250) / maxVal) * H;

      var circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', x.toFixed(1));
      circle.setAttribute('cy', y.toFixed(1));
      circle.setAttribute('r', '5');

      var evType = ev.event_type || '';
      var fill = 'var(--rag-amber-500)';
      if (evType.indexOf('ob') !== -1) fill = 'var(--rag-red-500)';
      if (evType.indexOf('os') !== -1) fill = 'var(--rag-green-500)';

      circle.setAttribute('fill', fill);
      circle.setAttribute('stroke', 'var(--bg-surface)');
      circle.setAttribute('stroke-width', '1.5');
      circle.setAttribute('opacity', '0.85');

      var title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
      title.textContent = fmtDate(ev.date) + ' · ' + (EVENT_LABELS[evType] || evType) + ' · Count: ' + ev.value;
      circle.appendChild(title);

      grp.appendChild(circle);
    });
  }

  // ── Build ROC oscillator ──────────────────────────────────────────────────
  function buildRocLine(series, fieldName) {
    var lineEl = document.getElementById('roc-line');
    if (!lineEl || !series || series.length < 6) return;

    var W = 900, H = 120;
    var roc = [];
    for (var i = 5; i < series.length; i++) {
      var cur = series[i][fieldName] || 0;
      var prev = series[i - 5][fieldName] || 1;
      roc.push(cur - prev);
    }

    var maxAbs = 0;
    roc.forEach(function (v) { if (Math.abs(v) > maxAbs) maxAbs = Math.abs(v); });
    if (maxAbs === 0) maxAbs = 1;

    var pts = roc.map(function (v, i) {
      var x = (i / (roc.length - 1)) * W;
      var y = H / 2 - (v / maxAbs) * (H / 2 - 8);
      return x.toFixed(1) + ',' + y.toFixed(1);
    });

    lineEl.setAttribute('points', pts.join(' '));
  }

  // ── Populate signal history table ─────────────────────────────────────────
  function populateSignalHistory(events) {
    var tbody = document.getElementById('signal-history-tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!events || events.length === 0) {
      var row = document.createElement('tr');
      var td = document.createElement('td');
      td.colSpan = 6;
      td.style.textAlign = 'center';
      td.style.padding = '16px';
      td.style.color = 'var(--text-tertiary)';
      td.style.fontSize = '12px';
      td.textContent = 'No zone transition events in this period.';
      row.appendChild(td);
      tbody.appendChild(row);
      return;
    }

    // Sort events descending by date (most recent first)
    var sorted = events.slice().sort(function (a, b) {
      return b.date < a.date ? -1 : b.date > a.date ? 1 : 0;
    });

    sorted.forEach(function (ev) {
      var tr = document.createElement('tr');
      var evType = ev.event_type || '';
      var chipCls = eventChipClass(evType);
      var priorZoneLabel = ev.prior_zone === 'ob' ? 'Overbought' :
                          ev.prior_zone === 'os' ? 'Oversold' : 'Neutral';

      tr.innerHTML =
        '<td>' + fmtDate(ev.date) + '</td>' +
        '<td><span class="ev-chip ' + chipCls + '">' + (EVENT_LABELS[evType] || evType) + '</span></td>' +
        '<td>' + (ev.indicator || '').toUpperCase() + '</td>' +
        '<td>' + priorZoneLabel + '</td>' +
        '<td class="num">' + (ev.prior_zone_duration_days || '—') + ' days</td>' +
        '<td class="num">' + (ev.value !== undefined ? ev.value : '—') + '</td>';

      tbody.appendChild(tr);
    });
  }

  // ── Main render function ──────────────────────────────────────────────────
  function renderBreadth(breadthData, zoneData) {
    var series = breadthData.series || [];
    var dataAsOf = breadthData.data_as_of || '';
    var events = (zoneData && zoneData.events) ? zoneData.events : [];

    if (series.length === 0) return;

    // Latest + previous rows (sorted newest-last in fixture)
    var latest = series[series.length - 1];
    var prev = series.length > 1 ? series[series.length - 2] : null;

    // Populate hero, kpi, regime, describe
    populateHero(latest, dataAsOf);
    populateDeltas(latest, prev);

    // Build oscillator lines
    buildOscillatorLine(series, 'ema21_count', 'oscillator-line', 'var(--accent-700)');
    buildRocLine(series, 'ema21_count');

    // Build event dots
    buildEventDots(series, events, 'event-dots');

    // Populate signal history
    populateSignalHistory(events);
  }

  // ── Fetch both fixtures in parallel ───────────────────────────────────────
  var breadthPromise = fetch('fixtures/breadth_daily_5y.json').then(function (r) { return r.json(); });
  var zonePromise = fetch('fixtures/zone_events.json').then(function (r) { return r.json(); });

  Promise.all([breadthPromise, zonePromise])
    .then(function (results) {
      renderBreadth(results[0], results[1]);
    })
    .catch(function (err) {
      var describe = document.getElementById('describe-body');
      if (describe) {
        describe.innerHTML = '<em style="color:var(--text-tertiary);">Could not load fixture data (run from a local server).</em>';
      }
    });

}());
