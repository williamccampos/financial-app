document.querySelectorAll(".excluir").forEach(btn => {
  btn.addEventListener("click", async () => {
    const id = btn.dataset.id;
    if (!confirm("Deseja realmente excluir este lançamento?")) return;

    const res = await fetch(`/excluir/${id}`, { method: "DELETE" });
    if (res.ok) {
      window.location.reload();
    } else {
      alert("Erro ao excluir lançamento.");
    }
  });
});

document.querySelectorAll(".editar").forEach(btn => {
  btn.addEventListener("click", () => {
    const id = btn.dataset.id;
    window.location.href = `/editar/${id}`;
  });
});