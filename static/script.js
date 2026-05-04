document.addEventListener("DOMContentLoaded", () => {
  const themeBtn = document.getElementById('toggle-theme');
  const html = document.documentElement;
  const body = document.body;
  const dados = body?.dataset?.dados ? JSON.parse(body.dataset.dados) : [];

  // ── Pull-to-refresh (mobile) ──
  let pullStartY = 0;
  let pulling = false;
  document.addEventListener('touchstart', e => {
    if (window.scrollY === 0) { pullStartY = e.touches[0].clientY; pulling = true; }
  });
  document.addEventListener('touchmove', e => {
    if (!pulling) return;
    const diff = e.touches[0].clientY - pullStartY;
    if (diff > 120) { pulling = false; window.location.reload(); }
  });
  document.addEventListener('touchend', () => { pulling = false; });
  const savedTheme = localStorage.getItem('theme');
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  const avatarTrigger = document.getElementById('avatar-trigger');
  const avatarMenu = document.getElementById('avatar-menu');
  const editarPerfilBtn = document.getElementById('editar-perfil-btn');
  const modalPerfil = document.getElementById('modal-perfil');
  const fecharPerfilBtn = document.getElementById('fechar-perfil');
  const cancelarPerfilBtn = document.getElementById('cancelar-perfil');
  const formPerfil = document.getElementById('form-perfil');
  const salvarPerfilBtn = document.getElementById('salvar-perfil');
  const tableEmpty = document.getElementById('table-empty');
  const tabPanels = Array.from(document.querySelectorAll('[data-tab-panel]'));
  const topTabs = Array.from(document.querySelectorAll('.top-tab'));
  const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const initialTheme = savedTheme || (prefersDark ? 'dark' : 'light');

  html.setAttribute('data-theme', initialTheme);
  updateThemeButtonText(initialTheme);

  themeBtn?.addEventListener("click", () => {
    const currentTheme = html.getAttribute('data-theme');
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', nextTheme);
    localStorage.setItem('theme', nextTheme);
    updateThemeButtonText(nextTheme);
    renderCharts(nextTheme);
    renderSpendingLine(nextTheme);
  });

  function updateThemeButtonText(theme) {
    if (!themeBtn) return;
    themeBtn.innerText = theme === 'dark' ? '☀️' : '🌙';
    themeBtn.setAttribute('title', theme === 'dark' ? 'Ativar modo claro' : 'Ativar modo escuro');
    themeBtn.setAttribute('aria-pressed', theme === 'dark' ? 'true' : 'false');
  }

  function showToast(message, type = 'success') {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3200);
  }

  function getActiveTabName() {
    const current = topTabs.find(tab => tab.classList.contains('is-active'));
    const href = current?.getAttribute('href') || '';
    if (href.includes('/visao-geral')) return 'visao_geral';
    if (href.includes('/dashboard')) return 'dashboard';
    if (href.includes('/lancamentos')) return 'lancamentos';
    if (href.includes('/relatorios')) return 'relatorios';
    return 'visao_geral';
  }

  function applyTabPanels() {
    const active = getActiveTabName();
    tabPanels.forEach(panel => {
      const tokens = (panel.dataset.tabPanel || '').split(' ').filter(Boolean);
      panel.hidden = !tokens.includes(active);
    });
  }

  applyTabPanels();

  // Scroll hint for table wrapper
  const tableWrapper = document.querySelector('.table-wrapper');
  function checkTableScroll() {
    if (!tableWrapper) return;
    const hasScroll = tableWrapper.scrollWidth > tableWrapper.clientWidth + 2;
    const atEnd = tableWrapper.scrollLeft + tableWrapper.clientWidth >= tableWrapper.scrollWidth - 2;
    tableWrapper.classList.toggle('has-scroll', hasScroll && !atEnd);
  }
  tableWrapper?.addEventListener('scroll', checkTableScroll);
  window.addEventListener('resize', checkTableScroll);
  checkTableScroll();

  // Focus trap for modals
  function trapFocus(modalEl) {
    if (!modalEl) return;
    const focusable = modalEl.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])');
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    modalEl._trapHandler = function(e) {
      if (e.key !== 'Tab') return;
      if (e.shiftKey) {
        if (document.activeElement === first) { e.preventDefault(); last?.focus(); }
      } else {
        if (document.activeElement === last) { e.preventDefault(); first?.focus(); }
      }
    };
    modalEl.addEventListener('keydown', modalEl._trapHandler);
    first?.focus();
  }
  function releaseFocus(modalEl) {
    if (!modalEl?._trapHandler) return;
    modalEl.removeEventListener('keydown', modalEl._trapHandler);
  }

  // Patch modal open/close to use focus trap
  const allModals = document.querySelectorAll('.modal');
  const observer = new MutationObserver(mutations => {
    mutations.forEach(m => {
      if (m.type === 'attributes' && m.attributeName === 'class') {
        const el = m.target;
        if (el.classList.contains('is-open')) trapFocus(el);
        else releaseFocus(el);
      }
    });
  });
  allModals.forEach(modal => observer.observe(modal, { attributes: true }));

  // Gráfico resumo com Chart.js
  const entrada = Number(body?.dataset?.entrada || 0);
  const saida = Number(body?.dataset?.saida || 0);
  const saldo = Number(body?.dataset?.saldo || 0);
  const tiposEntrada = ['entrada', 'salario', 'recebimento'];
  const tiposSaida = ['saida', 'divida', 'conta'];

  const moedaBRL = value => Number(value || 0).toLocaleString('pt-BR', {
    style: 'currency',
    currency: 'BRL'
  });

  let chartResumoInstance = null;
  let chartCategoriaInstance = null;

  function renderCharts(theme) {
    if (typeof Chart === 'undefined') return;

    const resumoCanvas = document.getElementById('graficoResumo');
    const categoriaCanvas = document.getElementById('graficoCategoria');
    const isDark = theme === 'dark';

    const chartColors = {
      entrada: isDark ? '#30d158' : '#34c759',
      saida: isDark ? '#ff453a' : '#ff3b30',
      saldo: isDark ? '#0a84ff' : '#007aff',
      // Mapa fixo: cada categoria sempre tem a mesma cor
      categoriaMap: {
        'Moradia':           isDark ? '#0a84ff' : '#007aff',     // azul
        'Alimentação':       isDark ? '#ff9f0a' : '#ff9500',     // laranja
        'Transporte':        isDark ? '#64d2ff' : '#5ac8fa',     // ciano
        'Educação':          isDark ? '#bf5af2' : '#af52de',     // roxo
        'Lazer':             isDark ? '#ffd60a' : '#ffcc00',     // amarelo
        'Saúde':             isDark ? '#30d158' : '#34c759',     // verde
        'Cartão de Crédito': isDark ? '#ff375f' : '#ff2d55',     // rosa
        'Outros':            isDark ? '#8e8e93' : '#636366',     // cinza
      },
      fallback: isDark ? '#aeaeb2' : '#8e8e93',
      grid: isDark ? 'rgba(255, 255, 255, 0.06)' : 'rgba(0, 0, 0, 0.05)',
      text: isDark ? '#8e8e93' : '#636366'
    };

    function corCategoria(cat) {
      return chartColors.categoriaMap[cat] || chartColors.fallback;
    }

    if (chartResumoInstance) chartResumoInstance.destroy();
    if (chartCategoriaInstance) chartCategoriaInstance.destroy();

    if (resumoCanvas) {
      const totalSalario = dados
        .filter(item => item.tipo === 'salario')
        .reduce((acc, item) => acc + Number(item.valor || 0), 0);
      const totalEntradas = dados
        .filter(item => ['entrada', 'recebimento'].includes(item.tipo))
        .reduce((acc, item) => acc + Number(item.valor || 0), 0);
      const totalDespesas = dados
        .filter(item => item.tipo === 'conta')
        .reduce((acc, item) => acc + Number(item.valor || 0), 0);
      const totalGastos = dados
        .filter(item => ['saida', 'divida'].includes(item.tipo))
        .reduce((acc, item) => acc + Number(item.valor || 0), 0);

      const ctx = resumoCanvas.getContext('2d');
      chartResumoInstance = new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['Salário', 'Entradas', 'Despesas', 'Gastos'],
          datasets: [{
            label: 'Valores por operação',
            data: [totalSalario, totalEntradas, totalDespesas, totalGastos],
            backgroundColor: [
              chartColors.saldo,                          // Salário — azul
              chartColors.entrada,                        // Entradas — verde
              isDark ? '#ff9f0a' : '#ff9500',             // Despesas — laranja
              chartColors.saida                           // Gastos — vermelho
            ],
            borderRadius: 6,
            borderSkipped: false,
            maxBarThickness: 48,
            barPercentage: 0.6,
            categoryPercentage: 0.7
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { top: 4, bottom: 4, left: 0, right: 0 } },
          plugins: {
            legend: { display: false },
            tooltip: {
              backgroundColor: isDark ? 'rgba(44,44,48,0.92)' : 'rgba(255,255,255,0.92)',
              titleColor: isDark ? '#f5f5f7' : '#1c1c1e',
              bodyColor: isDark ? '#d1d1d6' : '#3a3a3c',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)',
              borderWidth: 0.5,
              cornerRadius: 8,
              padding: 10,
              bodyFont: { family: '-apple-system, BlinkMacSystemFont, sans-serif', size: 12 },
              callbacks: { label: context => moedaBRL(context.parsed.y) }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: chartColors.grid, drawBorder: false },
              border: { display: false },
              ticks: {
                color: chartColors.text,
                font: { size: 11, family: '-apple-system, BlinkMacSystemFont, sans-serif' },
                callback: value => moedaBRL(value),
                maxTicksLimit: 5
              }
            },
            x: {
              grid: { display: false },
              border: { display: false },
              ticks: {
                color: chartColors.text,
                font: { size: 11, family: '-apple-system, BlinkMacSystemFont, sans-serif' }
              }
            }
          }
        }
      });
    }

    if (categoriaCanvas) {
      const tiposSaidaSet = ['saida', 'divida', 'conta'];
      const catMap = {};
      dados.filter(item => tiposSaidaSet.includes(item.tipo)).forEach(item => {
        const cat = item.categoria || 'Outros';
        catMap[cat] = (catMap[cat] || 0) + Number(item.valor || 0);
      });

      const labels = Object.keys(catMap);
      const values = Object.values(catMap);
      const possuiDados = values.some(value => value > 0);

      if (possuiDados) {
        const ctxCat = categoriaCanvas.getContext('2d');
        chartCategoriaInstance = new Chart(ctxCat, {
          type: 'doughnut',
          data: {
            labels,
            datasets: [{
              data: values,
              backgroundColor: labels.map(cat => corCategoria(cat)),
              borderWidth: 0,
              borderRadius: 3,
              spacing: 2
            }]
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '62%',
            layout: { padding: { top: 8, bottom: 0, left: 8, right: 8 } },
            plugins: {
              legend: {
                position: 'bottom',
                labels: {
                  color: chartColors.text,
                  font: { size: 12, family: '-apple-system, BlinkMacSystemFont, sans-serif', weight: '500' },
                  padding: 14,
                  usePointStyle: true,
                  pointStyle: 'circle',
                  boxWidth: 10,
                  boxHeight: 10
                }
              },
              tooltip: {
                backgroundColor: isDark ? 'rgba(44,44,48,0.92)' : 'rgba(255,255,255,0.92)',
                titleColor: isDark ? '#f5f5f7' : '#1c1c1e',
                bodyColor: isDark ? '#d1d1d6' : '#3a3a3c',
                borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)',
                borderWidth: 0.5,
                cornerRadius: 8,
                padding: 10,
                bodyFont: { family: '-apple-system, BlinkMacSystemFont, sans-serif', size: 12 },
                callbacks: {
                  label: context => `${context.label}: ${moedaBRL(context.parsed)}`
                }
              }
            }
          }
        });
      }
    }
  }

  renderCharts(initialTheme);

  // ── Spending Line Chart ──
  let spendingChartInstance = null;

  async function renderSpendingLine(theme) {
    const canvas = document.getElementById('graficoSpending');
    if (!canvas) return;
    const isDark = theme === 'dark';

    try {
      const res = await fetch('/api/spending-line');
      if (!res.ok) return;
      const data = await res.json();
      if (!data.pontos || data.pontos.length === 0) {
        canvas.parentElement.style.display = 'none';
        return;
      }

      if (spendingChartInstance) spendingChartInstance.destroy();

      const labels = data.pontos.map(p => {
        const parts = p.data.split('-');
        return `${parts[2]}/${parts[1]}`;
      });
      const gastos = data.pontos.map(p => p.gasto_acumulado);
      const orcLimite = data.orcamento_total;

      const ctx = canvas.getContext('2d');
      const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height || 200);
      gradient.addColorStop(0, isDark ? 'rgba(255,69,58,0.25)' : 'rgba(255,59,48,0.15)');
      gradient.addColorStop(1, 'transparent');

      const datasets = [{
        label: 'Gastos acumulados',
        data: gastos,
        borderColor: isDark ? '#ff453a' : '#ff3b30',
        backgroundColor: gradient,
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointBackgroundColor: isDark ? '#ff453a' : '#ff3b30',
        borderWidth: 2
      }];

      if (orcLimite > 0) {
        datasets.push({
          label: 'Limite orçamento',
          data: Array(labels.length).fill(orcLimite),
          borderColor: isDark ? 'rgba(142,142,147,0.5)' : 'rgba(99,99,102,0.4)',
          borderDash: [6, 4],
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false
        });
      }

      spendingChartInstance = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          layout: { padding: { top: 4, bottom: 4 } },
          plugins: {
            legend: {
              display: orcLimite > 0,
              position: 'bottom',
              labels: {
                color: isDark ? '#8e8e93' : '#636366',
                font: { size: 11, family: '-apple-system, BlinkMacSystemFont, sans-serif' },
                usePointStyle: true, pointStyle: 'circle', boxWidth: 8, boxHeight: 8, padding: 12
              }
            },
            tooltip: {
              backgroundColor: isDark ? 'rgba(44,44,48,0.92)' : 'rgba(255,255,255,0.92)',
              titleColor: isDark ? '#f5f5f7' : '#1c1c1e',
              bodyColor: isDark ? '#d1d1d6' : '#3a3a3c',
              borderColor: isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.06)',
              borderWidth: 0.5, cornerRadius: 8, padding: 10,
              bodyFont: { family: '-apple-system, BlinkMacSystemFont, sans-serif', size: 12 },
              callbacks: { label: ctx => `${ctx.dataset.label}: ${moedaBRL(ctx.parsed.y)}` }
            }
          },
          scales: {
            y: {
              beginAtZero: true,
              grid: { color: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)', drawBorder: false },
              border: { display: false },
              ticks: { color: isDark ? '#8e8e93' : '#636366', font: { size: 11 }, callback: v => moedaBRL(v), maxTicksLimit: 5 }
            },
            x: {
              grid: { display: false }, border: { display: false },
              ticks: { color: isDark ? '#8e8e93' : '#636366', font: { size: 11 } }
            }
          }
        }
      });
    } catch (e) { /* silently fail */ }
  }

  renderSpendingLine(initialTheme);

  const tbody = document.getElementById('tabela-lancamentos-body');
  const rows = Array.from(tbody?.querySelectorAll('tr') || []);
  const searchInput = document.getElementById('busca-lancamentos');
  const countEl = document.getElementById('table-count');
  const paginationEl = document.getElementById('paginacao');
  const sortButtons = Array.from(document.querySelectorAll('.th-sort'));
  const filtroButtons = Array.from(document.querySelectorAll('.chip-filtro'));
  const pageSize = 10;
  let currentPage = 1;
  let currentSort = { key: 'data', dir: 'desc' };
  let currentPeriodo = 'todos';

  const parseDate = value => new Date(`${value}T00:00:00`);
  const formatDateBR = value => {
    if (!value) return '';
    const [y, m, d] = value.split('-');
    if (!y || !m || !d) return value;
    return `${d}/${m}/${y}`;
  };

  rows.forEach(row => {
    const dateCell = row.querySelector('.col-data');
    const vencCell = row.querySelector('.col-vencimento');
    if (dateCell) dateCell.textContent = formatDateBR((dateCell.textContent || '').trim());
    if (vencCell) vencCell.textContent = formatDateBR((vencCell.textContent || '').trim());
  });

  function filtrarPorPeriodo(row) {
    if (currentPeriodo === 'todos') return true;
    const dataRaw = row.dataset.data;
    if (!dataRaw) return true;
    const data = parseDate(dataRaw);
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);

    if (currentPeriodo === 'hoje') {
      return data.getTime() === hoje.getTime();
    }
    if (currentPeriodo === '7dias') {
      const inicio = new Date(hoje);
      inicio.setDate(hoje.getDate() - 6);
      return data >= inicio && data <= hoje;
    }
    if (currentPeriodo === 'mes') {
      return data.getMonth() === hoje.getMonth() && data.getFullYear() === hoje.getFullYear();
    }
    return true;
  }

  function aplicarTabela() {
    const termo = (searchInput?.value || '').trim().toLowerCase();
    const filtradas = rows.filter(row => {
      const descricao = (row.dataset.descricao || '').toLowerCase();
      const categoria = (row.dataset.categoria || '').toLowerCase();
      const textoMatch = !termo || descricao.includes(termo) || categoria.includes(termo);
      return textoMatch && filtrarPorPeriodo(row);
    });

    filtradas.sort((a, b) => {
      let av = a.dataset[currentSort.key] || '';
      let bv = b.dataset[currentSort.key] || '';
      if (currentSort.key === 'valor') {
        av = Number(av);
        bv = Number(bv);
      }
      if (currentSort.key === 'data') {
        av = parseDate(av).getTime();
        bv = parseDate(bv).getTime();
      }
      if (av < bv) return currentSort.dir === 'asc' ? -1 : 1;
      if (av > bv) return currentSort.dir === 'asc' ? 1 : -1;
      return 0;
    });

    const total = filtradas.length;
    const pages = Math.max(1, Math.ceil(total / pageSize));
    if (currentPage > pages) currentPage = 1;
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;

    rows.forEach(r => { r.style.display = 'none'; });
    filtradas.slice(start, end).forEach(r => { r.style.display = ''; });

    if (countEl) {
      countEl.textContent = `${total} lançamento(s) encontrado(s)`;
    }

    if (tableEmpty) {
      tableEmpty.hidden = total !== 0;
    }

    if (paginationEl) {
      paginationEl.innerHTML = '';
      for (let p = 1; p <= pages; p += 1) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = String(p);
        if (p === currentPage) btn.classList.add('is-active');
        btn.addEventListener('click', () => {
          currentPage = p;
          aplicarTabela();
        });
        paginationEl.appendChild(btn);
      }
    }
  }

  searchInput?.addEventListener('input', () => {
    currentPage = 1;
    aplicarTabela();
  });

  sortButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.sort;
      if (!key) return;
      if (currentSort.key === key) {
        currentSort.dir = currentSort.dir === 'asc' ? 'desc' : 'asc';
      } else {
        currentSort = { key, dir: 'asc' };
      }
      aplicarTabela();
    });
  });

  filtroButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      currentPeriodo = btn.dataset.periodo || 'todos';
      filtroButtons.forEach(b => b.classList.remove('is-active'));
      btn.classList.add('is-active');
      currentPage = 1;
      aplicarTabela();
    });
  });

  const defaultFilter = filtroButtons.find(btn => btn.dataset.periodo === 'todos');
  defaultFilter?.classList.add('is-active');
  aplicarTabela();

  function closePerfilModal() {
    if (!modalPerfil) return;
    modalPerfil.classList.remove('is-open');
    modalPerfil.setAttribute('aria-hidden', 'true');
  }

  function openPerfilModal() {
    if (!modalPerfil) return;
    modalPerfil.classList.add('is-open');
    modalPerfil.setAttribute('aria-hidden', 'false');
  }

  avatarTrigger?.addEventListener('click', () => {
    const expanded = avatarTrigger.getAttribute('aria-expanded') === 'true';
    avatarTrigger.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    if (avatarMenu) avatarMenu.hidden = expanded;
  });

  document.addEventListener('click', event => {
    if (!avatarTrigger || !avatarMenu) return;
    if (!avatarTrigger.contains(event.target) && !avatarMenu.contains(event.target)) {
      avatarMenu.hidden = true;
      avatarTrigger.setAttribute('aria-expanded', 'false');
    }
  });

  editarPerfilBtn?.addEventListener('click', () => {
    if (avatarMenu) avatarMenu.hidden = true;
    if (avatarTrigger) avatarTrigger.setAttribute('aria-expanded', 'false');
    openPerfilModal();
  });

  fecharPerfilBtn?.addEventListener('click', closePerfilModal);
  cancelarPerfilBtn?.addEventListener('click', closePerfilModal);
  document.querySelectorAll('[data-close-perfil="true"]').forEach(el => {
    el.addEventListener('click', closePerfilModal);
  });

  formPerfil?.addEventListener('submit', async event => {
    event.preventDefault();
    if (!formPerfil) return;

    salvarPerfilBtn.disabled = true;
    salvarPerfilBtn.textContent = 'Salvando...';

    const formData = new FormData(formPerfil);
    const res = await fetch('/perfil', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken },
      body: formData
    });

    if (res.ok) {
      showToast('Perfil atualizado com sucesso.', 'success');
      window.location.reload();
      return;
    }

    const data = await res.json().catch(() => ({}));
    showToast(data.erro || 'Erro ao salvar perfil.', 'error');
    salvarPerfilBtn.disabled = false;
    salvarPerfilBtn.textContent = 'Salvar perfil';
  });

  document.getElementById('logout-btn')?.addEventListener('click', async () => {
    const res = await fetch('/logout', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken }
    });
    if (res.ok) {
      showToast('Sessão encerrada com sucesso.', 'success');
      window.location.href = '/login';
      return;
    }
    showToast('Não foi possível sair da conta.', 'error');
  });

  // ── Orçamentos ──
  function openModal(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.add('is-open');
    m.setAttribute('aria-hidden', 'false');
  }
  function closeModalById(id) {
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.remove('is-open');
    m.setAttribute('aria-hidden', 'true');
  }

  document.getElementById('btn-novo-orcamento')?.addEventListener('click', () => openModal('modal-orcamento'));
  document.querySelectorAll('.fechar-orcamento, [data-close-orcamento]').forEach(el => el.addEventListener('click', () => closeModalById('modal-orcamento')));

  document.getElementById('form-orcamento')?.addEventListener('submit', async e => {
    e.preventDefault();
    const mesAtual = new Date().toISOString().slice(0, 7);
    const res = await fetch('/orcamento', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({
        categoria: document.getElementById('orc-categoria').value,
        limite: parseFloat(document.getElementById('orc-limite').value),
        mes: mesAtual
      })
    });
    if (res.ok) {
      showToast('Orçamento salvo.', 'success');
      setTimeout(() => location.reload(), 500);
    } else {
      const d = await res.json().catch(() => ({}));
      showToast(d.erro || 'Erro ao salvar orçamento.', 'error');
    }
  });

  document.querySelectorAll('.excluir-orcamento').forEach(btn => {
    btn.addEventListener('click', async () => {
      const res = await fetch(`/orcamento/${btn.dataset.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } });
      if (res.ok) { showToast('Orçamento removido.', 'success'); setTimeout(() => location.reload(), 500); }
    });
  });

  // ── Metas ──
  document.getElementById('btn-nova-meta')?.addEventListener('click', () => openModal('modal-meta'));
  document.querySelectorAll('.fechar-meta, [data-close-meta]').forEach(el => el.addEventListener('click', () => closeModalById('modal-meta')));

  document.getElementById('form-meta')?.addEventListener('submit', async e => {
    e.preventDefault();
    const res = await fetch('/meta', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({
        nome: document.getElementById('meta-nome').value,
        emoji: document.getElementById('meta-emoji').value || '🎯',
        valor_alvo: parseFloat(document.getElementById('meta-valor').value),
        prazo: document.getElementById('meta-prazo').value
      })
    });
    if (res.ok) {
      showToast('Meta criada.', 'success');
      setTimeout(() => location.reload(), 500);
    } else {
      const d = await res.json().catch(() => ({}));
      showToast(d.erro || 'Erro ao criar meta.', 'error');
    }
  });

  document.querySelectorAll('.excluir-meta').forEach(btn => {
    btn.addEventListener('click', async () => {
      const res = await fetch(`/meta/${btn.dataset.id}`, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } });
      if (res.ok) { showToast('Meta removida.', 'success'); setTimeout(() => location.reload(), 500); }
    });
  });

  // ── Depósito em meta ──
  document.querySelectorAll('.botao-deposito').forEach(btn => {
    btn.addEventListener('click', () => {
      document.getElementById('deposito-meta-id').value = btn.dataset.id;
      openModal('modal-deposito');
    });
  });
  document.querySelectorAll('.fechar-deposito, [data-close-deposito]').forEach(el => el.addEventListener('click', () => closeModalById('modal-deposito')));

  document.getElementById('form-deposito')?.addEventListener('submit', async e => {
    e.preventDefault();
    const id = document.getElementById('deposito-meta-id').value;
    const valor = parseFloat(document.getElementById('deposito-valor').value);
    const res = await fetch(`/meta/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
      body: JSON.stringify({ valor_deposito: valor })
    });
    if (res.ok) {
      showToast('Depósito realizado!', 'success');
      setTimeout(() => location.reload(), 500);
    } else {
      const d = await res.json().catch(() => ({}));
      showToast(d.erro || 'Erro ao depositar.', 'error');
    }
  });

  // ── Gerar recorrentes (botão automático no load do dashboard) ──
  if (getActiveTabName() === 'dashboard') {
    fetch('/gerar-recorrentes', {
      method: 'POST',
      headers: { 'X-CSRF-Token': csrfToken }
    }).catch(() => {});

    // Carregar insights
    fetch('/api/insights').then(r => r.json()).then(data => {
      const el = document.getElementById('insights-list');
      if (!el) return;
      if (!data.insights || data.insights.length === 0) {
        el.innerHTML = '<p class="empty-hint">Adicione mais lançamentos para gerar insights.</p>';
        return;
      }
      el.innerHTML = data.insights.map(i =>
        `<div class="insight-item" data-tipo="${i.tipo}"><span class="insight-icon">${i.icone}</span><span>${i.mensagem}</span></div>`
      ).join('');
    }).catch(() => {});

    // Carregar projeção
    fetch('/api/projecao').then(r => r.json()).then(data => {
      const el = document.getElementById('projecao-content');
      if (!el) return;
      const fmt = v => Number(v).toLocaleString('pt-BR', {style:'currency',currency:'BRL'});
      const corSaldo = data.saldo_projetado >= 0 ? 'var(--color-green)' : 'var(--color-red)';
      el.innerHTML = `<div class="projecao-grid">
        <div class="projecao-item"><div class="projecao-label">Entradas</div><div class="projecao-valor" style="color:var(--color-green)">${fmt(data.entradas)}</div></div>
        <div class="projecao-item"><div class="projecao-label">Gastos até hoje</div><div class="projecao-valor" style="color:var(--color-red)">${fmt(data.saidas_ate_agora)}</div></div>
        <div class="projecao-item"><div class="projecao-label">Gasto/dia</div><div class="projecao-valor">${fmt(data.gasto_diario_medio)}</div></div>
        <div class="projecao-item"><div class="projecao-label">Recorrentes pendentes</div><div class="projecao-valor">${fmt(data.recorrentes_pendentes)}</div></div>
        <div class="projecao-item"><div class="projecao-label">Projeção gastos</div><div class="projecao-valor" style="color:var(--color-orange)">${fmt(data.projecao_gastos)}</div></div>
        <div class="projecao-item"><div class="projecao-label">Saldo projetado</div><div class="projecao-valor" style="color:${corSaldo}">${fmt(data.saldo_projetado)}</div></div>
      </div><p class="empty-hint" style="margin-top:0.5rem">${data.dias_restantes} dias restantes no mês</p>`;
    }).catch(() => {});
  }

  // ── PWA Service Worker ──
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/static/sw.js').catch(() => {});
  }

  // ── Pluggy Open Finance ──
  document.getElementById('btn-conectar-banco')?.addEventListener('click', async () => {
    try {
      const res = await fetch('/api/pluggy/connect-token', {
        method: 'POST',
        headers: { 'X-CSRF-Token': csrfToken }
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        showToast(d.erro || 'Erro ao iniciar conexão.', 'error');
        return;
      }
      const { accessToken } = await res.json();
      if (!accessToken) {
        showToast('Token não gerado.', 'error');
        return;
      }

      if (typeof PluggyConnect === 'undefined') {
        showToast('Carregando widget Pluggy...', 'success');
        await new Promise(r => setTimeout(r, 2000));
      }

      if (typeof PluggyConnect === 'undefined') {
        showToast('Widget Pluggy não carregou. Recarregue a página.', 'error');
        return;
      }

      const pluggy = new PluggyConnect({
        connectToken: accessToken,
        includeSandbox: true,
        onSuccess: async (data) => {
          const item = data?.item || data;
          await fetch('/api/pluggy/item-connected', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
            body: JSON.stringify({
              itemId: item.id,
              connectorName: item.connector?.name || 'Banco'
            })
          });
          showToast('Banco conectado! Sincronizando...', 'success');
          const sync = await fetch('/api/pluggy/sincronizar', {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrfToken }
          });
          if (sync.ok) {
            const d = await sync.json();
            showToast(`${d.importados} transações importadas.`, 'success');
          }
          setTimeout(() => location.reload(), 1500);
        },
        onError: (err) => {
          console.error('Pluggy error:', err);
          showToast('Erro na conexão com o banco.', 'error');
        }
      });
      pluggy.init();
    } catch (e) {
      console.error('Pluggy init error:', e);
      showToast('Erro ao conectar banco.', 'error');
    }
  });

  // Carregar conexões existentes
  async function loadConexoes() {
    const container = document.getElementById('conexoes-list');
    if (!container) return;
    try {
      const res = await fetch('/api/pluggy/conexoes');
      if (!res.ok) return;
      const conexoes = await res.json();
      if (conexoes.length === 0) {
        container.innerHTML = '<p class="empty-hint">Nenhum banco conectado ainda.</p>';
        return;
      }
      container.innerHTML = conexoes.map(c => `
        <div class="assinatura-item">
          <span class="assinatura-emoji">🏦</span>
          <span class="assinatura-desc">${c.connector_name || 'Banco'}</span>
          <span style="color:var(--text-quaternary);font-size:0.75rem;">${c.atualizado_em ? 'Sync: ' + c.atualizado_em.slice(0,10) : 'Pendente'}</span>
          <button class="excluir-orcamento" onclick="removeConexao(${c.id})" aria-label="Remover">✕</button>
        </div>
      `).join('');
    } catch (e) {}
  }

  window.removeConexao = async function(id) {
    await fetch('/api/pluggy/conexoes/' + id, { method: 'DELETE', headers: { 'X-CSRF-Token': csrfToken } });
    showToast('Conexão removida.', 'success');
    loadConexoes();
  };

  loadConexoes();

  // ── Push Notifications ──
  async function initPush() {
    if (!('serviceWorker' in navigator) || !('PushManager' in window)) return;
    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    if (existing) return; // já inscrito

    // Pedir permissão após 5s na página
    setTimeout(async () => {
      const perm = await Notification.requestPermission();
      if (perm !== 'granted') return;

      const res = await fetch('/api/push/vapid-key');
      if (!res.ok) return;
      const { publicKey } = await res.json();

      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey)
      });

      await fetch('/api/push/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrfToken },
        body: JSON.stringify({ subscription: sub.toJSON() })
      });
    }, 5000);
  }

  function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const raw = atob(base64);
    return Uint8Array.from([...raw].map(c => c.charCodeAt(0)));
  }

  initPush();
});
