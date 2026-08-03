(function () {
  'use strict';

  const trendView = {
    mode: 'monthly',
    selected: null,
    last: 0,
    amounts: [],
    orders: [],
    context: 'Red SSMOCC'
  };

  function cumulative(values) {
    let total = 0;
    return values.map(value => (total += Number(value || 0)));
  }

  function selectedContext() {
    const hospitals = [...state.estabs];
    return hospitals.length === 1 ? hospitals[0] : 'Red SSMOCC';
  }

  function installControls() {
    if (document.getElementById('trend-analysis-controls')) return;
    const canvasBox = document.getElementById('ch-trend')?.parentElement;
    if (!canvasBox) return;

    const description = canvasBox.parentElement.querySelector('h3 + p');
    if (description) {
      description.textContent = 'Gráfico completo para contexto y selección mensual para análisis';
    }

    const controls = document.createElement('div');
    controls.id = 'trend-analysis-controls';
    controls.className = 'mt-3 mb-2 rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 space-y-2';
    controls.innerHTML = `
      <div class="flex flex-wrap items-center gap-2">
        <span class="text-[10px] uppercase tracking-wide font-bold text-slate-500 w-24">Vista</span>
        <div class="inline-flex rounded-lg border border-slate-200 bg-white p-0.5">
          <button type="button" data-trend-mode="monthly" class="px-3 py-1.5 rounded-md text-[11px] font-bold">Mensual</button>
          <button type="button" data-trend-mode="cumulative" class="px-3 py-1.5 rounded-md text-[11px] font-bold">Acumulada</button>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-1.5">
        <span class="text-[10px] uppercase tracking-wide font-bold text-slate-500 w-24">Mes analizado</span>
        <div id="trend-month-buttons" class="flex flex-wrap gap-1.5"></div>
      </div>`;
    canvasBox.insertAdjacentElement('beforebegin', controls);

    controls.querySelectorAll('[data-trend-mode]').forEach(button => {
      button.addEventListener('click', () => {
        trendView.mode = button.dataset.trendMode;
        renderEnhancedTrend();
      });
    });
  }

  function syncControls() {
    installControls();
    document.querySelectorAll('[data-trend-mode]').forEach(button => {
      const active = button.dataset.trendMode === trendView.mode;
      button.className = 'px-3 py-1.5 rounded-md text-[11px] font-bold transition ' +
        (active ? 'bg-govblue text-white shadow-sm' : 'text-slate-500 hover:bg-slate-100');
      button.setAttribute('aria-pressed', String(active));
    });

    const holder = document.getElementById('trend-month-buttons');
    if (!holder) return;
    holder.innerHTML = MESES.slice(0, trendView.last + 1).map((month, index) => {
      const active = index === trendView.selected;
      return `<button type="button" data-trend-month="${index}" aria-pressed="${active}"
        class="px-2.5 py-1 rounded-full border text-[11px] font-bold transition ${
          active
            ? 'bg-blue-50 border-govblue text-govblue shadow-sm'
            : 'bg-white border-slate-200 text-slate-500 hover:border-blue-300'
        }">${month}</button>`;
    }).join('');
    holder.querySelectorAll('[data-trend-month]').forEach(button => {
      button.addEventListener('click', () => {
        trendView.selected = Number(button.dataset.trendMonth);
        renderEnhancedTrend();
      });
    });
  }

  function managementSignal(selected) {
    const amount = trendView.amounts[selected] || 0;
    const orders = trendView.orders[selected] || 0;
    const average = orders ? amount / orders : 0;
    const previousAmount = selected > 0 ? trendView.amounts[selected - 1] || 0 : 0;
    const previousOrders = selected > 0 ? trendView.orders[selected - 1] || 0 : 0;
    const previousAverage = previousOrders ? previousAmount / previousOrders : 0;
    const orderChange = previousOrders ? (orders - previousOrders) / previousOrders : 0;
    const averageChange = previousAverage ? (average - previousAverage) / previousAverage : 0;

    if (!orders) return {
      level: 'info', label: 'Sin actividad registrada',
      message: `No existen órdenes de compra registradas en ${MESES[selected]}. Verifique la cobertura de la carga antes de interpretar el período.`
    };
    if (!selected || !previousOrders) return {
      level: 'info', label: 'Período inicial',
      message: 'Aún no existe un mes anterior comparable. Este período será la base para el seguimiento de la gestión.'
    };
    if (orderChange >= .20 && averageChange <= -.20) return {
      level: 'high', label: 'Revisión prioritaria',
      message: 'Aumentaron las OC y disminuyó su monto promedio. Revise requerimientos repetidos y oportunidades de consolidación o mecanismos más competitivos.'
    };
    if (orderChange >= .10 && averageChange <= -.10) return {
      level: 'review', label: 'Revisar dispersión',
      message: 'Se observa un aumento de OC junto con una disminución de su valor promedio. Se recomienda revisar la planificación mensual.'
    };
    if (orderChange < 0 && averageChange > 0) return {
      level: 'stable', label: 'Mayor concentración',
      message: 'Disminuyó la cantidad de OC y aumentó su valor promedio. Verifique si responde a una mejor consolidación de requerimientos.'
    };
    return {
      level: 'stable', label: 'Actividad estable',
      message: 'La actividad mensual se mantiene sin una señal relevante de dispersión. Continúe monitoreando la planificación de compras.'
    };
  }

  function renderCards() {
    const selected = trendView.selected;
    const cumAmounts = cumulative(trendView.amounts);
    const cumOrders = cumulative(trendView.orders);
    const isCumulative = trendView.mode === 'cumulative';
    const amount = isCumulative ? cumAmounts[selected] : trendView.amounts[selected] || 0;
    const orders = isCumulative ? cumOrders[selected] : trendView.orders[selected] || 0;
    const average = orders ? amount / orders : 0;
    const month = MESES[selected];
    const signalData = managementSignal(selected);

    document.getElementById('trend-period').textContent = `${month} 2026 · ${trendView.context}`;
    const amountCard = document.getElementById('trend-amount');
    const ordersCard = document.getElementById('trend-orders');
    const averageCard = document.getElementById('trend-average');
    amountCard.previousElementSibling.textContent = isCumulative ? `Monto acumulado a ${month}` : `Monto de ${month}`;
    ordersCard.previousElementSibling.textContent = isCumulative ? `OC únicas acumuladas` : `OC únicas de ${month}`;
    averageCard.previousElementSibling.textContent = isCumulative ? `Promedio acumulado por OC` : `Promedio por OC de ${month}`;
    document.querySelector('#trend-signal-card > div:first-child').textContent = `Señal de ${month}`;
    amountCard.textContent = fmtCLP(amount);
    ordersCard.textContent = fmtNum(orders);
    averageCard.textContent = orders ? fmtCLP(average) : 'Sin OC';

    const card = document.getElementById('trend-signal-card');
    const signal = document.getElementById('trend-signal');
    card.className = 'rounded-lg border p-3 ' + (
      signalData.level === 'high' ? 'bg-red-50 border-red-200' :
      signalData.level === 'review' ? 'bg-amber-50 border-amber-200' :
      signalData.level === 'info' ? 'bg-blue-50 border-blue-200' :
      'bg-emerald-50 border-emerald-200'
    );
    signal.className = 'text-[14px] font-extrabold mt-1 ' + (
      signalData.level === 'high' ? 'text-red-700' :
      signalData.level === 'review' ? 'text-amber-700' :
      signalData.level === 'info' ? 'text-blue-700' : 'text-emerald-700'
    );
    signal.textContent = signalData.label;
    document.getElementById('trend-message').textContent =
      (isCumulative ? `Acumulado enero–${month}. ` : '') + signalData.message;
  }

  function renderChart() {
    const isCumulative = trendView.mode === 'cumulative';
    const amounts = isCumulative ? cumulative(trendView.amounts) : trendView.amounts;
    const orders = isCumulative ? cumulative(trendView.orders) : trendView.orders;
    paint('ch-trend', {
      type: 'line',
      data: {
        labels: MESES.slice(0, trendView.last + 1),
        datasets: [
          {
            label: isCumulative ? 'Monto acumulado (M CLP)' : 'Monto (M CLP)',
            data: amounts.map(value => value / 1e6), yAxisID: 'y',
            borderColor: '#0063af', backgroundColor: 'rgba(0,99,175,.10)',
            fill: true, tension: .35,
            pointRadius: amounts.map((_, index) => index === trendView.selected ? 6 : 3),
            pointBackgroundColor: '#0063af', borderWidth: 2.5
          },
          {
            label: isCumulative ? 'OC únicas acumuladas' : 'OC únicas',
            data: orders, yAxisID: 'y1', borderColor: '#e2242c',
            backgroundColor: 'transparent', borderDash: [5, 4], tension: .35,
            pointRadius: orders.map((_, index) => index === trendView.selected ? 6 : 3),
            pointBackgroundColor: '#e2242c', borderWidth: 2
          }
        ]
      },
      options: baseOpts({
        interaction: {mode: 'index', intersect: false},
        onClick: (event, elements) => {
          if (!elements.length) return;
          trendView.selected = elements[0].index;
          renderEnhancedTrend();
        },
        scales: {
          x: {grid: {display: false}, ticks: {font: {family: 'Inter', size: 11}, color: '#475569'}},
          y: {position: 'left', grid: {color: '#f1f5f9'}, ticks: {font: {family: 'Inter', size: 10}, color: '#0063af', callback: value => '$' + value + 'M'}},
          y1: {position: 'right', grid: {display: false}, ticks: {font: {family: 'Inter', size: 10}, color: '#e2242c'}}
        },
        plugins: {
          legend: {display: true, position: 'top', align: 'end', labels: {font: {family: 'Inter', size: 11}, usePointStyle: true, boxWidth: 8, padding: 14}},
          tooltip: {callbacks: {
            title: items => `${items[0].label} 2026 · clic para analizar`,
            label: context => context.datasetIndex === 0 ? ' ' + fmtCLP(context.raw * 1e6) : ' ' + fmtNum(context.raw) + ' OC únicas'
          }}
        }
      })
    });
  }

  function renderEnhancedTrend() {
    syncControls();
    renderChart();
    renderCards();
  }

  renderPurchaseManagementSignal = function (monthlyAmount, monthlyOrders, last) {
    trendView.amounts = monthlyAmount.slice(0, last + 1);
    trendView.orders = monthlyOrders.slice(0, last + 1);
    trendView.last = last;
    trendView.context = selectedContext();
    if (trendView.selected === null || trendView.selected > last) trendView.selected = last;
    renderEnhancedTrend();
  };

  installControls();
  if (typeof refresh === 'function') refresh();
})();
