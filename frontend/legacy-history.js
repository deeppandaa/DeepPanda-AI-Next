(() => {
  const fileInput = document.querySelector('#legacy-file');
  const scanButton = document.querySelector('#legacy-scan');
  const candidateInput = document.querySelector('#legacy-candidate');
  const listButton = document.querySelector('#legacy-list');
  const clearButton = document.querySelector('#legacy-clear');
  const status = document.querySelector('#legacy-status');
  const tasks = document.querySelector('#legacy-tasks');
  const detail = document.querySelector('#legacy-detail');
  let candidates = [];
  let busy = false;

  function reset() {
    candidates = [];
    candidateInput.replaceChildren();
    tasks.replaceChildren();
    detail.textContent = '';
    status.textContent = '';
    updateControls();
  }

  function updateControls() {
    fileInput.disabled = busy;
    scanButton.disabled = busy;
    clearButton.disabled = busy;
    candidateInput.disabled = busy || candidates.length === 0;
    listButton.disabled = busy || candidates.length === 0;
  }

  async function send(action, candidate, taskId) {
    const file = fileInput.files[0];
    if (!file || file.size === 0 || file.size > 64 * 1024 * 1024) {
      throw new Error('1 bayt ile 64 MiB arasında bir ZIP seçin.');
    }
    const origin = new URL(window.location.origin);
    if (!['http:', 'https:'].includes(origin.protocol) || !['127.0.0.1', '[::1]'].includes(origin.hostname)) {
      throw new Error('Hassas arşiv yalnız sayısal yerel adresteki DeepPanda sunucusuna gönderilebilir.');
    }
    if (navigator.serviceWorker && navigator.serviceWorker.controller) {
      throw new Error('Etkin service worker varken arşiv gönderilemez.');
    }
    if (!window.confirm(
      `${file.name} (${file.size} bayt) arşivi ${origin.origin} adresine yeniden gönderilecek.\n` +
      'Yalnız bu bilgisayardaki güvenilir DeepPanda kurulumuna gönderin. İçerik hassas olabilir. Onaylıyor musunuz?'
    )) {
      throw new Error('Gönderim iptal edildi.');
    }
    const url = new URL(`/api/legacy-history/${action}`, origin);
    const headers = { 'Content-Type': 'application/octet-stream', 'X-Legacy-History-Approved': 'true' };
    if (candidate) {
      url.searchParams.set('database_index', String(candidate.database_index));
      url.searchParams.set('source_sha256', candidate.source_sha256);
    }
    if (taskId !== undefined) headers['X-Legacy-Task-Id'] = encodeURIComponent(taskId);
    const response = await fetch(url.toString(), {
      method: 'POST', headers, body: file, redirect: 'error', cache: 'no-store', credentials: 'same-origin',
    });
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'Geçmiş API hatası.');
    return result;
  }

  async function run(operation) {
    if (busy) return;
    busy = true;
    updateControls();
    status.textContent = 'İşleniyor...';
    try {
      await operation();
    } catch (error) {
      status.textContent = error instanceof Error ? error.message : 'Geçmiş işlemi başarısız.';
    } finally {
      busy = false;
      updateControls();
    }
  }

  fileInput.addEventListener('change', reset);
  clearButton.addEventListener('click', () => {
    fileInput.value = '';
    reset();
  });
  candidateInput.addEventListener('change', () => {
    tasks.replaceChildren();
    detail.textContent = '';
  });

  scanButton.addEventListener('click', () => run(async () => {
    reset();
    const result = await send('candidates');
    if (!Array.isArray(result.candidates) || result.candidates.some((candidate) =>
      !Number.isInteger(candidate.database_index) || candidate.database_index < 1 ||
      typeof candidate.source_sha256 !== 'string' || !/^[0-9a-f]{64}$/.test(candidate.source_sha256))) {
      throw new Error('Aday yanıtı geçersiz.');
    }
    candidates = result.candidates;
    candidates.forEach((candidate, index) => {
      const option = document.createElement('option');
      option.value = String(index);
      option.textContent = `Aday ${candidate.database_index} · SHA-256 ${candidate.source_sha256}`;
      candidateInput.append(option);
    });
    status.textContent = candidates.length ? `${candidates.length} aday bulundu.` : 'SQLite adayı bulunamadı.';
  }));

  listButton.addEventListener('click', () => run(async () => {
    const candidate = candidates[Number(candidateInput.value)];
    if (!candidate) throw new Error('Önce bir aday seçin.');
    tasks.replaceChildren();
    detail.textContent = '';
    const result = await send('list', candidate);
    if (result.mode !== 'historical_read_only' || result.source_sha256 !== candidate.source_sha256 ||
        !Array.isArray(result.tasks)) throw new Error('Görev listesi yanıtı geçersiz.');
    for (const task of result.tasks) {
      if (typeof task.task_id !== 'string') throw new Error('Görev kimliği geçersiz.');
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'task-step-action';
      button.textContent = `${task.task_id} · ${String(task.request ?? '')} · ${String(task.status ?? '')}`;
      button.addEventListener('click', () => run(async () => {
        detail.textContent = '';
        const selected = await send('detail', candidate, task.task_id);
        if (selected.mode !== 'historical_read_only' || selected.source_sha256 !== candidate.source_sha256 ||
            !selected.task || selected.task.task_id !== task.task_id || typeof selected.steps_available !== 'boolean') {
          throw new Error('Görev ayrıntısı yanıtı geçersiz.');
        }
        detail.textContent = `${selected.steps_available ? 'Adım tablosu mevcut.' : 'Adım tablosu yok.'}\n\n` +
          JSON.stringify({ task: selected.task, steps: selected.steps }, null, 2);
        status.textContent = 'Geçmiş yalnız görüntülendi; hiçbir işlem çalıştırılmadı.';
      }));
      tasks.append(button);
    }
    status.textContent = result.tasks.length ? `${result.tasks.length} geçmiş görev bulundu.` : 'Geçmiş görev yok.';
  }));
  updateControls();
})();
