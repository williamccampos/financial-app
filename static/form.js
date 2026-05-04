// form.js - Validação e envio do formulário com lógica de parcelas

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form.formulario");
  if (!form) return;

  const categoriaSelect = document.getElementById("categoria");
  const parcelasContainer = document.getElementById("parcelas-container");
  const parcelasSelect = document.getElementById("parcelas");
  const tipoSelect = document.getElementById("tipo");
  const dataInput = document.getElementById("data");
  const vencimentoInput = document.getElementById("vencimento");
  const valorInput = document.getElementById("valor");
  const submitBtn = form.querySelector('.botao-principal');
  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';

  function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    if (!container) return;
    const toast = document.createElement("div");
    toast.className = `toast toast--${type}`;
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => toast.remove(), 3200);
  }

  function formatDateISO(date) {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  function applyConditionalFields() {
    const tipo = tipoSelect?.value;
    if (!vencimentoInput || !categoriaSelect) return;

    categoriaSelect.required = ["saida", "divida", "conta"].includes(tipo);

    const mostraVencimento = ["divida", "conta"].includes(tipo);
    vencimentoInput.closest(".campo-form").style.display = mostraVencimento ? "flex" : "none";
    if (!mostraVencimento) vencimentoInput.value = "";
  }

  function updateParcelasVisibility() {
    if (!categoriaSelect || !parcelasContainer || !parcelasSelect) return;
    const isCartao = categoriaSelect.value === "Cartão de Crédito";
    parcelasContainer.style.display = isCartao ? "flex" : "none";
    if (!isCartao) parcelasSelect.value = "1";
  }

  categoriaSelect?.addEventListener("change", updateParcelasVisibility);
  tipoSelect?.addEventListener("change", applyConditionalFields);

  if (dataInput && !dataInput.value) {
    dataInput.value = formatDateISO(new Date());
  }

  valorInput?.addEventListener("blur", () => {
    const value = Number(valorInput.value);
    if (!Number.isNaN(value) && value > 0) {
      valorInput.value = value.toFixed(2);
    }
  });

  updateParcelasVisibility();
  applyConditionalFields();

  // Sugestão automática de categoria por IA
  const descInput = document.getElementById("descricao");
  let sugestaoTimer = null;
  if (descInput && categoriaSelect) {
    const sugestaoEl = document.createElement("span");
    sugestaoEl.className = "sugestao-cat";
    descInput.closest(".campo-form")?.appendChild(sugestaoEl);

    descInput.addEventListener("input", () => {
      clearTimeout(sugestaoTimer);
      const val = descInput.value.trim();
      if (val.length < 3) { sugestaoEl.className = "sugestao-cat"; return; }
      sugestaoTimer = setTimeout(async () => {
        try {
          const res = await fetch(`/api/sugerir-categoria?descricao=${encodeURIComponent(val)}`);
          if (!res.ok) return;
          const data = await res.json();
          if (data.categoria && data.confianca > 0.5) {
            sugestaoEl.textContent = `💡 Sugestão: ${data.categoria} — clique para aplicar`;
            sugestaoEl.className = "sugestao-cat visible";
            sugestaoEl.onclick = () => {
              categoriaSelect.value = data.categoria;
              sugestaoEl.className = "sugestao-cat";
              updateParcelasVisibility();
            };
          } else {
            sugestaoEl.className = "sugestao-cat";
          }
        } catch (e) {}
      }, 400);
    });
  }

  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    const data = new FormData(form);
    const body = Object.fromEntries(data.entries());
    body.recorrente = data.get("recorrente") === "on";
    body.valor = parseFloat(body.valor);
    body.parcelas = parseInt(data.get("parcelas")) || 1;

    if (!body.data || !body.tipo || !body.descricao || isNaN(body.valor)) {
      showToast("Preencha todos os campos obrigatórios.", "error");
      return;
    }

    if (categoriaSelect?.required && !body.categoria) {
      showToast("Categoria é obrigatória para este tipo de lançamento.", "error");
      return;
    }

    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.textContent = 'Salvando...';
    }

    const res = await fetch("/lancamento", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken
      },
      body: JSON.stringify(body)
    });

    if (res.ok) {
      showToast("Lançamento salvo com sucesso.", "success");
      form.reset();
      if (dataInput) dataInput.value = formatDateISO(new Date());
      updateParcelasVisibility();
      applyConditionalFields();
      // Reload para atualizar dados (tabela, gráficos, resumo)
      setTimeout(() => window.location.reload(), 600);
    } else {
      const data = await res.json().catch(() => ({}));
      showToast(data.erro || "Erro ao adicionar lançamento.", "error");
    }

    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.textContent = 'Salvar lançamento';
    }
  });

  document.getElementById("fab-novo")?.addEventListener("click", () => {
    const lancamentosTab = document.querySelector('.top-tab[data-tab="lancamentos"]');
    if (lancamentosTab && !lancamentosTab.classList.contains('is-active')) {
      lancamentosTab.click();
      return;
    }
    form?.scrollIntoView({ behavior: "smooth", block: "start" });
    dataInput?.focus();
  });
});
