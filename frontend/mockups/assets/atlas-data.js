/**
 * atlas-data.js — ATLAS §6.2 Data Loader
 *
 * Plain ES2020. No TypeScript, no bundler. Load via:
 *   <script defer src="assets/atlas-states.js"></script>
 *   <script defer src="assets/atlas-data.js"></script>
 *
 * Depends on atlas-states.js being loaded first.
 *
 * State machine:
 *   on load  → data-state="loading"  (renderSkeleton)
 *   on success:
 *     hasData + !isStale  → data-state="ready"
 *     hasData + isStale   → data-state="stale"  (renderStaleBanner)
 *     !hasData            → data-state="empty"  (renderEmpty)
 *   on error → data-state="error"    (renderError)
 *
 * Offline fixture fallback:
 *   If fetch fails with NetworkError AND el.dataset.fixture is set,
 *   retry with fetch(el.dataset.fixture). If fixture also fails, render error.
 *
 * Known-sparse-source guard:
 *   If json._meta.insufficient_data === true, call renderEmpty() regardless
 *   of records length. Never error on sparse data.
 */

'use strict';

// Default timeout for API calls (ms)
var LOAD_BLOCK_TIMEOUT_MS = 8000;


// ─── Core helpers ─────────────────────────────────────────────────────────────

/**
 * fetchWithTimeout(url, ms)
 * Wraps fetch() with an AbortController timeout.
 * @param {string} url - URL to fetch
 * @param {number} ms  - timeout in milliseconds
 * @returns {Promise<Response>}
 */
function fetchWithTimeout(url, ms) {
  var controller = new AbortController();
  var timer = setTimeout(function () {
    controller.abort();
  }, ms);

  return fetch(url, { signal: controller.signal }).then(function (response) {
    clearTimeout(timer);
    return response;
  }).catch(function (err) {
    clearTimeout(timer);
    throw err;
  });
}

/**
 * buildUrl(endpoint, params)
 * Merges an endpoint path with a params object.
 * @param {string} endpoint  - base URL path (e.g. "/api/v1/stocks/RELIANCE.NS")
 * @param {Object} [params]  - optional query parameter map
 * @returns {string} - full URL string
 */
function buildUrl(endpoint, params) {
  if (!params || Object.keys(params).length === 0) {
    return endpoint;
  }
  var qs = Object.entries(params)
    .filter(function (kv) { return kv[1] !== null && kv[1] !== undefined; })
    .map(function (kv) {
      return encodeURIComponent(kv[0]) + '=' + encodeURIComponent(String(kv[1]));
    })
    .join('&');
  return qs ? (endpoint + '?' + qs) : endpoint;
}

/**
 * hasData(json)
 * Returns true if the API response contains at least one record.
 * Checks records, series, and divergences arrays.
 * @param {Object} json - parsed API response
 * @returns {boolean}
 */
function hasData(json) {
  if (!json) return false;
  var records = json.records;
  var series = json.series;
  var divergences = json.divergences;
  return (
    (Array.isArray(records) && records.length > 0) ||
    (Array.isArray(series) && series.length > 0) ||
    (Array.isArray(divergences) && divergences.length > 0)
  );
}

/**
 * isStale(el, json)
 * Compares json._meta.staleness_seconds against STALENESS_THRESHOLDS.
 * @param {Element} el  - the data block element (must have data-data-class attribute)
 * @param {Object}  json - parsed API response with _meta.staleness_seconds
 * @returns {boolean} - true if staleness_seconds exceeds threshold for the data class
 */
function isStale(el, json) {
  if (!json || !json._meta) return false;

  var stalenessSeconds = json._meta.staleness_seconds;
  if (typeof stalenessSeconds !== 'number') return false;

  var dataClass = el.dataset.dataClass;
  if (!dataClass) return false;

  var thresholds = (typeof window !== 'undefined' && window.STALENESS_THRESHOLDS)
    ? window.STALENESS_THRESHOLDS
    : {};

  var threshold = thresholds[dataClass];
  if (typeof threshold !== 'number') return false;

  return stalenessSeconds > threshold;
}


// ─── State machine ────────────────────────────────────────────────────────────

/**
 * _handleSuccess(el, json)
 * Applies state after a successful API response.
 * Known-sparse guard: if json._meta.insufficient_data === true → empty.
 * @param {Element} el
 * @param {Object}  json
 */
function _handleSuccess(el, json) {
  // Known-sparse-source guard: insufficient_data overrides record length
  if (json && json._meta && json._meta.insufficient_data === true) {
    if (typeof window.renderEmpty === 'function') {
      window.renderEmpty(el);
    } else {
      el.setAttribute('data-state', 'empty');
    }
    return;
  }

  if (!hasData(json)) {
    // No records — render empty state
    if (typeof window.renderEmpty === 'function') {
      window.renderEmpty(el);
    } else {
      el.setAttribute('data-state', 'empty');
    }
    return;
  }

  if (isStale(el, json)) {
    // Has data but stale — render stale banner
    el.setAttribute('data-state', 'stale');
    if (typeof window.renderStaleBanner === 'function') {
      window.renderStaleBanner(el, json);
    }
    return;
  }

  // Data present, fresh — render ready
  el.setAttribute('data-state', 'ready');
}

/**
 * _handleError(el, err)
 * Renders error state on the element.
 * @param {Element} el
 * @param {Error|Object} err
 */
function _handleError(el, err) {
  if (typeof window.renderError === 'function') {
    window.renderError(el, err);
  } else {
    el.setAttribute('data-state', 'error');
  }
}

/**
 * _isNetworkError(err)
 * Returns true if the error is a network connectivity failure (not an abort).
 * @param {Error} err
 * @returns {boolean}
 */
function _isNetworkError(err) {
  if (!err) return false;
  // AbortError means intentional abort/timeout — not a network failure
  if (err.name === 'AbortError') return false;
  // TypeError is thrown by fetch on network errors (CORS, DNS, offline)
  return err instanceof TypeError || err.name === 'TypeError';
}


/**
 * loadBlock(el)
 * Main entry point. Fetches data-endpoint, manages state transitions.
 *
 * Reads from element dataset:
 *   el.dataset.endpoint    — API endpoint path (required)
 *   el.dataset.params      — JSON-encoded query params (optional)
 *   el.dataset.dataClass   — staleness threshold key (optional)
 *   el.dataset.fixture     — offline fallback fixture URL (optional)
 *
 * @param {Element} el - the data block element
 * @returns {Promise<void>}
 */
function loadBlock(el) {
  if (!el) return Promise.resolve();

  var endpoint = el.dataset.endpoint;
  if (!endpoint) {
    var noEndpointErr = { code: 'NO_ENDPOINT', message: 'data-endpoint attribute is missing.' };
    _handleError(el, noEndpointErr);
    return Promise.resolve();
  }

  // 1. Show skeleton immediately
  if (typeof window.renderSkeleton === 'function') {
    window.renderSkeleton(el);
  } else {
    el.setAttribute('data-state', 'loading');
  }

  // Build query params
  var params = null;
  try {
    if (el.dataset.params) {
      params = JSON.parse(el.dataset.params);
    }
  } catch (_) {
    // Ignore malformed params
  }

  var url = buildUrl(endpoint, params);

  // 2. Fetch with 8s timeout
  return fetchWithTimeout(url, LOAD_BLOCK_TIMEOUT_MS)
    .then(function (response) {
      if (!response.ok) {
        var httpErr = {
          code: 'HTTP_' + response.status,
          message: 'Server returned ' + response.status + ' ' + response.statusText,
        };
        _handleError(el, httpErr);
        return;
      }
      return response.json().then(function (json) {
        _handleSuccess(el, json);
      });
    })
    .catch(function (err) {
      // Offline fixture fallback: only on network errors (not abort/timeout)
      var fixtureUrl = el.dataset.fixture;
      if (_isNetworkError(err) && fixtureUrl) {
        return fetch(fixtureUrl)
          .then(function (fixtureResponse) {
            if (!fixtureResponse.ok) {
              _handleError(el, { code: 'FIXTURE_HTTP_' + fixtureResponse.status, message: 'Fixture load failed.' });
              return;
            }
            return fixtureResponse.json().then(function (fixtureJson) {
              // Tag as fixture so UI can show an indicator if desired
              if (fixtureJson && fixtureJson._meta) {
                fixtureJson._meta.from_fixture = true;
              }
              _handleSuccess(el, fixtureJson);
            });
          })
          .catch(function (fixtureErr) {
            _handleError(el, { code: 'FIXTURE_LOAD_ERROR', message: String(fixtureErr.message || fixtureErr) });
          });
      }

      // Timeout or unexpected error — render error
      var code = err.name === 'AbortError' ? 'TIMEOUT' : 'NETWORK_ERROR';
      _handleError(el, { code: code, message: String(err.message || err) });
    });
}


// ─── Auto-wire on DOMContentLoaded ───────────────────────────────────────────

/**
 * Auto-load all [data-endpoint] blocks on the page.
 * Components can also call loadBlock(el) manually.
 */
function _autoLoad() {
  var blocks = document.querySelectorAll('[data-endpoint]');
  blocks.forEach(function (el) {
    loadBlock(el);
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', _autoLoad);
} else {
  // DOMContentLoaded already fired
  _autoLoad();
}


// Expose public API at window level
window.loadBlock = loadBlock;
window.fetchWithTimeout = fetchWithTimeout;
window.buildUrl = buildUrl;
window.hasData = hasData;
window.isStale = isStale;
