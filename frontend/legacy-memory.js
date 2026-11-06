(() => {
  const form = document.querySelector('#legacy-memory-search');
  const query = document.querySelector('#legacy-memory-query');
  const results = document.querySelector('#legacy-memory-results');
  const status = document.querySelector('#legacy-memory-status');
  const detail = document.querySelector('#legacy-memory-detail');
  const next = document.querySelector('#legacy-memory-next');
  const clear = document.querySelector('#legacy-memory-clear');
  let generation = 0;
  let nextOffset = null;
  let activeQuery = '';

  function reset() {
    generation++;
    results.replaceChildren();
    detail.textContent = '';
    status.textContent = '';
    nextOffset = null;
    next.hidden = true;
  }

  async function request(action, payload) {
    const response = await fetch(`/api/plugins/memory/actions/${action}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload }), cache: 'no-store', redirect: 'error',
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `HTTP ${response.status}`);
    return result;
  }

  async function load(offset) {
    const token = ++generation;
    results.replaceChildren();
    detail.textContent = '';
    next.hidden = true;
    status.textContent = 'Yükleniyor...';
    try {
      const result = await request('legacy_list', { query: activeQuery, offset });
      if (token !== generation) return;
      if (!['not_imported', 'available'].includes(result.status) || !Array.isArray(result.records) ||
          !(result.next_offset === null || Number.isInteger(result.next_offset))) {
        throw new Error('Eski hafıza yanıtı geçersiz.');
      }
      for (const record of result.records) {
        if (typeof record.source_digest !== 'string' || !Number.isSafeInteger(record.legacy_id) ||
            typeof record.note !== 'string') throw new Error('Eski hafıza kaydı geçersiz.');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'task-step-action';
        button.textContent = `${record.legacy_id} · ${record.created_at} · ${record.note}`;
        button.addEventListener('click', async () => {
          const detailToken = ++generation;
          detail.textContent = '';
          status.textContent = 'Kayıt yükleniyor...';
          try {
            const response = await request('legacy_get', {
              source_digest: record.source_digest, legacy_id: record.legacy_id,
            });
            if (detailToken !== generation) return;
            if (response.status !== 'available' || !response.record ||
                response.record.source_digest !== record.source_digest ||
                response.record.legacy_id !== record.legacy_id || typeof response.record.note !== 'string') {
              throw new Error('Eski hafıza ayrıntısı geçersiz.');
            }
            detail.textContent = JSON.stringify(response.record, null, 2);
            status.textContent = 'Salt okunur eski kayıt gösteriliyor.';
          } catch (error) {
            if (detailToken === generation) status.textContent = error.message;
          }
        });
        results.append(button);
      }
      nextOffset = result.next_offset;
      next.hidden = nextOffset === null;
      status.textContent = result.status === 'not_imported'
        ? 'Eski hafıza henüz aktarılmadı.' : `${result.records.length} kayıt gösteriliyor.`;
    } catch (error) {
      if (token === generation) {
        results.replaceChildren();
        status.textContent = error.message;
      }
    }
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    activeQuery = query.value;
    load(0);
  });
  next.addEventListener('click', () => { if (nextOffset !== null) load(nextOffset); });
  clear.addEventListener('click', reset);
})();
