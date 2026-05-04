const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content') || '';
const bodyData = document.body?.dataset?.dados ? JSON.parse(document.body.dataset.dados) : [];

const modal = document.getElementById('modal-edicao');
const formEdicao = document.getElementById('form-edicao');
const btnFecharModal = document.getElementById('fechar-modal');
const btnCancelarEdicao = document.getElementById('cancelar-edicao');
const btnSalvarEdicao = document.getElementById('salvar-edicao');

const modalConfirm = document.getElementById('confirm-exclusao');
const btnFecharConfirm = document.getElementById('fechar-confirm');
const btnCancelarExclusao = document.getElementById('cancelar-exclusao');
const btnConfirmarExclusao = document.getElementById('confirmar-exclusao');
const confirmTexto = document.getElementById('confirm-texto');

const fields = {
  id: document.getElementById('edit-id'),
  data: document.getElementById('edit-data'),
  tipo: document.getElementById('edit-tipo'),
  descricao: document.getElementById('edit-descricao'),
  valor: document.getElementById('edit-valor'),
  categoria: document.getElementById('edit-categoria'),
  vencimento: document.getElementById('edit-vencimento'),
  parcelas: document.getElementById('edit-parcelas'),
  recorrente: document.getElementById('edit-recorrente'),
  parcelasContainer: document.getElementById('edit-parcelas-container')
};

function openModal() {
  if (!modal) return;
  modal.classList.add('is-open');
  modal.setAttribute('aria-hidden', 'false');
}

function closeModal() {
  if (!modal) return;
  modal.classList.remove('is-open');
  modal.setAttribute('aria-hidden', 'true');
}

function showToast(message, type = 'success', actionLabel = '', action = null) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast--${type}`;
  toast.textContent = message;

  if (actionLabel && typeof action === 'function') {
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = actionLabel;
    button.className = 'chip-filtro';
    button.style.marginLeft = '0.6rem';
    button.addEventListener('click', () => {
      action();
      toast.remove();
    });
    toast.appendChild(button);
  }

  container.appendChild(toast);
  setTimeout(() => toast.remove(), 4200);
}

function openConfirmModal() {
  if (!modalConfirm) return;
  modalConfirm.classList.add('is-open');
  modalConfirm.setAttribute('aria-hidden', 'false');
}

function closeConfirmModal() {
  if (!modalConfirm) return;
  modalConfirm.classList.remove('is-open');
  modalConfirm.setAttribute('aria-hidden', 'true');
}

function toggleParcelasEdicao() {
  if (!fields.categoria || !fields.parcelasContainer || !fields.parcelas) return;
  const isCartao = fields.categoria.value === 'Cartão de Crédito';
  fields.parcelasContainer.style.display = isCartao ? 'flex' : 'none';
  if (!isCartao) fields.parcelas.value = '1';
}

document.querySelectorAll('[data-close-modal="true"]').forEach(el => {
  el.addEventListener('click', closeModal);
});

document.querySelectorAll('[data-close-confirm="true"]').forEach(el => {
  el.addEventListener('click', closeConfirmModal);
});

btnFecharModal?.addEventListener('click', closeModal);
btnCancelarEdicao?.addEventListener('click', closeModal);
btnFecharConfirm?.addEventListener('click', closeConfirmModal);
btnCancelarExclusao?.addEventListener('click', closeConfirmModal);
fields.categoria?.addEventListener('change', toggleParcelasEdicao);

document.addEventListener('keydown', event => {
  if (event.key === 'Escape') {
    closeModal();
    closeConfirmModal();
  }
});

let idParaExcluir = null;
let ultimoExcluido = null;

document.querySelectorAll(".excluir").forEach(btn => {
  btn.addEventListener("click", async () => {
    const id = btn.dataset.id;
    const registro = bodyData.find(item => String(item.id) === String(id));
    idParaExcluir = id;
    ultimoExcluido = registro || null;
    if (confirmTexto && registro) {
      confirmTexto.textContent = `Excluir "${registro.descricao}" no valor de R$ ${Number(registro.valor || 0).toFixed(2)}?`;
    }
    openConfirmModal();
  });
});

btnConfirmarExclusao?.addEventListener('click', async () => {
  if (!idParaExcluir) return;
  const res = await fetch(`/excluir/${idParaExcluir}`, {
    method: 'DELETE',
    headers: { 'X-CSRF-Token': csrfToken }
  });

  if (res.ok) {
    closeConfirmModal();
    showToast('Lançamento excluído.', 'success', 'Desfazer', async () => {
      if (!ultimoExcluido) return;
      const payload = { ...ultimoExcluido };
      delete payload.id;
      const undoRes = await fetch('/lancamento', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRF-Token': csrfToken
        },
        body: JSON.stringify(payload)
      });
      if (undoRes.ok) {
        showToast('Exclusão desfeita com sucesso.', 'success');
        setTimeout(() => window.location.reload(), 500);
      }
    });
    setTimeout(() => window.location.reload(), 800);
  } else {
    const data = await res.json().catch(() => ({}));
    showToast(data.erro || 'Erro ao excluir lançamento.', 'error');
  }
});

document.querySelectorAll('.editar').forEach(btn => {
  btn.addEventListener('click', async () => {
    const id = btn.dataset.id;
    const currentRes = await fetch(`/editar/${id}`);
    if (!currentRes.ok) {
      alert('Não foi possível carregar o lançamento para edição.');
      return;
    }

    const atual = await currentRes.json();
    fields.id.value = atual.id || '';
    fields.data.value = (atual.data || '').slice(0, 10);
    fields.tipo.value = atual.tipo || 'entrada';
    fields.descricao.value = atual.descricao || '';
    fields.valor.value = Number(atual.valor || 0).toFixed(2);
    fields.categoria.value = atual.categoria || '';
    fields.vencimento.value = (atual.vencimento || '').slice(0, 10);
    fields.parcelas.value = String(atual.parcelas || 1);
    fields.recorrente.checked = Boolean(atual.recorrente);

    toggleParcelasEdicao();
    openModal();
    fields.descricao?.focus();
  });
});

formEdicao?.addEventListener('submit', async event => {
  event.preventDefault();

  if (btnSalvarEdicao) {
    btnSalvarEdicao.disabled = true;
    btnSalvarEdicao.textContent = 'Salvando...';
  }

  const id = fields.id.value;
  const payload = {
    data: fields.data.value,
    tipo: fields.tipo.value,
    descricao: fields.descricao.value.trim(),
    valor: Number(fields.valor.value),
    categoria: fields.categoria.value,
    vencimento: fields.vencimento.value,
    recorrente: fields.recorrente.checked,
    parcelas: Number(fields.parcelas.value || 1),
    parcela_atual: 1
  };

  if (!payload.data || !payload.tipo || !payload.descricao || Number.isNaN(payload.valor) || payload.valor <= 0) {
    showToast('Preencha os campos obrigatórios corretamente.', 'error');
    if (btnSalvarEdicao) {
      btnSalvarEdicao.disabled = false;
      btnSalvarEdicao.textContent = 'Salvar alterações';
    }
    return;
  }

  const res = await fetch(`/editar/${id}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-CSRF-Token': csrfToken
    },
    body: JSON.stringify(payload)
  });

  if (res.ok) {
    showToast('Lançamento atualizado.', 'success');
    setTimeout(() => window.location.reload(), 500);
  } else {
    const data = await res.json().catch(() => ({}));
    showToast(data.erro || 'Erro ao editar lançamento.', 'error');
  }

  if (btnSalvarEdicao) {
    btnSalvarEdicao.disabled = false;
    btnSalvarEdicao.textContent = 'Salvar alterações';
  }
});
