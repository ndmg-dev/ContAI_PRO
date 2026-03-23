(() => {
  // Only on conciliacao page
  if (!document.querySelector('[id^="row-"]')) return;

  function setRowDone(id, color) {
    const row = document.getElementById('row-' + id);
    if (!row) return;
    row.style.opacity = '0.35';
    row.style.background = color;
    row.querySelectorAll('button').forEach((b) => (b.disabled = true));
    setTimeout(() => {
      row.style.transition = 'max-height 0.4s, padding 0.4s';
      row.style.maxHeight = '0';
      row.style.overflow = 'hidden';
      setTimeout(() => row.remove(), 400);
    }, 800);
  }

  async function resolver(id, btn) {
    btn.disabled = true;
    btn.textContent = '...';
    try {
      const res = await window.csrfFetch(`/conciliacao/resolver/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const payload = await res.json().catch(() => null);
      if (res.ok && payload?.ok) setRowDone(id, 'rgba(76,175,125,0.06)');
      else {
        btn.disabled = false;
        btn.textContent = '✓ Confirmar';
        alert('Erro ao confirmar: ' + (payload?.message || 'Falha desconhecida'));
      }
    } catch (e) {
      btn.disabled = false;
      btn.textContent = '✓ Confirmar';
      alert('Erro de rede: ' + e.message);
    }
  }

  async function excecao(id, btn) {
    const motivo = prompt('Motivo da exceção (deixe em branco para "Sem correspondência"):') ?? '';
    btn.disabled = true;
    btn.textContent = '...';
    try {
      const res = await window.csrfFetch(`/conciliacao/excecao/${id}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ motivo: motivo || 'Sem correspondência identificada' }),
      });
      const payload = await res.json().catch(() => null);
      if (res.ok && payload?.ok) setRowDone(id, 'rgba(224,82,82,0.06)');
      else {
        btn.disabled = false;
        btn.textContent = '✕ Exceção';
        alert('Erro ao marcar exceção: ' + (payload?.message || 'Falha desconhecida'));
      }
    } catch (e) {
      btn.disabled = false;
      btn.textContent = '✕ Exceção';
      alert('Erro de rede: ' + e.message);
    }
  }

  window.resolver = resolver; // used by onclick attributes
  window.excecao = excecao;   // used by onclick attributes
})();

