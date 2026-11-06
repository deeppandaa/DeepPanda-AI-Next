(() => {
  const TASKS = [
    ['info', 'Bilgi al'],
    ['code', 'Kod yaz'],
    ['review', 'Revizyon / inceleme'],
    ['debug', 'Hata bul'],
  ];
  let providers = [];

  async function postAction(action, payload) {
    const response = await fetch(`/api/plugins/cloud_providers/actions/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(result.detail || `İstek başarısız (${response.status}).`);
      error.auth = result.auth;
      throw error;
    }
    return result;
  }

  async function loadCatalog() {
    try {
      const catalog = await postAction('catalog', {});
      providers = Array.isArray(catalog.providers) ? catalog.providers : [];
    } catch {
      providers = [];
    }
    if (typeof renderModelOptions === 'function') renderModelOptions();
    renderManager();
  }

  function modelOptions() {
    return providers.map((provider) => ({
      value: `cloud:${provider.id}`,
      label: `☁ ${provider.name} · ${provider.configured ? 'oturum açık' : 'oturum yok'}${provider.free_tier ? ' · ücretsiz katman' : ''}`,
    }));
  }

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function appendCard(card) {
    const container = document.querySelector('#messages');
    container.append(card);
    card.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function keyForm(auth, onSaved) {
    const form = element('form', 'cloud-key-form');
    const input = element('input');
    input.type = 'password';
    input.autocomplete = 'off';
    input.placeholder = `${auth.provider_name} API anahtarını yapıştırın`;
    input.required = true;
    const save = element('button', 'session-action', 'Kaydet ve devam et');
    save.type = 'submit';
    const status = element('p', 'memory-status');
    form.append(input, save, status);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      save.disabled = true;
      status.textContent = 'Anahtar yerel olarak kaydediliyor...';
      try {
        await postAction('save_key', { provider: auth.provider, api_key: input.value.trim() });
        input.value = '';
        status.textContent = 'Oturum kaydedildi.';
        await loadCatalog();
        form.closest('.cloud-card')?.classList.add('resolved');
        if (onSaved) await onSaved();
      } catch (error) {
        status.textContent = error.message;
        save.disabled = false;
      }
    });
    return form;
  }

  function renderAuthRequired(auth, retry) {
    if (!auth) return;
    const card = element('div', 'message assistant cloud-card');
    card.append(element('p', '', auth.question));
    const actions = element('div', 'cloud-actions');
    const yes = element('button', 'session-action', 'Evet, oturum açabilirim');
    const no = element('button', 'session-action danger', 'Hayır, vazgeç');
    yes.type = 'button';
    no.type = 'button';
    actions.append(yes, no);
    card.append(actions);
    yes.addEventListener('click', () => {
      actions.remove();
      const guide = element('p', 'memory-status');
      guide.append(`1) ${auth.provider_name} sayfasında oturum açın veya kayıt olun. 2) API anahtarı oluşturun. 3) Anahtarı aşağıya yapıştırın. `);
      const link = element('a', '', 'API anahtarı sayfasını aç');
      link.href = auth.key_url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      guide.append(link);
      card.append(guide, keyForm(auth, retry));
      window.open(auth.key_url, '_blank', 'noopener,noreferrer');
    });
    no.addEventListener('click', () => {
      actions.remove();
      card.append(element('p', 'memory-status', 'Anlaşıldı; istek durduruldu ve hiçbir veri gönderilmedi.'));
    });
    appendCard(card);
  }

  async function consult(form, question, previousAnswer) {
    const selected = [...form.querySelectorAll('input[name="cloud-provider"]:checked')].map((input) => input.value);
    const status = form.querySelector('.memory-status');
    if (!selected.length) {
      status.textContent = 'En az bir sağlayıcı seçin.';
      return;
    }
    const task = form.querySelector('select').value;
    const includePrevious = form.querySelector('input[name="include-previous"]').checked;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    status.textContent = `${selected.length} sağlayıcıya soruluyor...`;
    try {
      const result = await postAction('consult', {
        providers: selected,
        task,
        message: question,
        previous_answer: includePrevious && previousAnswer ? previousAnswer : null,
      });
      status.textContent = 'Yanıtlar geldi.';
      for (const item of result.results || []) {
        if (item.status === 'ok') {
          addMessage(`☁ ${item.provider_name} (${item.model})\n\n${item.content}`, 'assistant');
        } else if (item.status === 'auth_required') {
          renderAuthRequired(item, () => consult(form, question, previousAnswer));
        } else {
          addMessage(`☁ ${item.provider_name}: ${item.error}`, 'assistant', true);
        }
      }
    } catch (error) {
      status.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function consultForm(question, previousAnswer, suggested) {
    const form = element('form', 'cloud-consult-form');
    form.append(element('strong', '', 'Başka yapay zekâya sor'));
    const list = element('div', 'cloud-provider-list');
    for (const provider of providers) {
      const label = element('label', 'cloud-provider-option');
      const input = element('input');
      input.type = 'checkbox';
      input.name = 'cloud-provider';
      input.value = provider.id;
      input.checked = suggested.includes(provider.id) && provider.configured;
      label.append(input, ` ${provider.name}${provider.configured ? ' ✓' : ' · oturum yok'}`);
      list.append(label);
    }
    const task = element('select');
    for (const [value, text] of TASKS) task.add(new Option(text, value));
    const previous = element('label', 'cloud-provider-option');
    const previousInput = element('input');
    previousInput.type = 'checkbox';
    previousInput.name = 'include-previous';
    previousInput.checked = Boolean(previousAnswer);
    previousInput.disabled = !previousAnswer;
    previous.append(previousInput, ' Yerel yanıtı da gönder (revize/hata bulma için)');
    const send = element('button', 'session-action', 'Seçilenlere sor');
    send.type = 'submit';
    form.append(
      element('p', 'memory-status', 'Soru yalnızca seçtiğiniz sağlayıcılara gönderilir; oturumu olmayanlar durur ve oturum açmanız istenir.'),
      list, task, previous, send, element('p', 'memory-status'),
    );
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      consult(form, question, previousAnswer);
    });
    return form;
  }

  function renderAnswerActions(question, answer, suggestion) {
    if (!providers.length) return;
    const row = element('div', 'message tool-activity cloud-answer-actions');
    if (suggestion?.reason) row.append(element('p', '', suggestion.reason));
    const button = element('button', 'session-action', 'Başka yapay zekâya sor');
    button.type = 'button';
    row.append(button);
    const suggested = (suggestion?.providers || []).map((item) => item.id);
    button.addEventListener('click', () => {
      button.remove();
      row.append(consultForm(question, answer, suggested));
    });
    appendCard(row);
  }

  function renderManager() {
    const panel = document.querySelector('#cloud-provider-panel');
    if (!panel) return;
    const list = panel.querySelector('.cloud-manager-list');
    list.replaceChildren();
    for (const provider of providers) {
      const row = element('div', 'cloud-manager-row');
      row.append(element('span', '', `${provider.name}${provider.free_tier ? ' · ücretsiz katman' : ''}`));
      row.append(element('span', 'memory-status', provider.configured
        ? `oturum açık (${provider.key_source === 'env' ? 'ortam değişkeni' : 'yerel'}) · ${provider.model}`
        : 'oturum yok'));
      if (provider.configured && provider.key_source === 'ui') {
        const remove = element('button', 'session-action danger', 'Oturumu kapat');
        remove.type = 'button';
        remove.addEventListener('click', async () => {
          if (!window.confirm(`${provider.name} anahtarı silinsin mi?`)) return;
          await postAction('remove_key', { provider: provider.id });
          await loadCatalog();
        });
        row.append(remove);
      } else if (!provider.configured) {
        const login = element('button', 'session-action', 'Oturum aç');
        login.type = 'button';
        login.addEventListener('click', () => {
          row.append(keyForm({ provider: provider.id, provider_name: provider.name }, null));
          login.remove();
          window.open(provider.key_url, '_blank', 'noopener,noreferrer');
        });
        row.append(login);
      }
      list.append(row);
    }
  }

  window.DeepPandaCloud = { modelOptions, renderAuthRequired, renderAnswerActions, reload: loadCatalog };
  loadCatalog();
})();
