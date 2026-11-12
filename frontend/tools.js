'use strict';

// Local capability tools ported from the legacy LocalQwenAgent. Every call goes through the plugin gateway.
(() => {
  const TOOLS = [
    {
      id: 'windows_host', label: 'Windows host (Qt gerekir)', forms: [
        { title: 'Windows / USB / COM / sürücü / kayıt erişimi: Qt istemcisini kullanın',
          plugin: 'windows_host', action: 'status', fields: [] },
      ],
    },
    {
      id: 'prompt-library', label: 'Şablonlar', forms: [
        { title: 'Yerel katalog indir / yenile', plugin: 'prompt_library', action: 'sync',
          approval: 'GitHub raw.githubusercontent.com adresinden genel prompts.chat kataloğu indirilsin ve yerel katalog yenilensin mi? Mevcut katalog değiştirilecek.', fields: [] },
        { title: 'Yerel şablon ara (başlık)', plugin: 'prompt_library', action: 'local_search', fields: [
          { name: 'query', label: 'Arama', maxLength: 200 },
        ] },
        { title: 'Çevrim içi şablon ara', plugin: 'prompt_library', action: 'online_search',
          approval: 'Arama sorgusu prompts.chat adresine gönderilsin mi?', fields: [
            { name: 'query', label: 'Gönderilecek sorgu', required: true, maxLength: 200 },
          ] },
        { title: 'Çevrim içi şablon getir', plugin: 'prompt_library', action: 'online_get',
          approval: 'Seçilen şablon kimliği prompts.chat adresine gönderilsin mi?', fields: [
            { name: 'id', label: 'Şablon ID', required: true, maxLength: 200 },
          ] },
      ],
    },
    {
      id: 'system', label: 'Sistem', forms: [
        { title: 'Donanım', plugin: 'system', action: 'hardware', fields: [] },
        { title: 'Hazırlık durumu', plugin: 'system', action: 'readiness', fields: [] },
        { title: 'Model dosyaları', plugin: 'system', action: 'model_assets', fields: [] },
        { title: 'Ollama modeli indir', plugin: 'ollama', action: 'pull', approval: 'Model indirilsin mi? Bu işlem uzun sürebilir.', fields: [
          { name: 'model', label: 'Model', placeholder: 'nomic-embed-text:latest', required: true, maxLength: 232, pattern: '[A-Za-z0-9][A-Za-z0-9._/-]{0,150}(:[A-Za-z0-9._-]{1,80})?' },
        ] },
      ],
    },
    {
      id: 'licensing', label: 'Lisans', forms: [
        { title: 'Lisans durumu', plugin: 'licensing', action: 'status', fields: [] },
        { title: 'Lisans etkinleştir', plugin: 'licensing', action: 'activate', approval: 'Lisans bu kuruluma etkinleştirilsin mi?', fields: [
          { name: 'license_key', label: 'Lisans anahtarı (VANA1...)', type: 'textarea', required: true, maxLength: 8_000 },
        ] },
        { title: 'Lisansı kaldır', plugin: 'licensing', action: 'deactivate', approval: 'Etkin lisans bu kurulumdan kaldırılsın mı?', fields: [] },
      ],
    },
    {
      id: 'assets', label: 'Dosyalar', forms: [
        { title: 'Üretilen dosyalar', plugin: 'assets', action: 'list', fields: [
          { name: 'kind', label: 'Tür', type: 'select', options: ['', 'image', 'audio', 'video', 'report', 'document', 'other'] },
          { name: 'limit', label: 'Sınır', type: 'number', value: '50', min: 1, max: 200, step: 1 },
        ] },
        { title: 'Dosya sil', plugin: 'assets', action: 'delete', approval: 'Dosya kalıcı olarak silinsin mi?', fields: [
          { name: 'asset_id', label: 'Dosya ID', required: true, maxLength: 32, pattern: '[a-f0-9]{32}' },
        ] },
      ],
    },
    {
      id: 'reports', label: 'Rapor', forms: [
        { title: 'Rapor dışa aktar', plugin: 'reports', action: 'export', approval: 'Rapor dosyası oluşturulsun mu?', fields: [
          { name: 'title', label: 'Başlık', value: 'DeepPanda Raporu', maxLength: 200 },
          { name: 'format', label: 'Biçim', type: 'select', options: ['pdf', 'md'] },
          { name: 'content', label: 'İçerik (Markdown)', type: 'textarea', maxLength: 200_000 },
          { name: 'report', label: 'Rapor verisi (JSON)', type: 'json', maxLength: 200_000 },
          { name: 'sources', label: 'Kaynaklar (satır başına bir)', type: 'lines', maxLines: 100, maxLineLength: 2_000 },
        ] },
        { title: "PDF'e ek sayfa", plugin: 'reports', action: 'append_pdf', approval: 'PDF sonuna ek eklensin mi?', fields: [
          { name: 'file', label: 'PDF', type: 'file', accept: '.pdf', required: true, maxBytes: 20_000_000 },
          { name: 'heading', label: 'Ek başlığı', value: 'Ek Bilgi', maxLength: 200 },
          { name: 'addition', label: 'Ek metin', type: 'textarea', required: true, maxLength: 50_000 },
        ] },
      ],
    },
    {
      id: 'speech', label: 'Ses', forms: [
        { title: 'Ses durumu', plugin: 'speech', action: 'status', fields: [] },
        { title: 'Metni seslendir', plugin: 'speech', action: 'synthesize', approval: 'Ses dosyası oluşturulsun mu?', fields: [
          { name: 'text', label: 'Metin', type: 'textarea', required: true, maxLength: 5_000 },
        ] },
        { title: 'Sesi yazıya dök', plugin: 'speech', action: 'transcribe', fields: [
          { name: 'file', label: 'Ses / video', type: 'file', accept: 'audio/*,video/*', required: true, maxBytes: 100_000_000 },
          { name: 'language', label: 'Dil', value: 'tr', maxLength: 5, pattern: '[A-Za-z]+' },
        ] },
      ],
    },
    {
      id: 'ocr', label: 'OCR', forms: [
        { title: 'OCR durumu', plugin: 'ocr', action: 'status', fields: [] },
        { title: 'Görselden metin çıkar', plugin: 'ocr', action: 'extract', fields: [
          { name: 'file', label: 'Görsel', type: 'file', accept: 'image/*', required: true, maxBytes: 20_000_000 },
          { name: 'language', label: 'Dil', value: 'tur+eng', maxLength: 51, pattern: '[a-z_]{3,12}(\\+[a-z_]{3,12}){0,3}' },
        ] },
      ],
    },
    {
      id: 'media', label: 'Medya', forms: [
        { title: 'Medya durumu', plugin: 'media', action: 'status', fields: [] },
        { title: 'Görsel üret', plugin: 'media', action: 'generate_image', approval: 'Yerel modelle görsel üretilsin mi?', fields: [
          { name: 'prompt', label: 'İstem', type: 'textarea', required: true, maxLength: 2_000 },
          { name: 'width', label: 'Genişlik', type: 'number', value: '512', min: 128, max: 768, step: 8 },
          { name: 'height', label: 'Yükseklik', type: 'number', value: '512', min: 128, max: 768, step: 8 },
          { name: 'steps', label: 'Adım', type: 'number', value: '20', min: 1, max: 30, step: 1 },
        ] },
        { title: 'Video üret (arka plan işi)', plugin: 'media', action: 'start_video', approval: 'Video üretim işi başlatılsın mı?', fields: [
          { name: 'prompt', label: 'İstem', type: 'textarea', required: true, maxLength: 2_000 },
          { name: 'duration_seconds', label: 'Süre (sn)', type: 'number', value: '4', min: 1, max: 10, step: 1 },
        ] },
        { title: 'Görsel düzenle', plugin: 'media', action: 'edit_image', approval: 'Düzenlenmiş görsel kaydedilsin mi?', fields: [
          { name: 'file', label: 'Görsel', type: 'file', accept: 'image/*', required: true, maxBytes: 20_000_000 },
          { name: 'operation', label: 'İşlem', type: 'select', options: ['grayscale', 'rotate', 'resize', 'flip'] },
          { name: 'value', label: 'Değer (derece / uzun kenar pikseli; resize: 16–4096)', type: 'number', value: '0', min: 0, max: 4096, step: 1 },
        ] },
        { title: 'Video kes', plugin: 'media', action: 'edit_video', approval: 'Kesilmiş video kaydedilsin mi?', fields: [
          { name: 'file', label: 'Video', type: 'file', accept: 'video/*', required: true, maxBytes: 300_000_000 },
          { name: 'start_seconds', label: 'Başlangıç (sn)', type: 'number', value: '0', min: 0, max: 86_400, step: 'any' },
          { name: 'duration_seconds', label: 'Süre (sn)', type: 'number', value: '10', min: 0.1, max: 3_600, step: 'any' },
          { name: 'output_format', label: 'Biçim', type: 'select', options: ['mp4', 'webm'] },
        ] },
        { title: 'Video analizi', plugin: 'media', action: 'analyze', fields: [
          { name: 'file', label: 'Video', type: 'file', accept: 'video/*', required: true, maxBytes: 300_000_000 },
          { name: 'transcribe', label: 'Sesi yazıya dök', type: 'checkbox' },
          { name: 'vision', label: 'Kareleri görsel modelle yorumla', type: 'checkbox' },
        ] },
      ],
    },
    {
      id: 'evaluation', label: 'Değerlendirme', forms: [
        { title: 'Değerlendirme çalıştır', plugin: 'evaluation', action: 'run', approval: 'Değerlendirme işi başlatılsın mı?', fields: [
          { name: 'suite', label: 'Paket', type: 'select', options: ['unit_tests', 'intent', 'models'] },
          { name: 'model', label: 'Model (isteğe bağlı)' },
          { name: 'limit', label: 'Örnek sınırı', type: 'number', min: 1, max: 500, step: 1 },
        ] },
        { title: 'Raporlar', plugin: 'evaluation', action: 'reports', fields: [
          { name: 'report_id', label: 'Rapor ID (boş = liste)' },
        ] },
      ],
    },
    {
      id: 'instagram', label: 'Instagram', forms: [
        { title: 'Instagram durumu', plugin: 'instagram', action: 'status', fields: [] },
        { title: 'Görsel paylaş', plugin: 'instagram', action: 'publish_image', approval: 'Görsel Instagram hesabında herkese açık paylaşılsın mı?', fields: [
          { name: 'image_url', label: 'Public HTTPS görsel URL', type: 'url', required: true, maxLength: 2_000 },
          { name: 'caption', label: 'Açıklama', type: 'textarea', maxLength: 2_200 },
        ] },
        { title: 'Reel paylaş', plugin: 'instagram', action: 'publish_video', approval: 'Video Reel olarak herkese açık paylaşılsın mı?', fields: [
          { name: 'video_url', label: 'Public HTTPS video URL', type: 'url', required: true, maxLength: 2_000 },
          { name: 'caption', label: 'Açıklama', type: 'textarea', maxLength: 2_200 },
        ] },
        { title: 'Mesaj gönder', plugin: 'instagram', action: 'send_message', approval: 'Mesaj gönderilsin mi?', fields: [
          { name: 'recipient_id', label: 'Alıcı ID', required: true, maxLength: 40, pattern: '[0-9]{1,40}' },
          { name: 'text', label: 'Mesaj', type: 'textarea', required: true, maxLength: 2_000 },
        ] },
      ],
    },
  ];

  const panel = document.querySelector('#tools-panel');
  const openButton = document.querySelector('#open-tools');
  const closeButton = document.querySelector('#close-tools');
  const tabs = document.querySelector('#tools-tabs');
  const body = document.querySelector('#tools-body');
  if (!panel || !openButton || !closeButton || !tabs || !body) return;

  async function invoke(plugin, action, payload = {}) {
    const response = await fetch(`/api/plugins/${plugin}/actions/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload }),
    });
    let result;
    try {
      result = await response.json();
    } catch {
      throw new Error(`${response.status}: Sunucu geçerli JSON yanıtı döndürmedi.`);
    }
    if (!response.ok) {
      const detail = typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail || result);
      throw new Error(`${response.status}: ${detail || 'İşlem tamamlanamadı.'}`);
    }
    return result;
  }

  function readFileBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',', 2)[1] || '');
      reader.onerror = () => reject(new Error('Dosya okunamadı.'));
      reader.onabort = () => reject(new Error('Dosya okuma işlemi iptal edildi.'));
      reader.readAsDataURL(file);
    });
  }

  function collectLinks(value, found = { downloads: [], jobs: [] }) {
    if (Array.isArray(value)) {
      value.forEach((item) => collectLinks(item, found));
    } else if (value && typeof value === 'object') {
      for (const [key, item] of Object.entries(value)) {
        if (key === 'download_url' && typeof item === 'string' && item.startsWith('/api/assets/')) {
          found.downloads.push({ url: item, name: value.filename || value.asset_id || item });
        } else if (key === 'job_id' && typeof item === 'string') {
          found.jobs.push(item);
        } else {
          collectLinks(item, found);
        }
      }
    }
    return found;
  }

  function renderResult(container, result, spec) {
    container.replaceChildren();
    if (spec.plugin === 'prompt_library' && ['local_search', 'online_search', 'online_get'].includes(spec.action)) {
      const prompts = spec.action === 'local_search' ? result.prompts : [result.prompt];
      const entries = spec.action === 'online_search' ? result.prompts : prompts;
      if (!Array.isArray(entries) || entries.length > 10 || entries.some((prompt) =>
        !prompt || typeof prompt.title !== 'string' || typeof prompt.content !== 'string' ||
        prompt.content.length > 40000 || (spec.action === 'online_search' &&
          (prompt.preview !== true || typeof prompt.id !== 'string' || !prompt.id || prompt.id.length > 200)))) {
        throw new Error('Şablon yanıtı geçersiz.');
      }

      function renderPrompt(prompt, preview) {
        const card = document.createElement('article');
        card.className = 'memory-result';
        const title = document.createElement('strong');
        title.textContent = prompt.title;
        const content = document.createElement('pre');
        content.className = 'tools-output';
        content.textContent = prompt.content;
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'memory-timeline';
        button.textContent = preview ? 'Tam şablonu getir' : 'Taslağa ekle';
        const status = document.createElement('p');
        status.className = 'memory-status';
        status.setAttribute('role', 'status');
        button.addEventListener('click', async () => {
          if (preview) {
            if (!window.confirm(`Şablon kimliği prompts.chat adresine gönderilsin mi?\n${prompt.id}`)) return;
            button.disabled = true;
            status.textContent = 'Şablon getiriliyor...';
            try {
              const response = await invoke('prompt_library', 'online_get', { id: prompt.id, approved: true });
              const full = response.prompt;
              if (!full || full.id !== prompt.id || typeof full.title !== 'string' ||
                  typeof full.content !== 'string' || !full.content || full.content.length > 40000) {
                throw new Error('Şablon yanıtı geçersiz.');
              }
              card.replaceChildren(renderPrompt(full, false));
            } catch (error) {
              status.textContent = error.message;
              button.disabled = false;
            }
            return;
          }
          const input = document.querySelector('#message');
          const combined = input.value ? `${input.value}\n\n${prompt.content}` : prompt.content;
          if (combined.length > 20000) {
            status.textContent = 'Taslak ve şablon toplamı 20.000 karakteri aşıyor.';
            return;
          }
          input.value = combined;
          status.textContent = 'Şablon taslağa eklendi; gönderilmedi.';
          input.focus();
        });
        card.append(title, content, button, status);
        return card;
      }
      for (const prompt of entries) container.append(renderPrompt(prompt, spec.action === 'online_search'));
      return;
    }
    const { downloads, jobs } = collectLinks(result);
    for (const item of downloads) {
      const link = document.createElement('a');
      link.href = item.url;
      link.textContent = `İndir: ${item.name}`;
      link.target = '_blank';
      link.rel = 'noopener';
      link.className = 'tools-link';
      container.append(link);
    }
    for (const jobId of [...new Set(jobs)]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'memory-timeline';
      button.textContent = `İşi izle: ${jobId}`;
      button.addEventListener('click', () => document.querySelector('#open-jobs')?.click());
      container.append(button);
    }
    const pre = document.createElement('pre');
    pre.className = 'tools-output';
    pre.textContent = JSON.stringify(result, null, 2);
    container.append(pre);
  }

  function buildField(field) {
    const label = document.createElement('label');
    label.className = 'tools-field';
    const caption = document.createElement('span');
    caption.textContent = field.maxBytes ? `${field.label} (en fazla ${field.maxBytes / 1_000_000} MB)` : field.label;
    let input;
    if (field.type === 'textarea' || field.type === 'lines' || field.type === 'json') {
      input = document.createElement('textarea');
      input.rows = 4;
    } else if (field.type === 'select') {
      input = document.createElement('select');
      for (const option of field.options) {
        const element = document.createElement('option');
        element.value = option;
        element.textContent = option || 'Tümü';
        input.append(element);
      }
    } else {
      input = document.createElement('input');
      input.type = field.type || 'text';
      if (field.accept) input.accept = field.accept;
      if (field.step) input.step = field.step;
    }
    input.name = field.name;
    if (field.placeholder) input.placeholder = field.placeholder;
    if (field.value !== undefined && field.type !== 'file') input.value = field.value;
    if (field.required && field.type !== 'file') input.required = true;
    if (field.maxLength !== undefined) input.maxLength = field.maxLength;
    if (field.pattern) input.pattern = field.pattern;
    if (field.min !== undefined) input.min = field.min;
    if (field.max !== undefined) input.max = field.max;
    if (field.type === 'checkbox') {
      label.classList.add('tools-check');
      label.append(input, caption);
    } else {
      label.append(caption, input);
    }
    return label;
  }

  async function buildPayload(form, spec) {
    const payload = {};
    for (const field of spec.fields) {
      const input = form.elements.namedItem(field.name);
      if (field.type === 'file') {
        const file = input.files && input.files[0];
        if (!file) {
          if (field.required) throw new Error(`${field.label} seçilmedi.`);
          continue;
        }
        if (file.size > field.maxBytes) {
          throw new Error(`${field.label} boyutu en fazla ${field.maxBytes / 1_000_000} MB olabilir.`);
        }
        payload.filename = file.name;
        payload.content_base64 = await readFileBase64(file);
      } else if (field.type === 'checkbox') {
        payload[field.name] = input.checked;
      } else if (field.type === 'number') {
        if (input.value !== '') {
          const value = Number(input.value);
          if (!Number.isFinite(value)) throw new Error(`${field.label} sonlu bir sayı olmalı.`);
          payload[field.name] = value;
        }
      } else if (field.type === 'json') {
        if (input.value.trim() !== '') {
          try {
            payload[field.name] = JSON.parse(input.value);
          } catch {
            throw new Error(`${field.label} geçerli JSON olmalı.`);
          }
        }
      } else if (field.type === 'lines') {
        const lines = input.value.split('\n').map((line) => line.trim()).filter(Boolean);
        if (field.maxLines !== undefined && lines.length > field.maxLines) {
          throw new Error(`${field.label} en fazla ${field.maxLines} satır olabilir.`);
        }
        if (field.maxLineLength !== undefined && lines.some((line) => line.length > field.maxLineLength)) {
          throw new Error(`${field.label} satırları en fazla ${field.maxLineLength} karakter olabilir.`);
        }
        if (lines.length) payload[field.name] = lines;
      } else if (input.value.trim() !== '') {
        payload[field.name] = input.value.trim();
      }
    }
    if (
      spec.plugin === 'reports' &&
      spec.action === 'export' &&
      !payload.content &&
      (payload.report === undefined || payload.report === null)
    ) {
      throw new Error('İçerik veya rapor verisi girilmeli.');
    }
    return payload;
  }

  function buildForm(spec) {
    const form = document.createElement('form');
    form.className = 'tools-form';
    const title = document.createElement('h3');
    title.textContent = spec.title;
    form.append(title);
    spec.fields.forEach((field) => form.append(buildField(field)));
    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.className = spec.approval ? 'document-delete-button' : 'memory-timeline';
    submit.textContent = spec.approval ? 'Onayla ve çalıştır' : 'Çalıştır';
    const status = document.createElement('p');
    status.className = 'memory-status';
    status.setAttribute('role', 'status');
    const output = document.createElement('div');
    output.className = 'tools-result';
    form.append(submit, status, output);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      output.replaceChildren();
      submit.disabled = true;
      status.textContent = 'Doğrulanıyor...';
      try {
        const payload = await buildPayload(form, spec);
        const approvalText = spec.plugin === 'prompt_library' && ['online_search', 'online_get'].includes(spec.action)
          ? `${spec.approval}\n${payload.query || payload.id || ''}` : spec.approval;
        if (approvalText && !window.confirm(approvalText)) {
          status.textContent = 'Onay verilmedi; işlem yapılmadı.';
          return;
        }
        if (spec.approval) payload.approved = true;
        status.textContent = 'Çalışıyor...';
        const result = await invoke(spec.plugin, spec.action, payload);
        status.textContent = spec.plugin === 'prompt_library' && spec.action === 'local_search' && result.installed === false
          ? 'Yerel katalog henüz indirilmedi; yukarıdan onayla ve indir.'
          : spec.action === 'status'
          ? 'Durum alındı; özellik kullanılabilirliği aşağıda gösteriliyor.'
          : Array.isArray(result.skipped_reports) && result.skipped_reports.length
            ? `Tamamlandı; okunamayan raporlar: ${result.skipped_reports.join(', ')}`
            : 'Tamamlandı.';
        renderResult(output, result, spec);
      } catch (error) {
        status.textContent = error.message;
      } finally {
        submit.disabled = false;
      }
    });
    return form;
  }

  async function renderProposals() {
    body.replaceChildren();
    const status = document.createElement('p');
    status.className = 'memory-status';
    status.textContent = 'Öneriler yükleniyor...';
    const list = document.createElement('div');
    list.className = 'memory-results';
    body.append(status, list);
    try {
      const { proposals } = await invoke('memory', 'proposals');
      status.textContent = proposals.length ? `${proposals.length} bekleyen öğrenme önerisi.` : 'Bekleyen öğrenme önerisi yok.';
      for (const proposal of proposals) {
        const item = document.createElement('article');
        item.className = 'memory-result';
        const heading = document.createElement('strong');
        heading.textContent = proposal.title;
        const meta = document.createElement('span');
        meta.textContent = [proposal.project, proposal.category, `${Math.round(proposal.expires_in / 3600)} sa kaldı`].filter(Boolean).join(' · ');
        const content = document.createElement('p');
        content.textContent = proposal.content;
        const approve = document.createElement('button');
        approve.type = 'button';
        approve.className = 'document-delete-button';
        approve.textContent = 'Hafızaya kaydet';
        approve.addEventListener('click', async () => {
          if (!window.confirm('Bu not kalıcı hafızaya kaydedilsin mi?')) return;
          try {
            await invoke('memory', 'approve_proposal', { proposal_id: proposal.proposal_id, approved: true });
            renderProposals();
          } catch (error) {
            status.textContent = error.message;
          }
        });
        const reject = document.createElement('button');
        reject.type = 'button';
        reject.className = 'memory-timeline';
        reject.textContent = 'Reddet';
        reject.addEventListener('click', async () => {
          try {
            await invoke('memory', 'reject_proposal', { proposal_id: proposal.proposal_id });
            renderProposals();
          } catch (error) {
            status.textContent = error.message;
          }
        });
        item.append(heading, meta, content, approve, reject);
        list.append(item);
      }
    } catch (error) {
      status.textContent = error.message;
    }
  }

  function selectTab(id) {
    for (const button of tabs.querySelectorAll('button')) {
      button.setAttribute('aria-selected', String(button.dataset.tool === id));
    }
    if (id === 'proposals') {
      renderProposals();
      return;
    }
    const tool = TOOLS.find((item) => item.id === id);
    body.replaceChildren(...tool.forms.map(buildForm));
  }

  for (const tool of [...TOOLS, { id: 'proposals', label: 'Öğrenme önerileri' }]) {
    const button = document.createElement('button');
    button.type = 'button';
    button.role = 'tab';
    button.dataset.tool = tool.id;
    button.textContent = tool.label;
    button.addEventListener('click', () => selectTab(tool.id));
    tabs.append(button);
  }

  openButton.addEventListener('click', () => {
    const jobsPanel = document.querySelector('#jobs-panel');
    if (jobsPanel && !jobsPanel.hidden) document.querySelector('#close-jobs')?.click();
    for (const other of document.querySelectorAll('.conversation section[id$="-panel"]')) {
      if (other !== panel && other.id !== 'intent-panel') other.hidden = true;
    }
    panel.hidden = false;
    if (!tabs.querySelector('[aria-selected="true"]')) selectTab('system');
  });
  closeButton.addEventListener('click', () => {
    panel.hidden = true;
  });
  document.querySelectorAll('.top-actions button').forEach((button) => {
    if (button !== openButton) button.addEventListener('click', () => { panel.hidden = true; });
  });
})();
