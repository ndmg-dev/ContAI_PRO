(() => {
  const root = document.getElementById('global-chat');
  if (!root) return; // chat panel isn't rendered

  const messagesEl = document.getElementById('chat-messages');
  const inputEl = document.getElementById('chat-input');
  if (!messagesEl || !inputEl) return;

  const userName = root.getAttribute('data-user-name') || '';

  function appendMessage(text, side, isRaw = false) {
    const bubble = document.createElement('div');

    if (side === 'user') {
      bubble.style.cssText =
        'background:#2a2a2a; padding:12px 16px; border-radius:10px; font-size:0.88rem; line-height:1.5; align-self:flex-end; max-width:85%; word-break:break-word;';
      bubble.textContent = text;
    } else {
      bubble.style.cssText =
        'background:var(--bg-card); padding:12px 16px; border-radius:10px; font-size:0.88rem; line-height:1.6; border-left:3px solid var(--accent-gold); white-space:pre-wrap;';
      
      if (isRaw) {
        bubble.innerHTML = text;
      } else {
        // Parse simple markdown links: [text](url) -> <a href="url" target="_blank">text</a>
        const linkRegex = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
        const html = text.replace(linkRegex, (match, linkText, url) => {
          return `<a href="${url}" target="_blank" style="color:var(--accent-gold); text-decoration:underline; font-weight:600;">${linkText}</a>`;
        });
        bubble.innerHTML = html;
      }
    }

    messagesEl.appendChild(bubble);
    messagesEl.scrollTop = messagesEl.scrollHeight;
    return bubble;
  }

  async function loadChatHistory() {
    try {
      const res = await fetch('/chat/history');
      const payload = await res.json();
      const history = payload?.data || [];
      messagesEl.innerHTML = '';

      if (!Array.isArray(history) || history.length === 0) {
        // Verifica se há empresa ativa checando o texto do seletor no sidebar
        const selectorText = document.getElementById('empresaSelectorText');
        const noCompany = !selectorText || selectorText.textContent.trim() === 'Nenhuma Empresa';

        if (noCompany) {
          appendMessage(
            'Selecione uma empresa no menu lateral para ativar o assistente contábil.',
            'ai',
            false
          );
        } else {
          const safeName = userName ? userName.replace(/[<>]/g, '') : '';
          appendMessage(
            `Olá, <strong>${safeName}</strong>! Sou o <strong>ContAI</strong>, seu assistente contábil. Posso ajudar com conciliação bancária, NF-e, obrigações fiscais e muito mais. Como posso ajudar?`,
            'ai',
            true
          );
        }
        return;
      }

      history.forEach((msg) => {
        appendMessage(msg.conteudo, msg.remetente);
      });
    } catch (e) {
      // best-effort: keep UI usable even if history fails
      console.error('Erro ao carregar histórico do chat', e);
    }
  }

  async function sendChat() {
    const text = (inputEl.value || '').trim();
    if (!text) return;

    appendMessage(text, 'user');
    inputEl.value = '';

    const loading = appendMessage(
      '<span style="animation:pulse 1s infinite">●</span> ContAI está pensando...',
      'ai',
      true
    );
    loading.style.color = 'var(--text-secondary)';

    try {
      const res = await window.csrfFetch('/chat/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text }),
      });
      const payload = await res.json();
      const responseText = payload?.data?.response;
      loading.textContent = responseText || payload?.message || 'Erro ao obter resposta.';
      loading.style.color = '';
    } catch (e) {
      loading.textContent = 'Erro de comunicação com o ContAI.';
    }
  }

  window.sendChat = sendChat; // used by inline handlers in template

  inputEl.addEventListener('keydown', (ev) => {
    if (ev.key === 'Enter') sendChat();
  });

  loadChatHistory();
})();

