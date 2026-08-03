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

  function filteredRowsForContractualView() {
    if (typeof ROWS === 'undefined' || !Array.isArray(ROWS)) return null;
    if (typeof passes !== 'function') return ROWS.slice();
    return ROWS.filter(function (row) {
      return passes(row);
    });
  }

  /*
   * La vista contractual ahora parte del mismo universo filtrado que Resumen
   * y Explorador. El filtro propio de la pestaña se aplica después, como una
   * segunda capa, sin modificar la base ni los datos guardados.
   */
  const originalComputeLic = window.computeLic;
  if (typeof originalComputeLic === 'function') {
    window.computeLic = function () {
      const sourceRows = typeof ROWS !== 'undefined' ? ROWS : null;
      const filteredRows = filteredRowsForContractualView();
      try {
        if (filteredRows) ROWS = filteredRows;
        const result = originalComputeLic.apply(this, arguments);
        if (!result || !Array.isArray(result.rows)) return result;
        result.rows = result.rows.filter(function (row) {
          return !isOperationalPurchase(row);
        });
        return result;
      } finally {
        if (sourceRows) ROWS = sourceRows;
      }
    };
  }

  function setSidebarChecks(group, selectedValues) {
    const selected = new Set(selectedValues);
    document.querySelectorAll('input[data-g="' + group + '"]').forEach(function (checkbox) {
      checkbox.checked = selected.has(checkbox.value);
    });
  }

  function syncTopControlsFromSidebar() {
    if (typeof state === 'undefined' || typeof licState === 'undefined') return;

    const establishmentSelect = document.getElementById('lic-estab');
    const selectedEstablishments = Array.from(state.estabs || []);
    if (establishmentSelect) {
      if (selectedEstablishments.length === 1) {
        licState.estab = selectedEstablishments[0];
        establishmentSelect.value = selectedEstablishments[0];
      } else {
        licState.estab = 'all';
        establishmentSelect.value = 'all';
      }
    }

    const channelSelect = document.getElementById('lic-canal');
    const selectedChannels = Array.from(state.canales || []);
    if (channelSelect) {
      if (selectedChannels.length === 1) {
        const selected = selectedChannels[0];
        const excluded = EXCLUDED_CHANNELS.has(normalizeContractualValue(selected));
        licState.canal = excluded ? 'all' : selected;
        channelSelect.value = excluded ? 'all' : selected;
      } else {
        licState.canal = 'all';
        channelSelect.value = 'all';
      }
    }

    licState.page = 1;
    licState.sel = null;
  }

  function syncSidebarFromTopControl(kind, value) {
    if (typeof state === 'undefined') return;

    if (kind === 'establishment') {
      state.estabs.clear();
      if (value && value !== 'all') state.estabs.add(value);
      setSidebarChecks('e', state.estabs);
    } else if (kind === 'channel') {
      state.canales.clear();
      if (value && value !== 'all') state.canales.add(value);
      setSidebarChecks('c', state.canales);
    }

    state.page = 1;
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
    }

    const subtitle = Array.from(view.querySelectorAll('p, div')).find(function (node) {
      return (node.textContent || '').trim() === 'licitaciones / convenios distintos';
    });
    if (subtitle) {
      subtitle.textContent = 'licitaciones y convenios con seguimiento contractual';
    }
  }

  /*
   * doRefresh originalmente actualiza Resumen/Explorador, pero no vuelve a
   * renderizar Licitaciones. Esta envoltura incorpora esa actualización.
   */
  const originalDoRefresh = window.doRefresh;
  if (typeof originalDoRefresh === 'function') {
    window.doRefresh = function () {
      const result = originalDoRefresh.apply(this, arguments);
      if (typeof state !== 'undefined' && state.view === 'lic') {
        syncTopControlsFromSidebar();
        if (typeof window.renderLic === 'function') window.renderLic();
      }
      return result;
    };
  }

  document.addEventListener('DOMContentLoaded', function () {
    clarifyContractualView();

    const establishmentSelect = document.getElementById('lic-estab');
    if (establishmentSelect) {
      establishmentSelect.addEventListener('change', function (event) {
        syncSidebarFromTopControl('establishment', event.target.value);
      }, true);
    }

    const channelSelect = document.getElementById('lic-canal');
    if (channelSelect) {
      channelSelect.addEventListener('change', function (event) {
        syncSidebarFromTopControl('channel', event.target.value);
      }, true);
    }

    syncTopControlsFromSidebar();
    if (typeof state !== 'undefined' && state.view === 'lic' &&
        typeof window.renderLic === 'function') {
      window.renderLic();
    }
  });
})();
