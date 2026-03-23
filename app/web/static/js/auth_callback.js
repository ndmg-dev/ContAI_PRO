(() => {
  const msg = document.getElementById('msg');
  if (!msg) return;

  function showError(text) {
    msg.textContent = text;
    msg.style.display = 'block';
    setTimeout(() => {
      window.location.href = '/auth/login';
    }, 3000);
  }

  (async function run() {
    const hash = window.location.hash.substring(1);
    if (!hash) {
      showError('Nenhum token recebido. Redirecionando para login...');
      return;
    }

    const params = new URLSearchParams(hash);
    const accessToken = params.get('access_token');
    const errorParam = params.get('error_description') || params.get('error');

    if (errorParam) {
      showError('Erro: ' + errorParam);
      return;
    }

    if (!accessToken) {
      showError('Token não encontrado. Redirecionando...');
      return;
    }

    try {
      const res = await window.csrfFetch('/auth/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ access_token: accessToken }),
      });
      const data = await res.json();
      if (data.ok) window.location.href = data.redirect || '/dashboard';
      else showError(data.message || 'Acesso negado.');
    } catch (e) {
      showError('Erro de rede ao validar sessão.');
    }
  })();
})();

