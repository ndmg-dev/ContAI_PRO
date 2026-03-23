(() => {
  const trigger = document.getElementById('empresaSelectorTrigger');
  const menu = document.getElementById('empresaDropdownMenu');
  const textSpan = document.getElementById('empresaSelectorText');
  if (!trigger || !menu) return;

  // Toggle Menu
  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    const isVisible = menu.style.display === 'flex';
    menu.style.display = isVisible ? 'none' : 'flex';
  });

  // Fecha menu clicando fora
  document.addEventListener('click', (e) => {
    if (!trigger.contains(e.target) && !menu.contains(e.target)) {
      menu.style.display = 'none';
    }
  });

  async function loadEmpresas() {
    try {
      const res = await fetch('/empresas/lista');
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      if (!payload?.ok) throw new Error(payload?.message || 'Falha ao carregar empresas');
      const empresas = payload?.data || [];
      
      menu.innerHTML = '';
      
      // Estilo global dos itens
      const itemStyle = "padding: 10px 14px; cursor: pointer; color: var(--text-primary); font-size: 0.85rem; border-bottom: 1px solid rgba(255,255,255,0.05); transition: background 0.2s; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;";
      
      // Botão "Nova Empresa" (Limpa sessão)
      const newOpt = document.createElement('div');
      newOpt.style.cssText = itemStyle + " color: var(--accent-gold); font-weight: 600;";
      newOpt.innerHTML = `<span style="display:flex; align-items:center; gap:6px;"><i data-lucide="plus-circle" style="width:16px; height:16px;"></i> Nova Empresa</span>`;
      newOpt.addEventListener('mouseenter', () => newOpt.style.background = 'rgba(212,172,107,0.1)');
      newOpt.addEventListener('mouseleave', () => newOpt.style.background = 'transparent');
      newOpt.addEventListener('click', () => clearEmpresa());
      menu.appendChild(newOpt);

      if (empresas.length === 0) {
        const empty = document.createElement('div');
        empty.style.cssText = "padding: 12px; color: var(--text-secondary); font-size: 0.8rem; text-align: center;";
        empty.textContent = "Nenhuma salva ainda.";
        menu.appendChild(empty);
      }

      empresas.forEach((e) => {
        const opt = document.createElement('div');
        opt.style.cssText = itemStyle;
        opt.textContent = e.nome;
        opt.addEventListener('mouseenter', () => opt.style.background = 'rgba(255,255,255,0.08)');
        opt.addEventListener('mouseleave', () => opt.style.background = 'transparent');
        opt.addEventListener('click', () => changeEmpresa(e.id));
        menu.appendChild(opt);
      });

      // Atualiza os novos ícones do Lucide instanciados dinamicamente
      if (typeof lucide !== 'undefined') {
        lucide.createIcons({ root: menu });
      }

    } catch (e) {
      console.error('Erro ao carregar empresas', e);
      menu.innerHTML = '<div style="padding: 12px; color: #ff4d4d; font-size: 0.8rem;">Erro ao carregar.</div>';
    }
  }

  async function changeEmpresa(id) {
    if (!id) return;
    try {
      const res = await window.csrfFetch(`/empresas/selecionar/${id}`, { method: 'POST' });
      const payload = await res.json().catch(() => null);
      if (res.ok && payload?.ok) {
        window.location.reload();
      } else {
        alert(payload?.message || 'Não foi possível trocar a empresa.');
      }
    } catch (e) {
      alert('Erro ao trocar empresa');
    }
  }

  async function clearEmpresa() {
    try {
      const res = await window.csrfFetch('/empresas/limpar', { method: 'POST' });
      if (res.ok) {
        // Limpa o chat visualmente antes de recarregar
        const chatEl = document.getElementById('chat-messages');
        if (chatEl) chatEl.innerHTML = '';
        // Redireciona para a página de Documentos (onde está o cadastro)
        window.location.href = '/documentos';
      }
    } catch (e) {
      alert('Erro ao limpar empresa ativa');
    }
  }

  document.addEventListener('DOMContentLoaded', loadEmpresas);
})();

