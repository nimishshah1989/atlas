/**
 * atlas-states.js — ATLAS §6.3 State Renderers
 *
 * Plain ES2020. No TypeScript, no bundler. Load via:
 *   <script defer src="assets/atlas-states.js"></script>
 *
 * Must be loaded BEFORE atlas-data.js so STALENESS_THRESHOLDS is available.
 */

'use strict';

// ─── §6.3 Staleness thresholds (seconds) ─────────────────────────────────────
// Values are authoritative. Any deviation blocks downstream chunks.

const STALENESS_THRESHOLDS = {
  intraday:      3600,    // 1 hour
  eod_breadth:   21600,   // 6 hours
  daily_regime:  86400,   // 24 hours
  fundamentals:  604800,  // 7 days
  events:        604800,  // 7 days
  holdings:      604800,  // 7 days
  system:        21600,   // 6 hours
};

// Expose at window level for atlas-data.js to consume
window.STALENESS_THRESHOLDS = STALENESS_THRESHOLDS;


// ─── State renderers ──────────────────────────────────────────────────────────

/**
 * renderSkeleton(el)
 * Injects a skeleton placeholder while data is loading.
 * Selects skeleton variant based on el.dataset.blockType:
 *   "chart"  → square block placeholder
 *   "table"  → three full-width line placeholders
 *   (other)  → generic wide/medium/narrow lines (default)
 * Sets data-state="loading" on the element.
 */
function renderSkeleton(el) {
  el.setAttribute('data-state', 'loading');
  var blockType = el.dataset ? el.dataset.blockType : '';
  var inner;
  if (blockType === 'chart') {
    inner = '<div class="skeleton-block skeleton-block--chart" aria-hidden="true">' +
      '  <div class="skeleton-block__square"></div>' +
      '</div>';
  } else if (blockType === 'table') {
    inner = '<div class="skeleton-block skeleton-block--table" aria-hidden="true">' +
      '  <div class="skeleton-block__line skeleton-block__line--full"></div>' +
      '  <div class="skeleton-block__line skeleton-block__line--full"></div>' +
      '  <div class="skeleton-block__line skeleton-block__line--full"></div>' +
      '</div>';
  } else {
    inner =
      '<div class="skeleton-block" aria-hidden="true">' +
      '  <div class="skeleton-block__line skeleton-block__line--wide"></div>' +
      '  <div class="skeleton-block__line skeleton-block__line--medium"></div>' +
      '  <div class="skeleton-block__line skeleton-block__line--narrow"></div>' +
      '</div>';
  }
  el.innerHTML = inner;
}

/**
 * renderEmpty(el)
 * Injects the empty-state subtree from components.html when no data exists.
 * Sets data-state="empty" on the element.
 */
function renderEmpty(el) {
  el.setAttribute('data-state', 'empty');
  el.innerHTML =
    '<div class="empty-state" role="status" aria-live="polite">' +
    '  <div class="empty-state__icon" aria-hidden="true">&#8709;</div>' +
    '  <p class="empty-state__title">No data available</p>' +
    '  <p class="empty-state__body">This data source has no records for the selected period.</p>' +
    '</div>';
}

/**
 * renderStaleBanner(el, json)
 * Prepends an amber staleness banner with data_as_of text.
 * Sets data-state="stale" on the element.
 * @param {Element} el  - the data block element
 * @param {Object}  json - the API response containing _meta.data_as_of
 */
function renderStaleBanner(el, json) {
  el.setAttribute('data-state', 'stale');

  const meta = (json && json._meta) ? json._meta : {};
  const dataAsOf = meta.data_as_of || 'unknown';

  // Remove any existing staleness banner to avoid duplicates
  const existing = el.querySelector('[data-staleness-banner]');
  if (existing) {
    existing.remove();
  }

  const banner = document.createElement('div');
  banner.setAttribute('data-staleness-banner', 'true');
  banner.setAttribute('role', 'alert');
  banner.className = 'staleness-banner staleness-banner--amber';
  banner.innerHTML =
    '<span class="staleness-banner__icon" aria-hidden="true">&#9888;</span> ' +
    'Data may be stale. Last updated: <time datetime="' + dataAsOf + '">' + dataAsOf + '</time>';

  el.insertBefore(banner, el.firstChild);
}

/**
 * renderError(el, err)
 * Injects an error card with err.code and a retry affordance.
 * Sets data-state="error" on the element.
 * @param {Element} el  - the data block element
 * @param {Object}  err - error object with optional .code and .message properties
 */
function renderError(el, err) {
  el.setAttribute('data-state', 'error');

  const code = (err && err.code) ? String(err.code) : 'UNKNOWN_ERROR';
  const message = (err && err.message) ? String(err.message) : 'An unexpected error occurred.';

  el.innerHTML =
    '<div class="error-card" role="alert">' +
    '  <div class="error-card__header">' +
    '    <span class="error-card__icon" aria-hidden="true">&#9888;</span>' +
    '    <span class="error-card__code">' + code + '</span>' +
    '  </div>' +
    '  <p class="error-card__message">' + message + '</p>' +
    '  <button class="error-card__retry" data-retry="true" aria-label="Retry loading this block">' +
    '    &#8635; Retry' +
    '  </button>' +
    '</div>';

  var retryBtn = el.querySelector('[data-retry="true"]');
  if (retryBtn) {
    retryBtn.addEventListener('click', function () {
      if (typeof window.loadBlock === 'function') {
        window.loadBlock(el);
      }
    });
  }
}


// Expose all renderers at window level
window.renderSkeleton = renderSkeleton;
window.renderEmpty = renderEmpty;
window.renderStaleBanner = renderStaleBanner;
window.renderError = renderError;
