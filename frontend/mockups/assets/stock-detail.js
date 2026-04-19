/**
 * stock-detail.js — Stock Detail page (hub-and-spoke equity terminal) init.
 *
 * Plain ES2020. No TypeScript, no bundler. Load via:
 *   <script defer src="assets/atlas-states.js"></script>
 *   <script defer src="assets/atlas-data.js"></script>
 *   <script defer src="assets/stock-detail.js"></script>  ← this file (load last)
 *
 * Responsibilities:
 *   1. Read data-symbol from <main data-symbol="HDFCBANK"> (override with ?symbol=X)
 *   2. Set window.__stockSymbol so atlas-data.js substitutes ${symbol} in all blocks.
 *   3. Defer peers block load until hero resolves (sector derivation).
 *   4. Wire simulate-this links to lab.html?symbol=<symbol>.
 */

'use strict';

(function () {

  // ── 1. Resolve symbol ────────────────────────────────────────────────────────
  /**
   * _resolveSymbol()
   * Returns the current stock symbol from:
   *   1. ?symbol=X URL query param (highest priority)
   *   2. <main data-symbol="..."> attribute
   *   3. Fallback: 'HDFCBANK'
   * @returns {string}
   */
  function _resolveSymbol() {
    try {
      var urlParams = new URLSearchParams(window.location.search);
      var urlSymbol = urlParams.get('symbol');
      if (urlSymbol) return urlSymbol.trim().toUpperCase();
    } catch (_) {
      // URLSearchParams not supported — fall through
    }

    var mainEl = document.querySelector('main[data-symbol]');
    if (mainEl && mainEl.dataset.symbol) return mainEl.dataset.symbol.trim().toUpperCase();

    return 'HDFCBANK';
  }

  var stockSymbol = _resolveSymbol();

  // Publish immediately so atlas-data.js substitutes ${symbol} correctly
  window.__stockSymbol = stockSymbol;

  // ── 2. Peers deferred load (requires sector from hero response) ───────────────
  /**
   * _deferPeersLoad()
   * Removes data-endpoint from the real peers block before _autoLoad runs,
   * then restores it and fires loadBlock() after hero settles.
   *
   * The real peers block is identified by [data-block="peers"]:not([aria-hidden]).
   * The void sentinel peers (aria-hidden="true") is left unaffected.
   */
  function _deferPeersLoad() {
    var peersEl = document.querySelector('[data-block="peers"]:not([aria-hidden])');
    var heroEl  = document.querySelector('[data-block="hero"]:not([aria-hidden])');

    if (!peersEl || !heroEl) return;

    var savedEndpoint = peersEl.getAttribute('data-endpoint');
    if (!savedEndpoint) return;

    // Remove endpoint so _autoLoad skips peers
    peersEl.removeAttribute('data-endpoint');

    // Watch hero state; reload peers once hero settles
    var observer = new MutationObserver(function (mutations) {
      for (var i = 0; i < mutations.length; i++) {
        if (mutations[i].attributeName === 'data-state') {
          var heroState = heroEl.getAttribute('data-state');
          var settled = heroState === 'ready' || heroState === 'stale' ||
                        heroState === 'empty' || heroState === 'error';
          if (settled) {
            observer.disconnect();
            // Restore endpoint and trigger load
            peersEl.setAttribute('data-endpoint', savedEndpoint);
            if (typeof window.loadBlock === 'function') {
              window.loadBlock(peersEl);
            }
            return;
          }
        }
      }
    });
    observer.observe(heroEl, { attributes: true, attributeFilter: ['data-state'] });
  }

  // ── 3. Wire simulate-this links ───────────────────────────────────────────────
  /**
   * _wireSimulateLinks()
   * Sets href on [data-action="simulate-this"] elements and any inline
   * "Open Simulation Lab" links inside signal-playback compact.
   */
  function _wireSimulateLinks() {
    var labHref = 'lab.html?symbol=' + encodeURIComponent(stockSymbol);

    var actionLinks = document.querySelectorAll('[data-action="simulate-this"]');
    actionLinks.forEach(function (el) {
      el.setAttribute('href', labHref);
    });

    // Inline lab link inside signal-playback compact
    var playbackLinks = document.querySelectorAll(
      '[data-component="signal-playback"] a[href^="lab.html"]'
    );
    playbackLinks.forEach(function (el) {
      el.setAttribute('href', labHref);
    });
  }

  // ── Init — synchronous (before DOMContentLoaded) ─────────────────────────────
  //
  // _deferPeersLoad() must run synchronously so peers endpoint is removed before
  // atlas-data.js's _autoLoad fires at DOMContentLoaded.
  _deferPeersLoad();

  // DOM-dependent wiring deferred to DOMContentLoaded
  function _onReady() {
    _wireSimulateLinks();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', _onReady);
  } else {
    _onReady();
  }

  // Expose for testing / manual reload
  window.__stockSymbol = stockSymbol;
  window.reloadSymbolBlocks = function () {
    var blocks = document.querySelectorAll('[data-endpoint]');
    blocks.forEach(function (el) {
      var rawEndpoint = el.getAttribute('data-endpoint') || '';
      var rawParams   = el.getAttribute('data-params')   || '';
      if (rawEndpoint.indexOf('${symbol}') !== -1 || rawParams.indexOf('${symbol}') !== -1) {
        if (typeof window.loadBlock === 'function') window.loadBlock(el);
      }
    });
  };

})();
