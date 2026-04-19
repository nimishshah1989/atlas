(function () {
  'use strict';

  // Read mstar_id from <main data-mstar-id="..."> or URL param
  var main = document.querySelector('main[data-mstar-id]');
  var urlParam = new URLSearchParams(window.location.search).get('id');
  window.__mfMstarId = urlParam || (main && main.dataset.mstarId) || 'ppfas-flexi-cap-direct-growth';

  // Category is derived from hero response and stored here for peer block deferral
  window.__mfCategory = window.__mfCategory || '';

  // After hero loads, extract category and reload peer block
  document.addEventListener('atlas:blockLoaded', function (ev) {
    var el = ev && ev.detail && ev.detail.element;
    if (!el) return;
    if (el.dataset.block === 'hero' && ev.detail.data && ev.detail.data.category) {
      window.__mfCategory = ev.detail.data.category;
      var peerEl = document.querySelector('[data-block="peers"]');
      if (peerEl && typeof window.loadBlock === 'function') {
        window.loadBlock(peerEl);
      }
    }
  });
})();
