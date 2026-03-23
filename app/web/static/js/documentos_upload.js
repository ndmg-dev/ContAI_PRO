(() => {
  const input = document.getElementById('file-input');
  const dropZone = document.getElementById('drop-zone');
  const badge = document.getElementById('file-badge');
  const count = document.getElementById('file-count');
  const preview = document.getElementById('file-names-preview');
  const submitSend = document.getElementById('submit-send');
  const modeSingle = document.getElementById('mode-single');
  const modeBatch = document.getElementById('mode-batch');
  const form = document.getElementById('upload-form');
  const overlay = document.getElementById('upload-overlay');
  const progText = document.getElementById('upload-progress-text');

  if (
    !input ||
    !dropZone ||
    !badge ||
    !count ||
    !preview ||
    !submitSend ||
    !modeSingle ||
    !modeBatch ||
    !form ||
    !overlay ||
    !progText
  )
    return;

  let mode = 'single'; // 'single' | 'batch'

  function setMode(nextMode) {
    mode = nextMode === 'batch' ? 'batch' : 'single';
    const isSingle = mode === 'single';
    modeSingle.setAttribute('aria-pressed', String(isSingle));
    modeBatch.setAttribute('aria-pressed', String(!isSingle));

    // Visual feedback (inline, consistent with current template style approach)
    modeSingle.style.background = isSingle ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.02)';
    modeSingle.style.color = isSingle ? 'var(--text-primary)' : 'var(--text-secondary)';
    modeSingle.style.borderColor = isSingle ? 'rgba(172,141,90,0.55)' : 'var(--border-color)';

    modeBatch.style.background = !isSingle ? 'rgba(255,255,255,0.04)' : 'rgba(255,255,255,0.02)';
    modeBatch.style.color = !isSingle ? 'var(--text-primary)' : 'var(--text-secondary)';
    modeBatch.style.borderColor = !isSingle ? 'rgba(172,141,90,0.55)' : 'var(--border-color)';

    // toggle multiple on input
    input.multiple = !isSingle;

    // If switching to single and there are multiple files selected, keep the first only
    if (isSingle && input.files && input.files.length > 1) {
      const dt = new DataTransfer();
      dt.items.add(input.files[0]);
      input.files = dt.files;
    }

    updateUI(input.files);
  }

  function setBtnEnabled(enabled) {
    submitSend.style.opacity = enabled ? '1' : '0.5';
    submitSend.style.pointerEvents = enabled ? 'auto' : 'none';
  }

  function updateUI(files) {
    if (files && files.length > 0) {
      count.textContent = String(files.length);
      badge.style.display = 'inline-block';
      const names = Array.from(files)
        .map((f) => f.name)
        .join(', ');
      preview.textContent = names;
      const n = files.length;
      const canSend = mode === 'single' ? n === 1 : n >= 1;
      setBtnEnabled(canSend);
      submitSend.value = mode; // upload_mode
      submitSend.lastChild.textContent = mode === 'single' ? ' Enviar Arquivo' : ' Enviar Lote';
    } else {
      badge.style.display = 'none';
      preview.textContent = '';
      setBtnEnabled(false);
      submitSend.value = mode;
      submitSend.lastChild.textContent = ' Enviar';
    }
  }

  input.addEventListener('change', () => updateUI(input.files));

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--accent-gold)';
    dropZone.style.background = 'rgba(172,141,90,0.06)';
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.style.borderColor = 'var(--border-color)';
    dropZone.style.background = '';
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.style.borderColor = 'var(--border-color)';
    dropZone.style.background = '';
    const dt = new DataTransfer();
    if (mode === 'single') {
      const first = e.dataTransfer.files?.[0];
      if (first) dt.items.add(first);
    } else {
      for (const f of e.dataTransfer.files) dt.items.add(f);
    }
    input.files = dt.files;
    updateUI(input.files);
  });

  form.addEventListener('submit', () => {
    if (!input.files || input.files.length === 0) return;
    const n = input.files.length;
    progText.textContent = `Enviando ${n} arquivo${n > 1 ? 's' : ''}… Isso pode levar alguns segundos.`;
    overlay.style.display = 'flex';
  });

  modeSingle.addEventListener('click', () => setMode('single'));
  modeBatch.addEventListener('click', () => setMode('batch'));

  // default mode
  setMode('single');
})();

