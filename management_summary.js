(function () {
  'use strict';

  const MANAGEMENT_ALERT_STATES = new Set([
    'CANCELADA',
    'NO ACEPTADA',
    'CANCELACION SOLICITADA'
  ]);

  function contextLabel() {
    const selected = [...state.estabs];
    if (!selected.length) return 'Red SSMOCC';
    if (selected.length === 1) return selected[0];
    return `${selected.length} establecimientos seleccionados`;
  }

  function metrics(rows) {
    let amount = 0;
    let tdAmount = 0;
    let alerts = 0;
    const orders = new Set();
    const providers = new Map();
    for (const row of rows) {
      if (!row.m) {
        amount += row.t || 0;
        if (row.c === 'TRATO DIRECTO') tdAmount += row.t || 0;
        if (row.pr) providers.set(row.pr, (providers.get(row.pr) || 0) + (row.t || 0));
      }
      if (MANAGEMENT_ALERT_STATES.has(row.s)) alerts++;
      if (row.oc) orders.add(`${row.e}|${row.oc}`);
    }
    const topProvider = [...providers.entries()].sort((a, b) => b[1] - a[1])[0];
    return {
      amount,
      tdAmount,
      tdShare: amount ? tdAmount / amount * 100 : 0,
      alerts,
      alertShare: rows.length ? alerts / rows.length * 100 : 0,
      orders: orders.size,
      topProvider: topProvider ? topProvider[0] : '',
      topProviderShare: topProvider && amount ? topProvider[1] / amount * 100 : 0
    };
  }

  function establishmentActions(rows) {
    const groups = new Map();
    for (const row of rows) {
      if (!groups.has(row.e)) groups.set(row.e, []);
      groups.get(row.e).push(row);
    }
    const actions = [];
    for (const [establishment, group] of groups) {
      const m = metrics(group);
      if (m.tdShare >= 20) {
        actions.push({priority: 3, establishment, finding: `TD representa ${m.tdShare.toFixed(1)}% del monto`, action: 'Revisar causales, respaldos y oportunidades de mecanismos competitivos.'});
      } else if (m.tdShare >= 16) {
        actions.push({priority: 2, establishment, finding: `TD representa ${m.tdShare.toFixed(1)}% del monto`, action: 'Mantener seguimiento y revisar las compras de mayor impacto.'});
      }
      if (m.alerts && m.alertShare >= 2) {
        actions.push({priority: m.alertShare >= 5 ? 3 : 2, establishment, finding: `${fmtNum(m.alerts)} registros cancelados o no aceptados`, action: 'Validar causas, estados y necesidad de depuración de los registros.'});
      }
      if (m.topProviderShare >= 35) {
        actions.push({priority: 1, establishment, finding: `Principal proveedor concentra ${m.topProviderShare.toFixed(1)}% del monto`, action: 'Revisar dependencia, vigencia contractual y alternativas disponibles.'});
      }
    }
    return actions.sort((a, b) => b.priority - a.priority || a.establishment.localeCompare(b.establishment)).slice(0, 6);
  }

  function installManagementPanels() {
    if (document.getElementById('management-overview')) return;
    const dashboard = document.getElementById('view-dash');
    const kpiGrid = dashboard?.querySelector('.grid.grid-cols-2');
    if (!dashboard || !kpiGrid) return;

    const section = document.createElement('div');
    section.id = 'management-overview';
    section.className = 'grid grid-cols-1 xl:grid-cols-5 gap-5';
    section.innerHTML = `
      <article class="xl:col-span-2 bg-white rounded-xl shadow-sm border border-slate-200 p-4">
        <div class="flex flex-wrap items-start justify-between gap-2">
          <div>
            <h2 class="font-tight font-extrabold text-[17px] text-slate-800"><i class="fa-solid fa-chart-line text-govblue mr-2"></i>Resumen ejecutivo</h2>
            <p class="text-[11px] text-slate-400 mt-0.5">Lectura automática de la selección actual</p>
          </div>
          <span id="management-context" class="text-[11px] font-bold text-govblue bg-blue-50 px-2.5 py-1 rounded-full">Red SSMOCC</span>
        </div>
        <p id="management-summary" class="mt-4 text-[13px] leading-relaxed text-slate-600">—</p>
        <div id="management-status" class="mt-4 grid grid-cols-2 gap-2"></div>
        <p class="mt-3 text-[10px] text-slate-400"><i class="fa-solid fa-circle-info mr-1"></i>Lectura preventiva para orientar la revisión; no acredita por sí sola incumplimientos.</p>
      </article>
      <article class="xl:col-span-3 bg-white rounded-xl shadow-sm border border-slate-200 p-4">
        <div class="flex flex-wrap items-start justify-between gap-2 mb-3">
          <div>
            <h2 class="font-tight font-extrabold text-[17px] text-slate-800"><i class="fa-solid fa-list-check text-govred mr-2"></i>Acciones prioritarias</h2>
            <p class="text-[11px] text-slate-400 mt-0.5">Hallazgos ordenados por criticidad dentro de la selección</p>
          </div>
          <span id="management-action-count" class="text-[11px] font-bold text-slate-500 bg-slate-100 px-2.5 py-1 rounded-full">—</span>
        </div>
        <div id="management-actions" class="space-y-2"></div>
      </article>`;
    kpiGrid.insertAdjacentElement('afterend', section);

    const labelMap = [
      ['k-rows', 'Líneas analizadas'],
      ['k-monto', 'Monto adjudicado'],
      ['k-avg', 'Promedio por línea'],
      ['k-oc', 'Órdenes de compra'],
      ['k-td', 'Monto vía TD'],
      ['k-alert', 'Registros por revisar']
    ];
    for (const [id, label] of labelMap) {
      const value = document.getElementById(id);
      const title = value?.previousElementSibling;
      if (title) {
        const icon = title.querySelector('i');
        title.textContent = label;
        if (icon) title.prepend(icon);
      }
    }
  }

  function statusCard(label, value, tone) {
    const tones = {
      red: 'bg-red-50 border-red-100 text-red-700',
      amber: 'bg-amber-50 border-amber-100 text-amber-700',
      green: 'bg-emerald-50 border-emerald-100 text-emerald-700',
      blue: 'bg-blue-50 border-blue-100 text-govblue'
    };
    return `<div class="rounded-lg border p-2.5 ${tones[tone]}"><div class="text-[9px] uppercase tracking-wide font-bold opacity-70">${label}</div><div class="text-[13px] font-extrabold mt-0.5">${value}</div></div>`;
  }

  function actionRow(item) {
    const style = item.priority === 3
      ? ['Alta', 'bg-red-50 text-red-700 border-red-100', 'bg-red-500']
      : item.priority === 2
        ? ['Media', 'bg-amber-50 text-amber-700 border-amber-100', 'bg-amber-500']
        : ['Preventiva', 'bg-blue-50 text-govblue border-blue-100', 'bg-blue-500'];
    return `<div class="relative rounded-lg border border-slate-100 bg-slate-50 p-3 pl-4 overflow-hidden">
      <span class="absolute left-0 top-0 bottom-0 w-1 ${style[2]}"></span>
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[9px] uppercase font-extrabold px-2 py-0.5 rounded-full border ${style[1]}">${style[0]}</span>
        <span class="text-[11px] font-extrabold text-slate-700">${item.establishment}</span>
        <span class="text-[11px] text-slate-600">${item.finding}</span>
      </div>
      <div class="text-[11px] text-slate-500 mt-1.5"><strong>Acción sugerida:</strong> ${item.action}</div>
    </div>`;
  }

  function renderManagementOverview(rows) {
    installManagementPanels();
    const summary = document.getElementById('management-summary');
    if (!summary) return;
    const m = metrics(rows);
    const context = contextLabel();
    document.getElementById('management-context').textContent = context;
    summary.innerHTML = `<strong>${context}</strong> registra <strong>${fmtNum(m.orders)} órdenes de compra</strong> por <strong>${fmtCLP(m.amount)}</strong>. El Trato Directo representa <strong>${m.tdShare.toFixed(1)}% del monto</strong> y existen <strong>${fmtNum(m.alerts)} registros</strong> cancelados o no aceptados que requieren validación.`;

    const tdTone = m.tdShare >= 20 ? 'red' : m.tdShare >= 16 ? 'amber' : 'green';
    const alertTone = m.alertShare >= 5 ? 'red' : m.alertShare >= 2 ? 'amber' : 'green';
    document.getElementById('management-status').innerHTML =
      statusCard('Participación TD', `${m.tdShare.toFixed(1)}% del monto`, tdTone) +
      statusCard('Registros por revisar', `${fmtNum(m.alerts)} · ${m.alertShare.toFixed(1)}%`, alertTone) +
      statusCard('Promedio por OC', m.orders ? fmtCLP(m.amount / m.orders) : 'Sin OC', 'blue') +
      statusCard('Concentración proveedor líder', m.topProvider ? `${m.topProviderShare.toFixed(1)}%` : 'Sin información', m.topProviderShare >= 35 ? 'amber' : 'green');

    const actions = establishmentActions(rows);
    document.getElementById('management-action-count').textContent = actions.length ? `${actions.length} señales` : 'Sin señales relevantes';
    document.getElementById('management-actions').innerHTML = actions.length
      ? actions.map(actionRow).join('')
      : `<div class="rounded-lg border border-emerald-100 bg-emerald-50 p-4 text-[12px] text-emerald-700"><i class="fa-solid fa-circle-check mr-2"></i>No se identifican señales prioritarias con los criterios preventivos actuales. Mantenga el seguimiento periódico.</div>`;
  }

  const originalRenderKPIs = renderKPIs;
  renderKPIs = function (rows) {
    originalRenderKPIs(rows);
    renderManagementOverview(rows);
  };

  installManagementPanels();
  if (typeof refresh === 'function') refresh();
})();
