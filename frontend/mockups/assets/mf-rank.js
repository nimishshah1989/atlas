/* mf-rank.js — extracted from mf-rank.html inline script (V2FE-7) */
(function () {
  'use strict';

  // Category display names (no Math.random, no unseeded Date)
  var CATEGORY_LABELS = {
    'flexi_cap':  'Flexi Cap',
    'large_cap':  'Large Cap',
    'mid_cap':    'Mid Cap',
    'small_cap':  'Small Cap',
    'multi_cap':  'Multi Cap',
    'elss':       'ELSS',
    'balanced':   'Balanced'
  };

  var CATEGORY_DOT_CLASSES = {
    'flexi_cap': 'filter-item__dot--flexi-cap',
    'large_cap': 'filter-item__dot--large-cap',
    'mid_cap':   'filter-item__dot--mid-cap',
    'small_cap': 'filter-item__dot--small-cap'
  };

  function categoryLabel(cat) {
    return CATEGORY_LABELS[cat] || cat.replace(/_/g, ' ').replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function categoryDotClass(cat) {
    return CATEGORY_DOT_CLASSES[cat] || 'filter-item__dot--all';
  }

  function formatAum(crore) {
    if (crore >= 100) {
      return '₹' + crore.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }
    return '₹' + crore.toFixed(2);
  }

  function scorePill(composite) {
    if (composite >= 75) return 'composite-pill--high';
    if (composite >= 65) return 'composite-pill--mid';
    return 'composite-pill--low';
  }

  function rankBadgeClass(rank) {
    if (rank === 1) return 'rank-badge--1';
    if (rank === 2) return 'rank-badge--2';
    if (rank === 3) return 'rank-badge--3';
    return 'rank-badge--n';
  }

  function scoreBarHtml(score, cls) {
    var pct = Math.min(100, Math.max(0, score));
    return '<div class="score-cell ' + cls + '">' +
      '<span class="score-cell__val">' + score.toFixed(1) + '</span>' +
      '<div class="score-cell__bar"><div class="score-cell__fill" style="width:' + pct + '%"></div></div>' +
      '</div>';
  }

  function renderRow(fund) {
    var rank = fund.rank || 0;
    var badgeClass = rankBadgeClass(rank);
    var catLabel = categoryLabel(fund.category || '');
    var catClass = 'cat-pill--' + (fund.category || '').replace(/_/g, '-');

    var row = document.createElement('tr');
    row.setAttribute('data-mstar-id', fund.mstar_id || '');
    row.innerHTML =
      '<td class="left">' +
        '<span class="rank-badge ' + badgeClass + '">' + rank + '</span>' +
      '</td>' +
      '<td class="left">' +
        '<div class="fund-name-cell">' +
          '<span class="fund-name-cell__primary">' + (fund.fund_name || '') + '</span>' +
          '<span class="fund-name-cell__scheme">' + (fund.scheme_code || '') + '</span>' +
        '</div>' +
      '</td>' +
      '<td class="left"><span class="cat-pill ' + catClass + '">' + catLabel + '</span></td>' +
      '<td class="num">' + formatAum(fund.aum_crore || 0) + '</td>' +
      '<td class="num">' + scoreBarHtml(fund.returns_score || 0, 'score-cell--returns') + '</td>' +
      '<td class="num">' + scoreBarHtml(fund.risk_score || 0, 'score-cell--risk') + '</td>' +
      '<td class="num">' + scoreBarHtml(fund.resilience_score || 0, 'score-cell--resilience') + '</td>' +
      '<td class="num">' + scoreBarHtml(fund.consistency_score || 0, 'score-cell--consistency') + '</td>' +
      '<td class="num">' +
        '<div class="composite-cell">' +
          '<span class="composite-num">' + (fund.composite_score || 0).toFixed(1) + '</span>' +
          '<span class="composite-pill ' + scorePill(fund.composite_score || 0) + '">' +
            (fund.composite_score >= 75 ? 'Strong' : fund.composite_score >= 65 ? 'Moderate' : 'Weak') +
          '</span>' +
        '</div>' +
      '</td>' +
      '<td class="num tb-rank">' + (fund.tie_break_rank || rank) + '</td>' +
      '<td class="num" style="display:none"><span data-role="rank-sparkline"></span></td>';

    return row;
  }

  function buildCategoryFilter(funds, filterBody) {
    var cats = {};
    funds.forEach(function (f) { cats[f.category] = (cats[f.category] || 0) + 1; });
    Object.keys(cats).sort().forEach(function (cat) {
      var item = document.createElement('div');
      item.className = 'filter-item';
      item.setAttribute('data-filter-value', cat);
      item.innerHTML =
        '<span class="filter-item__dot ' + categoryDotClass(cat) + '"></span>' +
        categoryLabel(cat) +
        '<span class="filter-item__count">' + cats[cat] + '</span>';
      filterBody.appendChild(item);
    });
  }

  function renderFixture(data) {
    var funds = data.funds || [];
    var tbody = document.getElementById('rank-tbody');
    if (!tbody) return;

    // Sort by rank (already sorted in fixture, but be explicit)
    var sorted = funds.slice().sort(function (a, b) { return a.rank - b.rank; });

    sorted.forEach(function (fund) {
      tbody.appendChild(renderRow(fund));
    });

    // Universe bar
    var uCount = document.getElementById('universe-count');
    var cCount = document.getElementById('category-count');
    var rAsOf  = document.getElementById('ranked-as-of');
    if (uCount) uCount.textContent = String(data.universe_size || funds.length);
    if (cCount) {
      var cats = {};
      funds.forEach(function (f) { cats[f.category] = true; });
      cCount.textContent = String(Object.keys(cats).length);
    }
    if (rAsOf) rAsOf.textContent = data.ranking_as_of || data.data_as_of || '';

    // Table meta
    var meta = document.getElementById('table-meta');
    if (meta) {
      meta.textContent = funds.length + ' funds · data as of ' + (data.data_as_of || '');
    }

    // Footer
    var footerDate = document.getElementById('footer-data-as-of');
    if (footerDate) footerDate.textContent = data.data_as_of || '';

    // Filter all count
    var filterAllCount = document.getElementById('filter-all-count');
    if (filterAllCount) filterAllCount.textContent = String(funds.length);

    // Category filter
    var filterBody = document.getElementById('category-filter-body');
    if (filterBody) buildCategoryFilter(funds, filterBody);

    // DP slots: update data-as-of on regime-banner + signal-strip
    var regimeBanner = document.querySelector('[data-component="regime-banner"]');
    if (regimeBanner) regimeBanner.setAttribute('data-as-of', data.data_as_of || '');
  }

  // Filter-rail interaction: re-fire loadBlock when any filter changes
  function initFilterRail() {
    var filterRail = document.querySelector('[data-block="filter-rail"]');
    var rankTable = document.querySelector('[data-block="rank-table"]');
    if (!filterRail || !rankTable) return;

    // Category filter
    filterRail.addEventListener('click', function (e) {
      var filterItem = e.target.closest('[data-filter-value]');
      var aumItem = e.target.closest('[data-filter-aum]');
      var scoreItem = e.target.closest('[data-filter-score]');
      if (!filterItem && !aumItem && !scoreItem) return;

      // Update active states
      if (filterItem) {
        var catItems = filterRail.querySelectorAll('[data-filter-value]');
        catItems.forEach(function (i) { i.classList.remove('filter-item--active'); });
        filterItem.classList.add('filter-item--active');
        window.__mfRankFilters = window.__mfRankFilters || {};
        window.__mfRankFilters.category = filterItem.dataset.filterValue;
      }
      if (aumItem) {
        var aumItems = filterRail.querySelectorAll('[data-filter-aum]');
        aumItems.forEach(function (i) { i.classList.remove('filter-item--active'); });
        aumItem.classList.add('filter-item--active');
        window.__mfRankFilters = window.__mfRankFilters || {};
        window.__mfRankFilters.aum = aumItem.dataset.filterAum;
      }
      if (scoreItem) {
        var scoreItems = filterRail.querySelectorAll('[data-filter-score]');
        scoreItems.forEach(function (i) { i.classList.remove('filter-item--active'); });
        scoreItem.classList.add('filter-item--active');
        window.__mfRankFilters = window.__mfRankFilters || {};
        window.__mfRankFilters.minScore = parseInt(scoreItem.dataset.filterScore, 10) || 0;
      }

      // Re-fire loadBlock with updated params
      if (typeof window.loadBlock === 'function') {
        var filters = window.__mfRankFilters || {};
        var baseParams = { template: 'mf_rank_composite', params: { limit: 100 } };
        if (filters.category && filters.category !== 'all') {
          baseParams.params.category = filters.category;
        }
        if (filters.aum && filters.aum !== 'all') {
          baseParams.params.aum_band = filters.aum;
        }
        if (filters.minScore && filters.minScore > 0) {
          baseParams.params.min_score = filters.minScore;
        }
        rankTable.dataset.params = JSON.stringify(baseParams);
        window.loadBlock(rankTable);
      }
    });
  }

  // Batched sparkline loading after rank table renders
  function loadSparklines(funds) {
    var mstarIds = funds.map(function (f) { return f.mstar_id; }).filter(Boolean);
    if (mstarIds.length === 0) return;
    // Single POST with all mstar_ids (N+1 guard)
    var rankTable = document.querySelector('[data-block="rank-table"]');
    if (!rankTable) return;
    fetch('/api/v1/query/template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template: 'mf_rank_history', mstar_ids: mstarIds })
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
      // Render sparklines per row if backend available
      var sparkData = data.sparklines || {};
      Object.keys(sparkData).forEach(function (mstarId) {
        var row = rankTable.querySelector('[data-mstar-id="' + mstarId + '"]');
        if (row) {
          var sparkCell = row.querySelector('[data-role="rank-sparkline"]');
          if (sparkCell) {
            sparkCell.dataset.loaded = 'true';
          }
        }
      });
    })
    .catch(function () {
      // Sparklines are secondary — degrade silently
    });
  }

  // Initialize filter rail interaction
  initFilterRail();

  // Attempt API first (atlas-data.js handles this for data-endpoint blocks)
  // For backward compat: also fetch fixture for the inline table render
  fetch('fixtures/mf_rank_universe.json')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      renderFixture(data);
      // After table renders, load sparklines (batched, single call)
      loadSparklines(data.funds || []);
    })
    .catch(function () {
      var tbody = document.getElementById('rank-tbody');
      if (tbody) {
        var tr = document.createElement('tr');
        var td = document.createElement('td');
        td.setAttribute('colspan', '10');
        td.style.textAlign = 'center';
        td.style.padding = '20px';
        td.style.color = 'var(--text-tertiary)';
        td.textContent = 'Could not load fixture data (run from a local server).';
        tr.appendChild(td);
        tbody.appendChild(tr);
      }
    });
}());
