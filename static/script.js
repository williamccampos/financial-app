// Transição de 
document.addEventListener("DOMContentLoaded", () => {
  const themeBtn = document.getElementById('toggle-theme');
  const html = document.documentElement;
  const savedTheme = localStorage.getItem('theme');

  // Aplica o tema salvo
  if (savedTheme) {
    html.setAttribute('data-theme', savedTheme);
    updateThemeButtonText(savedTheme);
  }

  themeBtn?.addEventListener("click", () => {
    const currentTheme = html.getAttribute('data-theme');
    const nextTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', nextTheme);
    localStorage.setItem('theme', nextTheme);
    updateThemeButtonText(nextTheme);
  });

  function updateThemeButtonText(theme) {
    if (!themeBtn) return;
    themeBtn.innerText = theme === 'dark' ? '☀️ Modo Claro' : '🌙 Modo Escuro';
  }

  // Gráfico resumo com Chart.js
  if (typeof entrada !== 'undefined' && typeof Chart !== 'undefined') {
    const canvas = document.getElementById('graficoResumo');
    if (canvas) {
      const ctx = canvas.getContext('2d');
      new Chart(ctx, {
        type: 'bar',
        data: {
          labels: ['Entradas', 'Saídas', 'Saldo'],
          datasets: [{
            label: 'Valores',
            data: [entrada, saida, saldo],
            backgroundColor: ['#34c759', '#ff3b30', '#007aff'],
            borderRadius: 8
          }]
        },
        options: {
          responsive: true,
          plugins: {
            legend: { display: false }
          },
          scales: {
            y: {
              beginAtZero: true,
              ticks: {
                callback: value => `R$ ${parseFloat(value).toFixed(2)}`
              }
            }
          }
        }
      });
    }
  }
});
