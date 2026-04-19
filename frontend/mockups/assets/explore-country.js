/* explore-country.js — extracted from explore-country.html inline script (V2FE-3) */
(function () {
  'use strict';
  const anchors = document.querySelectorAll('.subbar__link[href^="#"]');
  const sections = Array.from(anchors).map(a => a.getAttribute('href').slice(1));
  const spy = () => {
    let active = sections[0];
    for (const id of sections) {
      const el = document.getElementById(id);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (r.top < 140) active = id;
    }
    anchors.forEach(a =>
      a.classList.toggle('subbar__link--active', a.getAttribute('href') === '#' + active)
    );
  };
  window.addEventListener('scroll', spy, { passive: true });
})();
