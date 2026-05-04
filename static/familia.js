document.addEventListener("DOMContentLoaded", () => {
  const section = document.getElementById('familia-section');
  if (!section) return;

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
  const membrosEl = document.getElementById('familia-membros');
  const resumoEl = document.getElementById('familia-resumo');
  const categoriasEl = document.getElementById('familia-categorias');
  const canvas = document.getElementById('graficoFamilia');
  let familiaChart = null;

  async function loadFamilia() {
    const [membrosRes, resumoRes, catRes] = await Promise.all([
      fetch('/api/familia/membros'),
      fetch('/api/familia/resumo'),
      fetch('/api/familia/gastos-categoria')
    ]);

    const membrosData = await membrosRes.json();
    const resumoData = await resumoRes.json();
    const catData = await catRes.json();

    renderMembros(membrosData);
    renderResumo(resumoData);
    renderCategorias(catData);
    renderChart(resumoData);
  }

  function renderMembros(data) {
    if (!data.membros || data.membros.length === 0) {
      membrosEl.innerHTML = `<div class="empty-state"><div class="empty-state-icon">👨‍👩‍👧‍👦</div><p>${data.msg || 'Nenhum membro familiar. Compartilhe com permissão "escrita" para criar sua família.'}</p></div>`;
      resumoEl.innerHTML = '';
      categoriasEl.innerHTML = '';
      canvas.style.display = 'none';
      return;
    }
    membrosEl.innerHTML = `<div class="familia-avatars">${data.membros.map(m =>
      `<div class="familia-avatar-item"><span class="avatar-fallback">${m.nome[0].toUpperCase()}</span><small>${m.nome}</small></div>`
    ).join('')}</div>`;
  }

  function renderResumo(data) {
    if (data.erro) return;
    resumoEl.innerHTML = `
      <div class="valor-boxes">
        <div class="valor-box">Entradas<br><strong style="color:var(--color-green)">R$ ${data.total_entradas?.toFixed(2) || '0.00'}</strong></div>
        <div class="valor-box">Saídas<br><strong style="color:var(--color-red)">R$ ${data.total_saidas?.toFixed(2) || '0.00'}</strong></div>
        <div class="valor-box">Saldo<br><strong>R$ ${data.saldo?.toFixed(2) || '0.00'}</strong></div>
        ${data.orcamento_familiar ? `<div class="valor-box">Orçamento<br><strong>R$ ${data.orcamento_familiar.toFixed(2)}</strong></div>` : ''}
      </div>
      <div class="familia-membros-gastos">
        <h3>Gastos por membro</h3>
        <div class="familia-membros-list">
          ${(data.por_membro || []).map(m => `
            <div class="familia-membro-row">
              <span class="familia-membro-nome">${m.nome}</span>
              <span class="familia-membro-valor text-red">- R$ ${m.saidas.toFixed(2)}</span>
              <span class="familia-membro-valor text-green">+ R$ ${m.entradas.toFixed(2)}</span>
            </div>
          `).join('')}
        </div>
      </div>`;
  }

  function renderCategorias(data) {
    if (data.erro || !data.categorias) return;
    categoriasEl.innerHTML = `
      <h3>Gastos por categoria</h3>
      <div class="familia-cat-list">
        ${data.categorias.map(c => `
          <div class="familia-cat-item">
            <div class="familia-cat-header">
              <span>${c.categoria}</span>
              <strong>R$ ${c.total.toFixed(2)}</strong>
            </div>
            <div class="familia-cat-membros">
              ${c.membros.map(m => `<small>${m.nome}: R$ ${m.valor.toFixed(2)}</small>`).join(' · ')}
            </div>
          </div>
        `).join('')}
      </div>`;
  }

  function renderChart(data) {
    if (data.erro || !data.por_membro || data.por_membro.length === 0) {
      canvas.style.display = 'none';
      return;
    }
    canvas.style.display = '';
    const theme = document.documentElement.getAttribute('data-theme');
    const textColor = theme === 'dark' ? '#f5f5f7' : '#1c1c1e';
    const gridColor = theme === 'dark' ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)';

    if (familiaChart) familiaChart.destroy();
    familiaChart = new Chart(canvas, {
      type: 'bar',
      data: {
        labels: data.por_membro.map(m => m.nome),
        datasets: [
          { label: 'Entradas', data: data.por_membro.map(m => m.entradas), backgroundColor: theme === 'dark' ? '#30d158' : '#34c759', borderRadius: 6 },
          { label: 'Saídas', data: data.por_membro.map(m => m.saidas), backgroundColor: theme === 'dark' ? '#ff453a' : '#ff3b30', borderRadius: 6 }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { labels: { color: textColor, font: { family: '-apple-system, BlinkMacSystemFont, SF Pro Display, Inter, sans-serif', weight: 600, size: 12 } } } },
        scales: {
          x: { ticks: { color: textColor, font: { size: 11 } }, grid: { color: gridColor } },
          y: { ticks: { color: textColor, font: { size: 11 }, callback: v => 'R$ ' + v }, grid: { color: gridColor } }
        }
      }
    });
  }

  loadFamilia();
});
