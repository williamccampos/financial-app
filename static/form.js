// form.js - Validação e envio do formulário com lógica de parcelas

document.addEventListener("DOMContentLoaded", () => {
  const form = document.querySelector("form.formulario");
  const categoriaSelect = document.getElementById("categoria");
  const parcelasContainer = document.getElementById("parcelas-container");

  // Mostrar/ocultar campo de parcelas conforme categoria
  categoriaSelect.addEventListener("change", () => {
    if (categoriaSelect.value === "divida") {
      parcelasContainer.style.display = "flex";
    } else {
      parcelasContainer.style.display = "none";
    }
  });

  // Submissão do formulário
  form.addEventListener("submit", async function (e) {
    e.preventDefault();

    const data = new FormData(form);
    const body = Object.fromEntries(data.entries());

    body.recorrente = data.get("recorrente") === "on";
    body.valor = parseFloat(body.valor);
    body.parcelas = parseInt(data.get("parcelas")) || 1;

    // Validação básica
    if (!body.data || !body.tipo || !body.descricao || isNaN(body.valor)) {
      alert("Preencha todos os campos obrigatórios.");
      return;
    }

    // Envio via fetch
    const res = await fetch("/lancamento", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body)
    });

    if (res.ok) {
      window.location.reload();
    } else {
      alert("Erro ao adicionar lançamento.");
    }
  });
});
