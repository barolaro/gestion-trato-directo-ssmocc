(function () {
  'use strict';

  const EXCLUDED_CHANNELS = new Set([
    'COMPRA AGIL',
    'COTIZACION'
  ]);

  function normalizeContractualValue(value) {
    return String(value || '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .trim()
      .toUpperCase();
  }

  function isOperationalPurchase(row) {
    const channel = normalizeContractualValue(row && row.canal);
    const instrument = normalizeContractualValue(row && row.li);

    if (EXCLUDED_CHANNELS.has(channel)) return true;
    if (channel.includes('COMPRA AGIL') || channel.includes('COTIZACION')) {
      return true;
    }

    // Ejemplos cubiertos: 1641-1041-COT26, COT-2026, 1052-AG26 y AG-2026.
    return /(?:^|[-_\s])(COT|AG)(?:[-_\s]?\d{2,4})?(?:$|[-_\s])/.test(instrument);
  }

  const originalComputeLic = window.computeLic;
  if (typeof originalComputeLic === 'function') {
    window.computeLic = function () {
      const result = originalComputeLic.apply(this, arguments);
      if (!result || !Array.isArray(result.rows)) return result;
      result.rows = result.rows.filter(function (row) {
        return !isOperationalPurchase(row);
      });
      return result;
    };
  }

  function clarifyContractualView() {
    const view = document.getElementById('view-lic');
    if (!view) return;

    const headings = view.querySelectorAll('h1, h2, h3');
    headings.forEach(function (heading) {
      if (/instrumentos y su ejecuci[oó]n/i.test(heading.textContent || '')) {
        heading.textContent = 'Instrumentos contractuales y su ejecución';
      }
    });

    const channelSelect = document.getElementById('lic-canal');
    if (channelSelect) {
      Array.from(channelSelect.options).forEach(function (option) {
        const label = normalizeContractualValue(option.textContent);
        const value = normalizeContractualValue(option.value);
        if (
          EXCLUDED_CHANNELS.has(label) ||
          EXCLUDED_CHANNELS.has(value) ||
          label.includes('COMPRA AGIL') ||
          label.includes('COTIZACION')
        ) {
          option.remove();
        }
      });
      if (
        EXCLUDED_CHANNELS.has(normalizeContractualValue(channelSelect.value)) ||
        normalizeContractualValue(channelSelect.value).includes('COMPRA AGIL')
      ) {
        channelSelect.value = 'all';
      }
    }

    const subtitle = Array.from(view.querySelectorAll('p, div')).find(function (node) {
      return (node.textContent || '').trim() === 'licitaciones / convenios distintos';
    });
    if (subtitle) subtitle.textContent = 'licitaciones y convenios con seguimiento contractual';
  }

  document.addEventListener('DOMContentLoaded', function () {
    clarifyContractualView();
    if (typeof window.renderLic === 'function') window.renderLic();
  });
})();
