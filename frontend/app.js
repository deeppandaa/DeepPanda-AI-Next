const connection = document.querySelector('#connection');
const connectionLabel = document.querySelector('#connection-label');
const modelStatus = document.querySelector('#model-status');
const modelSelect = document.querySelector('#model-select');
const modelSearch = document.querySelector('#model-search');
const refreshModelsButton = document.querySelector('#refresh-models');
const selectedModelName = document.querySelector('#selected-model-name');
const defaultBadge = document.querySelector('#default-badge');
const modelFamily = document.querySelector('#model-family');
const modelParameters = document.querySelector('#model-parameters');
const modelQuantization = document.querySelector('#model-quantization');
const modelSize = document.querySelector('#model-size');
const workflowSelect = document.querySelector('#workflow-select');
const workflowStatus = document.querySelector('#workflow-status');
const form = document.querySelector('#chat-form');
const messageInput = document.querySelector('#message');
const sendButton = document.querySelector('#send');
const intentPanel = document.querySelector('#intent-panel');
const closeIntentButton = document.querySelector('#close-intent');
const intentName = document.querySelector('#intent-name');
const intentConfidence = document.querySelector('#intent-confidence');
const intentRationale = document.querySelector('#intent-rationale');
const intentNextStep = document.querySelector('#intent-next-step');
const intentStatus = document.querySelector('#intent-status');
const intentTaskDraftButton = document.querySelector('#intent-task-draft');
const learningProposalForm = document.querySelector('#learning-proposal-form');
const learningTitleInput = document.querySelector('#learning-title');
const learningProjectInput = document.querySelector('#learning-project');
const learningCategoryInput = document.querySelector('#learning-category');
const learningContentInput = document.querySelector('#learning-content');
const learningApprovedInput = document.querySelector('#learning-approved');
const learningSaveButton = document.querySelector('#learning-save');
const learningSaveStatus = document.querySelector('#learning-save-status');
const messages = document.querySelector('#messages');
const welcome = document.querySelector('#welcome');
const sessionSelect = document.querySelector('#session-select');
const newChatButton = document.querySelector('#new-chat');
const deleteSessionButton = document.querySelector('#delete-session');
const sessionStatus = document.querySelector('#session-status');
const scanDiagnosticsButton = document.querySelector('#scan-diagnostics');
const closeDiagnosticsButton = document.querySelector('#close-diagnostics');
const diagnosticsPanel = document.querySelector('#diagnostics-panel');
const diagnosticsSummary = document.querySelector('#diagnostics-summary');
const diagnosticsResults = document.querySelector('#diagnostics-results');
const openMemoryButton = document.querySelector('#open-memory');
const closeMemoryButton = document.querySelector('#close-memory');
const memoryPanel = document.querySelector('#memory-panel');
const memorySaveForm = document.querySelector('#memory-save-form');
const memoryTitleInput = document.querySelector('#memory-title-input');
const memoryProjectInput = document.querySelector('#memory-project-input');
const memoryCategoryInput = document.querySelector('#memory-category-input');
const memoryContentInput = document.querySelector('#memory-content-input');
const memoryApprovedInput = document.querySelector('#memory-approved');
const memorySaveButton = document.querySelector('#memory-save-button');
const memorySaveStatus = document.querySelector('#memory-save-status');
const memorySearchForm = document.querySelector('#memory-search-form');
const memoryQueryInput = document.querySelector('#memory-query');
const memoryTimelineButton = document.querySelector('#memory-timeline');
const memoryProjectFilter = document.querySelector('#memory-project-filter');
const memoryCategoryFilter = document.querySelector('#memory-category-filter');
const memorySourceFilter = document.querySelector('#memory-source-filter');
const memoryTaxonomyButton = document.querySelector('#memory-taxonomy');
const memoryExportButton = document.querySelector('#memory-export');
const memoryImportForm = document.querySelector('#memory-import-form');
const memoryImportFileInput = document.querySelector('#memory-import-file');
const memoryImportApprovedInput = document.querySelector('#memory-import-approved');
const memoryImportButton = document.querySelector('#memory-import-button');
const memorySourcePreviewForm = document.querySelector('#memory-source-preview-form');
const memorySourceQueryInput = document.querySelector('#memory-source-query');
const memorySourcePreview = document.querySelector('#memory-source-preview');
const memoryToolsStatus = document.querySelector('#memory-tools-status');
const memoryResults = document.querySelector('#memory-results');
const openCodeGraphButton = document.querySelector('#open-code-graph');
const closeCodeGraphButton = document.querySelector('#close-code-graph');
const codeGraphPanel = document.querySelector('#graph-panel');
const buildCodeGraphButton = document.querySelector('#build-code-graph');
const graphSearchForm = document.querySelector('#graph-search-form');
const graphSearchQuery = document.querySelector('#graph-search-query');
const graphPathForm = document.querySelector('#graph-path-form');
const graphPathSource = document.querySelector('#graph-path-source');
const graphPathTarget = document.querySelector('#graph-path-target');
const graphStatus = document.querySelector('#graph-status');
const graphResults = document.querySelector('#graph-results');
const openDocumentsButton = document.querySelector('#open-documents');
const closeDocumentsButton = document.querySelector('#close-documents');
const documentsPanel = document.querySelector('#documents-panel');
const documentUploadForm = document.querySelector('#document-upload-form');
const documentFileInput = document.querySelector('#document-file');
const documentApprovedInput = document.querySelector('#document-approved');
const documentUploadButton = document.querySelector('#document-upload-button');
const documentUploadStatus = document.querySelector('#document-upload-status');
const documentSearchForm = document.querySelector('#document-search-form');
const documentQueryInput = document.querySelector('#document-query');
const documentListButton = document.querySelector('#document-list-button');
const documentResults = document.querySelector('#document-results');
const documentPreviewDialog = document.querySelector('#document-preview-dialog');
const documentPreviewTitle = document.querySelector('#document-preview-title');
const documentPreviewStatus = document.querySelector('#document-preview-status');
const documentPreviewContent = document.querySelector('#document-preview-content');
const closeDocumentPreviewButton = document.querySelector('#close-document-preview');
const openTasksButton = document.querySelector('#open-tasks');
const closeTasksButton = document.querySelector('#close-tasks');
const tasksPanel = document.querySelector('#tasks-panel');
const openJobsButton = document.querySelector('#open-jobs');
const closeJobsButton = document.querySelector('#close-jobs');
const jobsPanel = document.querySelector('#jobs-panel');
const jobsStatus = document.querySelector('#jobs-status');
const jobsRefreshButton = document.querySelector('#jobs-refresh');
const jobsStaleAfterInput = document.querySelector('#jobs-stale-after');
const jobsRecoverStaleButton = document.querySelector('#jobs-recover-stale');
const jobsRecoveryStatus = document.querySelector('#jobs-recovery-status');
const jobsRecoveryPreview = document.querySelector('#jobs-recovery-preview');
const jobsList = document.querySelector('#jobs-list');
const jobDetail = document.querySelector('#job-detail');
const openResearchButton = document.querySelector('#open-research');
const closeResearchButton = document.querySelector('#close-research');
const researchPanel = document.querySelector('#research-panel');
const researchSearchForm = document.querySelector('#research-search-form');
const researchQueryInput = document.querySelector('#research-query');
const researchSearchButton = document.querySelector('#research-search-button');
const researchResults = document.querySelector('#research-results');
const researchForm = document.querySelector('#research-form');
const researchQuestionInput = document.querySelector('#research-question');
const researchUrlsInput = document.querySelector('#research-urls');
const researchStartButton = document.querySelector('#research-start');
const researchStatus = document.querySelector('#research-status');
const githubResearchForm = document.querySelector('#github-research-form');
const githubResearchQuestionInput = document.querySelector('#github-research-question');
const githubRepositoryUrlsInput = document.querySelector('#github-repository-urls');
const githubResearchStartButton = document.querySelector('#github-research-start');
const githubResearchStatus = document.querySelector('#github-research-status');
const repoWatchAddForm = document.querySelector('#repo-watch-add-form');
const repoWatchRepositoryInput = document.querySelector('#repo-watch-repository');
const repoWatchPollingForm = document.querySelector('#repo-watch-polling-form');
const repoWatchPollingEnabledInput = document.querySelector('#repo-watch-polling-enabled');
const repoWatchPollingIntervalInput = document.querySelector('#repo-watch-polling-interval');
const repoWatchPollingStatus = document.querySelector('#repo-watch-polling-status');
const repoWatchStatus = document.querySelector('#repo-watch-status');
const repoWatchList = document.querySelector('#repo-watch-list');
const repoWatchResult = document.querySelector('#repo-watch-result');
const binaryInspectionForm = document.querySelector('#binary-inspection-form');
const binaryInspectionFileInput = document.querySelector('#binary-inspection-file');
const binaryInspectionApprovedInput = document.querySelector('#binary-inspection-approved');
const binaryInspectionButton = document.querySelector('#binary-inspection-button');
const binaryInspectionStatus = document.querySelector('#binary-inspection-status');
const binaryInspectionResult = document.querySelector('#binary-inspection-result');
const browserInspectionForm = document.querySelector('#browser-inspection-form');
const browserInspectionUrlInput = document.querySelector('#browser-inspection-url');
const browserInspectionApprovedInput = document.querySelector('#browser-inspection-approved');
const browserInspectionButton = document.querySelector('#browser-inspection-button');
const browserInspectionStatus = document.querySelector('#browser-inspection-status');
const browserInspectionResult = document.querySelector('#browser-inspection-result');
const knowledgeSearchForm = document.querySelector('#knowledge-search-form');
const knowledgeQueryInput = document.querySelector('#knowledge-query');
const knowledgeStatus = document.querySelector('#knowledge-status');
const knowledgeResults = document.querySelector('#knowledge-results');
const taskCreateForm = document.querySelector('#task-create-form');
const taskRequestInput = document.querySelector('#task-request');
const taskStepsInput = document.querySelector('#task-steps');
const taskDraftButton = document.querySelector('#task-draft-button');
const taskCreateStatus = document.querySelector('#task-create-status');
const taskRefreshButton = document.querySelector('#task-refresh');
const taskList = document.querySelector('#task-list');
const taskDetail = document.querySelector('#task-detail');
let availableModels = [];
let defaultModel = '';
let activeSessionId = '';
let activeTaskId = '';
let activeJobId = '';
let jobsRefreshTimer = null;

const SESSION_STORAGE_KEY = 'deep-panda-ai.session-id';

function addMessage(text, role, isError = false) {
  const element = document.createElement('div');
  element.className = `message ${role}${isError ? ' error' : ''}`;
  element.textContent = text;
  messages.append(element);
  element.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function renderToolActivity(toolsUsed) {
  if (!Array.isArray(toolsUsed)) return;
  const toolLabels = {
    list_local_models: 'yerel modeller',
    list_workflows: 'çalışma akışları',
    get_workflow: 'çalışma akışı ayrıntısı',
    list_jobs: 'arka plan işleri',
    get_job: 'iş ayrıntısı',
    search_code_symbols: 'kod sembolleri',
    find_code_path: 'kod çağrı yolu',
  };
  const names = toolsUsed
    .filter((tool) => tool && typeof tool.name === 'string')
    .map((tool) => {
      const label = toolLabels[tool.name] || tool.name;
      return tool.status === 'error' ? `${label} (başarısız)` : label;
    });
  if (names.length) addMessage(`Salt okunur araçlar: ${names.join(', ')}`, 'tool-activity');
}

const intentLabels = {
  answer: 'Sohbette yanıtla',
  plan: 'Görev planı',
  research: 'Kaynak araştırması',
  learn: 'Öğrenme önerisi',
  action_request: 'Onaylı eylem isteği',
};

function updateLearningSaveAvailability() {
  learningSaveButton.disabled = !learningApprovedInput.checked
    || !learningTitleInput.value.trim()
    || !learningContentInput.value.trim();
}

function clearIntentPanel() {
  intentPanel.hidden = true;
  intentTaskDraftButton.hidden = true;
  intentTaskDraftButton.dataset.message = '';
  learningProposalForm.hidden = true;
  learningApprovedInput.checked = false;
  learningSaveStatus.textContent = '';
  updateLearningSaveAvailability();
}

function renderIntentRoute(route, sourceMessage) {
  if (!route) return;
  intentPanel.hidden = false;
  learningProposalForm.hidden = true;
  intentName.textContent = intentLabels[route.intent] || route.intent || 'Sınıflandırılamadı';
  const modelDetails = [];
  if (route.model) modelDetails.push(`yönlendirici ${route.model}`);
  if (route.completion_model && route.completion_model !== route.model) {
    modelDetails.push(`yanıt ${route.completion_model}`);
  }
  intentConfidence.textContent = route.routing_status === 'ready'
    ? `Güven ${(route.confidence * 100).toFixed(0)}%${modelDetails.length ? ` · ${modelDetails.join(' → ')}` : ''}`
    : 'Yönlendirme kullanılamadı';
  intentRationale.textContent = route.rationale || '';
  intentNextStep.textContent = route.next_step || '';
  intentStatus.textContent = route.routing_status === 'ready'
    ? (route.confidence < 0.6 ? 'Düşük güvenli öneri; eylem başlatılmadı.' : 'Öneri; hiçbir eylem başlatılmadı.')
    : 'Sohbet normal şekilde devam etti.';
  const canDraftTask = route.routing_status === 'ready'
    && ['plan', 'action_request'].includes(route.intent);
  intentTaskDraftButton.hidden = !canDraftTask;
  intentTaskDraftButton.dataset.message = canDraftTask ? sourceMessage : '';

  const proposal = route.intent === 'learn' ? route.learning_proposal : null;
  if (proposal) {
    learningTitleInput.value = proposal.title;
    learningProjectInput.value = proposal.project || '';
    learningCategoryInput.value = proposal.category || 'general';
    learningContentInput.value = proposal.content;
    learningApprovedInput.checked = false;
    learningSaveStatus.textContent = '';
    learningProposalForm.hidden = false;
    updateLearningSaveAvailability();
  } else if (route.intent === 'learn' && route.routing_status === 'ready') {
    intentStatus.textContent = 'Kalıcı bir öğrenme notu önerilemedi.';
  }
}

intentTaskDraftButton.addEventListener('click', () => {
  const request = intentTaskDraftButton.dataset.message;
  if (!request) return;
  taskRequestInput.value = request;
  taskStepsInput.value = '';
  intentPanel.hidden = true;
  openTasksButton.click();
  taskDraftButton.click();
});

closeIntentButton.addEventListener('click', clearIntentPanel);

for (const input of [learningApprovedInput, learningTitleInput, learningContentInput]) {
  input.addEventListener('input', updateLearningSaveAvailability);
  input.addEventListener('change', updateLearningSaveAvailability);
}

learningProposalForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  updateLearningSaveAvailability();
  if (learningSaveButton.disabled) return;
  if (!window.confirm('Düzenlenen öğrenme notu yerel hafızaya kaydedilsin mi?')) return;
  learningSaveButton.disabled = true;
  learningSaveStatus.textContent = 'Yerel hafızaya kaydediliyor...';
  try {
    const saved = await callMemory('remember', {
      approved: true,
      title: learningTitleInput.value.trim(),
      project: learningProjectInput.value.trim(),
      category: learningCategoryInput.value.trim() || 'general',
      content: learningContentInput.value.trim(),
      source: 'intent-router',
    });
    learningSaveStatus.textContent = `Kaydedildi · #${saved.id}`;
    learningApprovedInput.checked = false;
  } catch (error) {
    learningSaveStatus.textContent = error.message;
  } finally {
    updateLearningSaveAvailability();
  }
});

function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes <= 0) return '-';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(unitIndex > 0 ? 1 : 0)} ${units[unitIndex]}`;
}

function isEmbeddingModel(model) {
  const name = model.name || model.model || '';
  const family = model.details?.family || '';
  return /(^|[-_:])embed(ding)?([-_:]|$)/i.test(name) || /embed/i.test(family);
}

function renderModelOptions() {
  const selectedValue = modelSelect.value;
  const query = modelSearch.value.trim().toLocaleLowerCase('tr-TR');
  modelSelect.replaceChildren(new Option(
    defaultModel ? `Varsayılan · ${defaultModel}` : 'Varsayılan model',
    '',
  ));

  const matches = availableModels.filter((model) =>
    (model.name || model.model || '').toLocaleLowerCase('tr-TR').includes(query),
  );
  for (const model of matches) {
    const name = model.name || model.model;
    modelSelect.add(new Option(name, name));
  }

  if (selectedValue && !matches.some((model) => (model.name || model.model) === selectedValue)) {
    const selectedModel = availableModels.find((model) => (model.name || model.model) === selectedValue);
    if (selectedModel) modelSelect.add(new Option(`${selectedValue} · filtre dışında`, selectedValue));
  }
  const cloudOptions = window.DeepPandaCloud?.modelOptions?.() || [];
  if (cloudOptions.length) {
    const group = document.createElement('optgroup');
    group.label = 'Bulut API (yalnızca seçilirse gönderilir)';
    for (const option of cloudOptions) group.append(new Option(option.label, option.value));
    modelSelect.append(group);
  }
  modelSelect.value = selectedValue;
}

function updateModelDetails() {
  const selectedValue = modelSelect.value;
  const selectedModel = selectedValue
    ? availableModels.find((model) => (model.name || model.model) === selectedValue)
    : availableModels.find((model) => (model.name || model.model) === defaultModel);
  const details = selectedModel?.details || {};
  const modelName = selectedValue || defaultModel;

  selectedModelName.textContent = modelName || 'Varsayılan model';
  defaultBadge.hidden = Boolean(selectedValue);
  modelFamily.textContent = details.family || details.families?.[0] || '-';
  modelParameters.textContent = details.parameter_size || '-';
  modelQuantization.textContent = details.quantization_level || '-';
  modelSize.textContent = selectedModel ? formatBytes(selectedModel.size) : '-';

  if (!availableModels.length) {
    modelStatus.textContent = 'Model indirilmesi gerekiyor';
  } else if (modelName && modelName.startsWith('cloud:')) {
    modelStatus.textContent = 'Bulut API · soru seçili sağlayıcıya gönderilir';
  } else if (modelName && !selectedModel) {
    modelStatus.textContent = 'Seçili model kurulu değil';
  } else {
    modelStatus.textContent = `${availableModels.length} model hazır`;
  }
}

async function loadModels() {
  refreshModelsButton.disabled = true;
  modelStatus.textContent = 'Model listesi yenileniyor';
  try {
    const modelData = await fetch('/api/plugins/ollama/models');
    if (!modelData.ok) throw new Error(`Model servisi hazır değil (${modelData.status}).`);
    const payload = await modelData.json();
    if (
      !payload ||
      !Array.isArray(payload.models) ||
      typeof payload.default_model !== 'string' ||
      payload.models.some((model) => (
        !model ||
        typeof model !== 'object' ||
        ![model.name, model.model].some((name) => typeof name === 'string' && name.trim())
      ))
    ) {
      throw new Error('Model kataloğunun yanıt biçimi geçersiz.');
    }
    availableModels = payload.models.filter((model) => !isEmbeddingModel(model));
    defaultModel = payload.default_model;
    renderModelOptions();
    updateModelDetails();
  } catch (error) {
    modelStatus.textContent = `Model listesi alınamadı: ${error.message}`;
  } finally {
    refreshModelsButton.disabled = false;
  }
}

async function loadWorkflows() {
  workflowStatus.textContent = 'Çalışma modları yükleniyor...';
  try {
    const response = await fetch('/api/plugins/workflows/actions/catalog', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload: {} }),
    });
    if (!response.ok) throw new Error(`Sunucu ${response.status} yanıtı verdi.`);
    const catalog = await response.json();
    if (
      !Array.isArray(catalog.workflows) ||
      !catalog.workflows.length ||
      catalog.workflows.some((workflow) => (
        !workflow ||
        typeof workflow.id !== 'string' ||
        !workflow.id ||
        typeof workflow.name !== 'string' ||
        !workflow.name
      ))
    ) {
      throw new Error('Çalışma modu kataloğunun yanıt biçimi geçersiz.');
    }
    const selectedMode = workflowSelect.value || 'standard';
    const workflows = catalog.workflows;
    workflowSelect.replaceChildren();
    for (const workflow of workflows) {
      workflowSelect.add(new Option(workflow.name, workflow.id));
    }
    workflowSelect.value = workflows.some((workflow) => workflow.id === selectedMode)
      ? selectedMode
      : workflows.find((workflow) => workflow.id === 'standard')?.id || workflows[0]?.id || '';
    workflowStatus.textContent = '';
  } catch (error) {
    workflowStatus.textContent = `Çalışma modları yüklenemedi: ${error.message}`;
  }
}

async function loadStatus() {
  try {
    const response = await fetch('/api/health');
    const health = await response.json();
    connection.dataset.state = health.status === 'ok' ? 'ready' : 'error';
    connectionLabel.textContent = health.status === 'ok' ? 'AI servisi hazır' : 'AI servisi bekleniyor';
  } catch {
    connection.dataset.state = 'error';
    connectionLabel.textContent = 'Servis bağlantısı yok';
  }
  await loadModels();
  await loadWorkflows();
  await loadSessions();
}

async function loadSessions() {
  try {
    const response = await fetch('/api/chat/sessions?limit=20');
    if (!response.ok) throw new Error('Oturum listesi alınamadı');
    const result = await response.json();
    const sessions = result.sessions || [];
    const storedId = localStorage.getItem(SESSION_STORAGE_KEY) || '';
    sessionSelect.replaceChildren(new Option('Yeni sohbet', ''));
    for (const session of sessions) {
      sessionSelect.add(new Option(session.title || 'Sohbet', session.session_id));
    }
    activeSessionId = sessions.some((session) => session.session_id === storedId) ? storedId : '';
    sessionSelect.value = activeSessionId;
    deleteSessionButton.disabled = !activeSessionId;
    if (activeSessionId) await loadSessionMessages(activeSessionId);
  } catch (error) {
    sessionStatus.textContent = error.message;
  }
}

async function loadSessionMessages(sessionId) {
  sessionStatus.textContent = 'Sohbet geçmişi yükleniyor...';
  try {
    const response = await fetch(`/api/chat/sessions/${encodeURIComponent(sessionId)}/messages`);
    if (!response.ok) throw new Error('Sohbet geçmişi alınamadı');
    const result = await response.json();
    messages.replaceChildren();
    for (const item of result.messages || []) addMessage(item.content, item.role);
    welcome.hidden = Boolean(result.messages?.length);
    sessionStatus.textContent = `${result.messages?.length || 0} mesaj yüklendi`;
  } catch (error) {
    sessionStatus.textContent = error.message;
  }
}

function startNewChat() {
  activeSessionId = '';
  sessionSelect.value = '';
  deleteSessionButton.disabled = true;
  localStorage.removeItem(SESSION_STORAGE_KEY);
  messages.replaceChildren();
  welcome.hidden = false;
  sessionStatus.textContent = 'Yeni sohbet';
  messageInput.focus();
}

function renderDiagnostics(report) {
  const summary = report.summary || {};
  const suffix = report.truncated ? ' · Limit nedeniyle tarama kısaltıldı' : '';
  diagnosticsSummary.textContent = `${report.scanned_files || 0} dosya tarandı · ${summary.errors || 0} hata · ${summary.warnings || 0} uyarı${suffix}`;
  diagnosticsResults.replaceChildren();

  if (!report.diagnostics?.length) {
    const empty = document.createElement('p');
    empty.className = 'diagnostics-empty';
    empty.textContent = 'Analiz edilen dosyalarda statik hata bulunmadı.';
    diagnosticsResults.append(empty);
    return;
  }

  for (const diagnostic of report.diagnostics) {
    const severity = ['error', 'warning', 'info'].includes(diagnostic.severity)
      ? diagnostic.severity
      : 'warning';
    const item = document.createElement('article');
    item.className = `diagnostic-item severity-${severity}`;

    const header = document.createElement('div');
    header.className = 'diagnostic-item-header';
    const location = document.createElement('code');
    const line = diagnostic.line ? `:${diagnostic.line}${diagnostic.column ? `:${diagnostic.column}` : ''}` : '';
    location.textContent = `${diagnostic.path || 'workspace'}${line}`;
    const code = document.createElement('span');
    code.className = 'diagnostic-code';
    code.textContent = diagnostic.code || severity;
    header.append(location, code);

    const message = document.createElement('p');
    message.textContent = diagnostic.message || 'Tanı bilgisi yok.';
    item.append(header, message);
    diagnosticsResults.append(item);
  }
}

function updateMemorySaveAvailability() {
  memorySaveButton.disabled = !memoryApprovedInput.checked
    || !memoryTitleInput.value.trim()
    || !memoryContentInput.value.trim();
}

function renderMemories(items) {
  memoryResults.replaceChildren();
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'diagnostics-empty';
    empty.textContent = 'Eşleşen yerel hafıza notu yok.';
    memoryResults.append(empty);
    return;
  }

  for (const memory of items) {
    const item = document.createElement('article');
    item.className = 'memory-item';
    const heading = document.createElement('div');
    heading.className = 'memory-item-heading';
    const title = document.createElement('strong');
    title.textContent = memory.title;
    const metadata = document.createElement('span');
    metadata.textContent = [memory.project, memory.category, memory.source, memory.created_at].filter(Boolean).join(' · ');
    heading.append(title, metadata);
    const content = document.createElement('p');
    content.textContent = memory.content;
    item.append(heading, content);
    memoryResults.append(item);
  }
}

async function readApiJson(response, operation) {
  let result;
  try {
    result = await response.json();
  } catch {
    const status = response.ok ? '' : ` · HTTP ${response.status}`;
    throw new Error(`${operation} yanıtı geçerli JSON değil${status}.`);
  }
  if (!result || typeof result !== 'object' || Array.isArray(result)) {
    const status = response.ok ? '' : ` · HTTP ${response.status}`;
    throw new Error(`${operation} yanıt biçimi geçersiz${status}.`);
  }
  return result;
}

async function callMemory(action, payload) {
  const response = await fetch(`/api/plugins/memory/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Hafıza işlemi tamamlanamadı.');
  return result;
}

async function callCodeGraph(action, payload = {}) {
  const response = await fetch(`/api/plugins/codegraph/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Kod grafı işlemi tamamlanamadı.');
  return result;
}

async function callDocuments(action, payload = {}) {
  const response = await fetch(`/api/plugins/documents/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Belge işlemi tamamlanamadı.');
  return result;
}

async function callTasks(action, payload = {}) {
  const response = await fetch(`/api/plugins/tasks/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Görev işlemi tamamlanamadı.');
  return result;
}

async function callTaskAssistant(action, payload = {}) {
  const response = await fetch(`/api/plugins/task_assistant/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Yerel görev taslağı oluşturulamadı.');
  return result;
}

async function callJobs(action, payload = {}) {
  const response = await fetch(`/api/plugins/jobs/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Job işlemi tamamlanamadı.');
  return result;
}

async function callResearch(action, payload = {}) {
  const response = await fetch(`/api/plugins/research/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Araştırma işi başlatılamadı.');
  return result;
}

async function callRepoWatch(action, payload = {}) {
  const response = await fetch(`/api/plugins/repo_watch/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await readApiJson(response, 'Repository takibi');
  if (!response.ok) throw new Error(result.detail || `Repository takibi başarısız · HTTP ${response.status}`);
  return result;
}

async function callAnalysis(action, payload = {}) {
  const response = await fetch(`/api/plugins/analysis/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await readApiJson(response, 'Statik analiz');
  if (!response.ok) throw new Error(result.detail || `Statik analiz başarısız · HTTP ${response.status}`);
  return result;
}

async function callBrowserInspection(action, payload = {}) {
  const response = await fetch(`/api/plugins/browser/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await readApiJson(response, 'Browser snapshot');
  if (!response.ok) throw new Error(result.detail || `Browser snapshot başarısız · HTTP ${response.status}`);
  return result;
}

async function callKnowledge(action, payload = {}) {
  const response = await fetch(`/api/plugins/knowledge/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await readApiJson(response, 'Yerel anlamsal arama');
  if (!response.ok) throw new Error(result.detail || `Yerel anlamsal arama başarısız · HTTP ${response.status}`);
  return result;
}

function updateBinaryInspectionAvailability() {
  binaryInspectionButton.disabled = !binaryInspectionApprovedInput.checked || !binaryInspectionFileInput.files?.length;
}

async function fileToBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  const chunks = [];
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    chunks.push(String.fromCharCode(...bytes.subarray(offset, offset + 0x8000)));
  }
  return btoa(chunks.join(''));
}

function renderBinaryInspection(result) {
  binaryInspectionResult.replaceChildren();
  const metadata = result.metadata;
  const summary = document.createElement('p');
  summary.className = 'repo-watch-metadata';
  summary.textContent = metadata.format === 'Mach-O Universal'
    ? `${metadata.format} · ${metadata.slice_count} slices · ${result.size_bytes} byte · SHA-256 ${result.sha256}`
    : `${metadata.format} · ${metadata.architecture} · ${metadata.bits}-bit · ${result.size_bytes} byte · SHA-256 ${result.sha256}`;
  binaryInspectionResult.append(summary);
  const slices = metadata.slices || [metadata];
  for (const slice of slices) {
    if (metadata.slices) {
      const sliceHeading = document.createElement('p');
      sliceHeading.className = 'repo-watch-metadata';
      sliceHeading.textContent = `${slice.architecture} · ${slice.bits}-bit`;
      binaryInspectionResult.append(sliceHeading);
    }
    const sections = document.createElement('details');
    const sectionSummary = document.createElement('summary');
    sectionSummary.textContent = `Sections (${slice.sections.length})`;
    const sectionList = document.createElement('ul');
    for (const section of slice.sections) {
      const item = document.createElement('li');
      item.textContent = `${section.name} · virtual ${section.virtual_size} · file ${section.file_size}${section.executable === null ? '' : ` · executable ${section.executable}`}`;
      sectionList.append(item);
    }
    sections.append(sectionSummary, sectionList);
    binaryInspectionResult.append(sections);
    const imports = slice.imports || slice.libraries || [];
    const importDetails = document.createElement('details');
    const importSummary = document.createElement('summary');
    importSummary.textContent = `Import libraries (${imports.length})`;
    const importList = document.createElement('ul');
    for (const entry of imports.slice(0, 100)) {
      const item = document.createElement('li');
      item.textContent = typeof entry === 'string'
        ? entry
        : `${entry.name} · ${(entry.symbols || []).slice(0, 20).join(', ')}`;
      importList.append(item);
    }
    importDetails.append(importSummary, importList);
    binaryInspectionResult.append(importDetails);

    const analysis = slice.static_analysis;
    if (!analysis) continue;
    const renderFunctionRecords = (label, records, truncated) => {
      const details = document.createElement('details');
      const detailsSummary = document.createElement('summary');
      detailsSummary.textContent = `${label} (${records.length})${truncated ? ' · truncated' : ''}`;
      const list = document.createElement('ul');
      for (const record of records) {
        const item = document.createElement('li');
        item.textContent = `${record.name || '(unnamed)'} · ${record.address} · ${record.size} bytes`;
        list.append(item);
      }
      details.append(detailsSummary, list);
      binaryInspectionResult.append(details);
    };
    renderFunctionRecords('Functions', analysis.functions, analysis.functions_truncated);
    renderFunctionRecords('Exports', analysis.exports, analysis.exports_truncated);
    const disassembly = document.createElement('details');
    const disassemblySummary = document.createElement('summary');
    disassemblySummary.textContent = analysis.supported
      ? `Disassembly · ${analysis.architecture} · entry ${analysis.entrypoint || 'n/a'} · ${analysis.instructions.length} instructions${analysis.disassembly_truncated ? ' · truncated' : ''}`
      : `Disassembly unavailable · ${analysis.architecture}`;
    disassembly.append(disassemblySummary);
    if (analysis.supported) {
      const listing = document.createElement('pre');
      listing.className = 'binary-disassembly';
      listing.textContent = analysis.instructions.map((instruction) => (
        `${instruction.address.padEnd(14)} ${instruction.bytes.padEnd(16)} ${instruction.mnemonic} ${instruction.operands}`
      )).join('\n');
      disassembly.append(listing);
    } else {
      const reason = document.createElement('p');
      reason.className = 'repo-watch-metadata';
      reason.textContent = analysis.reason;
      disassembly.append(reason);
    }
    binaryInspectionResult.append(disassembly);

    const strings = document.createElement('details');
    const stringsSummary = document.createElement('summary');
    stringsSummary.textContent = `Strings (${analysis.strings.length})${analysis.strings_truncated ? ' · truncated' : ''}`;
    const stringsList = document.createElement('ul');
    for (const entry of analysis.strings) {
      const item = document.createElement('li');
      item.textContent = `${entry.offset} · ${entry.encoding} · ${entry.value}`;
      stringsList.append(item);
    }
    strings.append(stringsSummary, stringsList);
    binaryInspectionResult.append(strings);
  }
  binaryInspectionStatus.textContent = 'Statik disassembly ve metadata tamamlandı · dosya çalıştırılmadı.';
}

const jobStatusLabels = {
  queued: 'Kuyrukta',
  running: 'Çalışıyor',
  cancel_requested: 'İptal bekleniyor',
  cancelled: 'İptal edildi',
  succeeded: 'Tamamlandı',
  failed: 'Başarısız',
};

function renderJobDetails(job) {
  jobDetail.replaceChildren();
  const heading = document.createElement('div');
  heading.className = 'task-detail-heading';
  const title = document.createElement('strong');
  title.textContent = `${job.kind} · ${job.job_id}`;
  const status = document.createElement('span');
  status.textContent = jobStatusLabels[job.status] || job.status;
  heading.append(title, status);
  jobDetail.append(heading);

  const progress = document.createElement('progress');
  progress.max = 100;
  progress.value = job.progress;
  progress.setAttribute('aria-label', `İş ilerlemesi yüzde ${job.progress}`);
  const progressLabel = document.createElement('span');
  progressLabel.className = 'job-progress-label';
  progressLabel.textContent = `%${job.progress}`;
  jobDetail.append(progress, progressLabel);

  if (job.error) {
    const error = document.createElement('p');
    error.className = 'task-test-failed';
    error.textContent = job.error;
    jobDetail.append(error);
  }
  if (job.result !== null) {
    const resultHeading = document.createElement('h4');
    resultHeading.textContent = 'Sonuç';
    const result = document.createElement('pre');
    result.className = 'task-diff';
    result.textContent = JSON.stringify(job.result, null, 2);
    jobDetail.append(resultHeading, result);
  }

  const actions = document.createElement('div');
  actions.className = 'job-actions';
  if (['queued', 'running'].includes(job.status)) {
    const cancelButton = document.createElement('button');
    cancelButton.className = 'document-delete-button';
    cancelButton.type = 'button';
    cancelButton.textContent = 'İşi iptal et';
    cancelButton.addEventListener('click', async () => {
      if (!window.confirm(`${job.kind} işi iptal edilsin mi? Çalışan iş worker iptal isteğini gözlemlediğinde duracak.`)) return;
      cancelButton.disabled = true;
      try {
        await callJobs('cancel', { job_id: job.job_id, approved: true });
        await loadJobDetails(job.job_id);
        await loadJobs();
      } catch (error) {
        cancelButton.disabled = false;
        jobsStatus.textContent = error.message;
      }
    });
    actions.append(cancelButton);
  }
  if (['failed', 'cancelled'].includes(job.status)) {
    const retryButton = document.createElement('button');
    retryButton.className = 'task-step-action';
    retryButton.type = 'button';
    retryButton.textContent = 'Onayla ve yeniden kuyruğa al';
    retryButton.addEventListener('click', async () => {
      if (!window.confirm(`${job.kind} işi aynı girdilerle yeniden kuyruğa alınsın mı?`)) return;
      retryButton.disabled = true;
      try {
        const retry = await callJobs('retry', { job_id: job.job_id, approved: true });
        await loadJobs();
        await loadJobDetails(retry.job_id);
      } catch (error) {
        retryButton.disabled = false;
        jobsStatus.textContent = error.message;
      }
    });
    actions.append(retryButton);
  }
  if (job.status === 'succeeded' && ['research', 'github_research'].includes(job.kind)) {
    const savedEvent = job.events?.find((event) => event.event === 'memory_saved');
    const memoryButton = document.createElement('button');
    memoryButton.className = 'task-step-action';
    memoryButton.type = 'button';
    memoryButton.textContent = savedEvent
      ? `Hafızaya kaydedildi · #${savedEvent.detail.memory_id}`
      : 'Onayla ve hafızaya kaydet';
    memoryButton.disabled = Boolean(savedEvent);
    if (!savedEvent) {
      memoryButton.addEventListener('click', async () => {
        if (!window.confirm('Araştırma özeti ve kaynak URL’leri yerel proje hafızasına kaydedilsin mi?')) return;
        memoryButton.disabled = true;
        try {
          const result = await callResearch('save_to_memory', { job_id: job.job_id, approved: true });
          jobsStatus.textContent = result.truncated
            ? `Araştırma hafızaya kaydedildi · #${result.memory_id} · içerik 10.000 karakterde kesildi.`
            : `Araştırma hafızaya kaydedildi · #${result.memory_id}`;
          await loadJobDetails(job.job_id);
        } catch (error) {
          memoryButton.disabled = false;
          jobsStatus.textContent = error.message;
        }
      });
    }
    actions.append(memoryButton);
  }
  if (actions.childElementCount) jobDetail.append(actions);

  if (job.events?.length) {
    const eventsHeading = document.createElement('h4');
    eventsHeading.textContent = 'İş geçmişi';
    const events = document.createElement('ol');
    events.className = 'task-history';
    for (const event of job.events) {
      const item = document.createElement('li');
      const detail = Object.values(event.detail || {}).filter((value) => value !== '').join(' · ');
      item.textContent = `${event.event}${detail ? ` · ${detail}` : ''} · ${event.created_at}`;
      events.append(item);
    }
    jobDetail.append(eventsHeading, events);
  }
}

async function loadJobDetails(jobId) {
  activeJobId = jobId;
  jobDetail.hidden = false;
  jobDetail.textContent = 'Job ayrıntıları yükleniyor...';
  try {
    const result = await callJobs('get', { job_id: jobId });
    renderJobDetails(result.job);
  } catch (error) {
    jobDetail.textContent = error.message;
  }
}

async function loadJobs() {
  jobsList.replaceChildren();
  jobsStatus.textContent = 'Job kayıtları yükleniyor...';
  try {
    const result = await callJobs('list', { limit: 50 });
    const jobs = result.jobs || [];
    jobsStatus.textContent = `${jobs.length} job kaydı`;
    if (!jobs.length) {
      const empty = document.createElement('p');
      empty.className = 'diagnostics-empty';
      empty.textContent = 'Henüz arka plan işi yok.';
      jobsList.append(empty);
      return;
    }
    for (const job of jobs) {
      const item = document.createElement('article');
      item.className = 'memory-item job-item';
      const heading = document.createElement('div');
      heading.className = 'memory-item-heading';
      const title = document.createElement('strong');
      title.textContent = job.kind;
      const metadata = document.createElement('span');
      metadata.textContent = `${jobStatusLabels[job.status] || job.status} · ${job.progress}% · ${job.updated_at}`;
      heading.append(title, metadata);
      const progress = document.createElement('progress');
      progress.max = 100;
      progress.value = job.progress;
      progress.setAttribute('aria-label', `${job.kind} ${job.progress}%`);
      const detailsButton = document.createElement('button');
      detailsButton.className = 'task-step-action';
      detailsButton.type = 'button';
      detailsButton.textContent = 'Ayrıntılar';
      detailsButton.addEventListener('click', () => loadJobDetails(job.job_id));
      item.append(heading, progress, detailsButton);
      jobsList.append(item);
    }
  } catch (error) {
    jobsStatus.textContent = error.message;
  }
}

async function refreshJobCenter() {
  await Promise.all([loadJobs(), ...(activeJobId ? [loadJobDetails(activeJobId)] : [])]);
}

function stopJobPolling() {
  if (jobsRefreshTimer !== null) window.clearInterval(jobsRefreshTimer);
  jobsRefreshTimer = null;
}

async function callWorkspace(action, payload = {}) {
  const response = await fetch(`/api/plugins/workspace/actions/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ payload }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.detail || 'Workspace işlemi tamamlanamadı.');
  return result;
}

const taskStatusLabels = {
  plan_only: 'Onay bekliyor',
  approved: 'Onaylandı',
  in_progress: 'Devam ediyor',
  completed: 'Tamamlandı',
  blocked: 'Engellendi',
  pending: 'Bekliyor',
};

function createTaskWorkspaceForm(task, step) {
  const form = document.createElement('form');
  form.className = 'task-workspace-form';
  const heading = document.createElement('h5');
  heading.textContent = 'Workspace dosya değişikliği';
  const pathInput = document.createElement('input');
  pathInput.maxLength = 500;
  pathInput.placeholder = 'Göreli dosya yolu';
  pathInput.required = true;
  const contextPathsInput = document.createElement('textarea');
  contextPathsInput.maxLength = 1_500;
  contextPathsInput.rows = 2;
  contextPathsInput.placeholder = 'Ek bağlam dosyaları (isteğe bağlı, her satıra bir yol, en fazla 3)';
  const instructionInput = document.createElement('textarea');
  instructionInput.maxLength = 2_000;
  instructionInput.rows = 2;
  instructionInput.placeholder = 'Bu adım için yerel modele ek yönerge (isteğe bağlı)';
  const draftButton = document.createElement('button');
  draftButton.className = 'task-step-action';
  draftButton.type = 'button';
  draftButton.textContent = 'Yerel modelle taslak üret';
  const contentInput = document.createElement('textarea');
  contentInput.maxLength = 1_000_000;
  contentInput.rows = 5;
  contentInput.placeholder = 'Yeni dosya içeriği veya model taslağı';
  contentInput.required = true;
  const previewButton = document.createElement('button');
  previewButton.className = 'task-step-action';
  previewButton.type = 'submit';
  previewButton.textContent = 'Diff önizle';
  const writeButton = document.createElement('button');
  writeButton.className = 'memory-save-button';
  writeButton.type = 'button';
  writeButton.textContent = 'Onayla ve yaz';
  writeButton.hidden = true;
  const status = document.createElement('p');
  status.className = 'memory-status';
  status.setAttribute('role', 'status');
  const diff = document.createElement('pre');
  diff.className = 'task-diff';
  diff.hidden = true;
  const evidencePanel = document.createElement('details');
  evidencePanel.className = 'task-evidence';
  evidencePanel.hidden = true;
  const evidenceHeading = document.createElement('summary');
  evidenceHeading.textContent = 'Kaynak kanıtları';
  const evidenceList = document.createElement('ol');
  evidenceList.className = 'task-evidence-list';
  evidencePanel.append(evidenceHeading, evidenceList);
  form.append(heading, pathInput, contextPathsInput, instructionInput, draftButton, contentInput, previewButton, writeButton, status, diff, evidencePanel);

  let previewSnapshot = null;
  const invalidatePreview = () => {
    previewSnapshot = null;
    diff.hidden = true;
    writeButton.hidden = true;
    evidencePanel.hidden = true;
    evidencePanel.open = false;
    evidenceList.replaceChildren();
    status.textContent = '';
  };
  pathInput.addEventListener('input', invalidatePreview);
  contextPathsInput.addEventListener('input', invalidatePreview);
  instructionInput.addEventListener('input', invalidatePreview);
  contentInput.addEventListener('input', invalidatePreview);
  modelSelect.addEventListener('change', invalidatePreview);

  draftButton.addEventListener('click', async () => {
    const path = pathInput.value.trim();
    if (!path) {
      pathInput.focus();
      status.textContent = 'Önce workspace içindeki dosya yolunu seç.';
      return;
    }
    const contextPaths = [...new Set(contextPathsInput.value.split(/\r?\n/).map((value) => value.trim()).filter(Boolean))];
    if (contextPaths.length > 3 || contextPaths.includes(path)) {
      status.textContent = 'En fazla 3 farklı bağlam yolu gir; hedef dosyayı tekrar ekleme.';
      return;
    }
    if (!window.confirm(`${path} dosyası ve görev adımı yerel Ollama modeline gönderilip yalnızca taslak üretilsin mi? Dosyaya yazılmaz.`)) return;
    draftButton.disabled = true;
    status.textContent = 'Seçilen dosya yerel modelle analiz ediliyor...';
    try {
      const proposal = await callTaskAssistant('propose_change', {
        approved: true,
        task_id: task.task_id,
        step_index: step.step_index,
        path,
        context_paths: contextPaths,
        instruction: instructionInput.value.trim(),
        model: modelSelect.value || null,
      });
      invalidatePreview();
      contentInput.value = proposal.content;
      const evidenceItems = Array.isArray(proposal.evidence) ? proposal.evidence : [];
      for (const item of evidenceItems) {
        const entry = document.createElement('li');
        const reference = document.createElement('strong');
        reference.className = 'task-evidence-reference';
        reference.textContent = `${item.path}:L${item.start_line}-${item.end_line} -> taslak satırı ${item.replacement_line}`;
        const quote = document.createElement('pre');
        quote.className = 'task-evidence-quote';
        quote.textContent = item.quote;
        entry.append(reference, quote);
        evidenceList.append(entry);
      }
      evidencePanel.hidden = evidenceItems.length === 0;
      status.textContent = `${proposal.model} taslağı · ${proposal.summary} · Dosyaya yazılmadı; önce diff’i incele.`;
      contentInput.focus();
    } catch (error) {
      status.textContent = error.message;
    } finally {
      draftButton.disabled = false;
    }
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const path = pathInput.value.trim();
    const content = contentInput.value;
    if (!path || !content.trim()) return;
    previewButton.disabled = true;
    status.textContent = 'Salt okunur diff hazırlanıyor...';
    try {
      const result = await callWorkspace('preview_write', { path, content });
      previewSnapshot = { path, content, expectedSha256: result.expected_sha256 };
      diff.textContent = result.diff || 'Dosya içeriğinde değişiklik yok.';
      diff.hidden = false;
      writeButton.hidden = false;
      status.textContent = `${result.status === 'new' ? 'Yeni dosya' : 'Mevcut dosya'} · yazma henüz yapılmadı.`;
    } catch (error) {
      status.textContent = error.message;
    } finally {
      previewButton.disabled = false;
    }
  });

  writeButton.addEventListener('click', async () => {
    if (!previewSnapshot || previewSnapshot.path !== pathInput.value.trim() || previewSnapshot.content !== contentInput.value) {
      invalidatePreview();
      status.textContent = 'İçerik değişti; önce diff’i yeniden önizle.';
      return;
    }
    if (!window.confirm(`Önizlenen diff’i ${previewSnapshot.path} dosyasına yazmak istiyor musun? Bu işlem backup oluşturur.`)) return;
    writeButton.disabled = true;
    status.textContent = 'Onaylı yazma uygulanıyor...';
    let writeResult;
    try {
      writeResult = await callWorkspace('write', {
        approved: true,
        path: previewSnapshot.path,
        content: previewSnapshot.content,
        expected_sha256: previewSnapshot.expectedSha256,
      });
      await callTasks('record_workspace_write', {
        task_id: task.task_id,
        step_index: step.step_index,
        path: writeResult.path,
        backup_id: writeResult.backup_id,
        approved: true,
      });
      await loadTaskDetails(task.task_id);
      await loadTasks();
    } catch (error) {
      if (writeResult?.backup_id) {
        status.textContent = `Dosya yazıldı; görev geçmişine backup kaydı eklenemedi. Backup: ${writeResult.backup_id}. ${error.message}`;
      } else {
        status.textContent = error.message;
      }
      writeButton.disabled = false;
    }
  });
  return form;
}

function createTaskTestForm(task, step) {
  const form = document.createElement('form');
  form.className = 'task-test-form';
  const heading = document.createElement('h5');
  heading.textContent = 'Test komutu';
  const commandInput = document.createElement('input');
  commandInput.maxLength = 1_000;
  commandInput.value = 'python -m unittest discover -s backend/tests -t backend';
  commandInput.setAttribute('aria-label', 'Çalıştırılacak test komutu');
  commandInput.required = true;
  const runButton = document.createElement('button');
  runButton.className = 'task-step-action';
  runButton.type = 'submit';
  runButton.textContent = 'Testi çalıştır';
  const status = document.createElement('p');
  status.className = 'memory-status';
  status.setAttribute('role', 'status');
  const output = document.createElement('pre');
  output.className = 'task-diff';
  output.hidden = true;
  form.append(heading, commandInput, runButton, status, output);

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const rawCommand = commandInput.value.trim();
    if (!rawCommand) return;
    let command;
    try {
      command = rawCommand.startsWith('[') ? JSON.parse(rawCommand) : rawCommand.split(/\s+/);
    } catch {
      status.textContent = 'Komut JSON array biçiminde geçerli değil.';
      return;
    }
    if (!Array.isArray(command) || !command.length || command.some((part) => typeof part !== 'string')) {
      status.textContent = 'Komut boş olmayan metin argümanlarından oluşmalı.';
      return;
    }
    if (!window.confirm(`Onaylı test komutu shell kullanmadan çalıştırılacak:\n${command.join(' ')}`)) return;
    runButton.disabled = true;
    status.textContent = 'Test komutu çalışıyor...';
    try {
      const result = await callWorkspace('run', { approved: true, command, timeout_seconds: 120 });
      const testOutput = `${result.stdout || ''}${result.stderr ? `\n${result.stderr}` : ''}`.slice(-4_000);
      await callTasks('record_test_run', {
        task_id: task.task_id,
        step_index: step.step_index,
        command,
        passed: result.passed,
        returncode: result.returncode,
        output: testOutput,
        approved: true,
      });
      status.textContent = result.passed ? 'Testler başarılı.' : `Testler başarısız · çıkış kodu ${result.returncode}`;
      output.textContent = testOutput || 'Komut çıktı üretmedi.';
      output.hidden = false;
      await loadTaskDetails(task.task_id);
      await loadTasks();
    } catch (error) {
      status.textContent = error.message;
      runButton.disabled = false;
    }
  });
  return form;
}

async function loadTaskDetails(taskId) {
  activeTaskId = taskId;
  taskDetail.hidden = false;
  taskDetail.textContent = 'Görev ayrıntıları yükleniyor...';
  try {
    const result = await callTasks('get', { task_id: taskId });
    renderTaskDetails(result.task);
  } catch (error) {
    taskDetail.textContent = error.message;
  }
}

function renderTaskDetails(task) {
  taskDetail.replaceChildren();
  const heading = document.createElement('div');
  heading.className = 'task-detail-heading';
  const request = document.createElement('strong');
  request.textContent = task.request;
  const status = document.createElement('span');
  status.textContent = taskStatusLabels[task.status] || task.status;
  heading.append(request, status);
  taskDetail.append(heading);

  const verification = document.createElement('section');
  verification.className = 'task-verification';
  const verifyButton = document.createElement('button');
  verifyButton.className = 'task-step-action';
  verifyButton.type = 'button';
  verifyButton.textContent = 'Görevi kanıta göre doğrula';
  const verificationResult = document.createElement('div');
  verificationResult.className = 'task-verification-result';
  verificationResult.setAttribute('role', 'status');
  verifyButton.addEventListener('click', async () => {
    verifyButton.disabled = true;
    verificationResult.textContent = 'Adımlar, test kayıtları ve son yazımlar denetleniyor...';
    verificationResult.dataset.state = 'checking';
    try {
      const report = await callTasks('verify', { task_id: task.task_id });
      const evidence = report.evidence;
      const summary = `${evidence.completed_steps}/${evidence.total_steps} adım · ${evidence.passing_test_run_count}/${evidence.test_run_count} başarılı test · ${evidence.active_workspace_write_count} aktif yazım`;
      const reasonLabels = {
        'Task plan has not been approved.': 'Plan henüz onaylanmadı.',
        'One or more task steps are not completed.': 'Bazı adımlar tamamlanmadı.',
        'No successful test run is recorded.': 'Başarılı test kaydı bulunmuyor.',
        'The latest recorded test run failed.': 'Son test çalıştırması başarısız.',
        'A successful test run after the latest workspace write or rollback is required.': 'Son dosya değişikliği veya geri alma işleminden sonra başarılı test çalıştırılmalı.',
      };
      const reasons = report.reasons.length
        ? ` · ${report.reasons.map((reason) => reasonLabels[reason] || reason).join(' ')}`
        : '';
      verificationResult.textContent = `${report.verified ? 'Kanıt doğrulandı' : 'Henüz doğrulanmadı'} · ${summary}${reasons}`;
      verificationResult.dataset.state = report.verified ? 'verified' : 'pending';
    } catch (error) {
      verificationResult.textContent = error.message;
      verificationResult.dataset.state = 'error';
    } finally {
      verifyButton.disabled = false;
    }
  });
  verification.append(verifyButton, verificationResult);
  taskDetail.append(verification);

  if (task.status === 'plan_only') {
    const approveButton = document.createElement('button');
    approveButton.className = 'memory-save-button';
    approveButton.type = 'button';
    approveButton.textContent = 'Planı onayla';
    approveButton.addEventListener('click', async () => {
      if (!window.confirm('Bu planı onaylayıp adım ilerlemesini açmak istiyor musun?')) return;
      approveButton.disabled = true;
      try {
        await callTasks('approve', { task_id: task.task_id, approved: true });
        await loadTaskDetails(task.task_id);
        await loadTasks();
      } catch (error) {
        approveButton.disabled = false;
        status.textContent = error.message;
      }
    });
    taskDetail.append(approveButton);
  }

  const stepsHeading = document.createElement('h4');
  stepsHeading.textContent = 'Adımlar';
  taskDetail.append(stepsHeading);
  for (const step of task.steps || []) {
    const item = document.createElement('article');
    item.className = 'task-step';
    const stepHeading = document.createElement('div');
    stepHeading.className = 'task-detail-heading';
    const title = document.createElement('strong');
    title.textContent = `${step.step_index + 1}. ${step.title}`;
    const stepStatus = document.createElement('span');
    stepStatus.textContent = taskStatusLabels[step.status] || step.status;
    stepHeading.append(title, stepStatus);
    item.append(stepHeading);

    if (step.evidence) {
      const evidence = document.createElement('p');
      evidence.className = 'task-evidence';
      evidence.textContent = `Kanıt: ${step.evidence}`;
      item.append(evidence);
    }

    const nextStatuses = task.approved ? {
      pending: [{ status: 'in_progress', label: 'Başlat' }, { status: 'blocked', label: 'Engellendi' }],
      in_progress: [{ status: 'completed', label: 'Tamamla' }, { status: 'blocked', label: 'Engellendi' }],
      blocked: [{ status: 'in_progress', label: 'Yeniden dene' }],
      completed: [],
    } : {};
    for (const next of nextStatuses[step.status] || []) {
      const evidenceInput = document.createElement('textarea');
      evidenceInput.maxLength = 1000;
      evidenceInput.rows = 2;
      evidenceInput.placeholder = next.status === 'completed' ? 'Tamamlanma kanıtı gerekli' : next.status === 'blocked' ? 'Engel nedeni gerekli' : 'İlerleme notu (isteğe bağlı)';
      item.append(evidenceInput);
      const updateButton = document.createElement('button');
      updateButton.className = next.status === 'completed' ? 'memory-save-button' : 'task-step-action';
      updateButton.type = 'button';
      updateButton.textContent = next.label;
      updateButton.addEventListener('click', async () => {
        const evidence = evidenceInput.value.trim();
        if (['completed', 'blocked'].includes(next.status) && !evidence) {
          evidenceInput.focus();
          return;
        }
        if (!window.confirm(`“${step.title}” adımını “${taskStatusLabels[next.status]}” durumuna geçirmek istiyor musun?`)) return;
        updateButton.disabled = true;
        try {
          await callTasks('update_step', {
            task_id: task.task_id,
            step_index: step.step_index,
            status: next.status,
            evidence,
            approved: true,
          });
          await loadTaskDetails(task.task_id);
          await loadTasks();
        } catch (error) {
          updateButton.disabled = false;
          stepStatus.textContent = error.message;
        }
      });
      item.append(updateButton);
    }
    if (task.approved && step.status === 'in_progress') {
      item.append(createTaskWorkspaceForm(task, step));
      item.append(createTaskTestForm(task, step));
    }
    taskDetail.append(item);
  }

  if (task.events?.length) {
    const historyHeading = document.createElement('h4');
    historyHeading.textContent = 'İşlem geçmişi';
    const history = document.createElement('ol');
    history.className = 'task-history';
    const rolledBackBackups = new Set(
      task.events
        .filter((event) => event.action === 'workspace_rollback')
        .map((event) => event.detail.backup_id),
    );
    for (const event of task.events) {
      const entry = document.createElement('li');
      const stepLabel = event.step_index === null ? '' : ` · adım ${event.step_index + 1}`;
      const pathLabel = event.detail.path ? ` · ${event.detail.path}` : '';
      entry.append(document.createTextNode(`${event.action}${stepLabel}${pathLabel} · ${event.created_at}`));
      if (event.action === 'workspace_write' && !rolledBackBackups.has(event.detail.backup_id)) {
        const rollbackButton = document.createElement('button');
        rollbackButton.className = 'task-step-action';
        rollbackButton.type = 'button';
        rollbackButton.textContent = 'Geri al';
        rollbackButton.addEventListener('click', async () => {
          if (!window.confirm(`${event.detail.path} dosyasını bu backup ile geri almak istiyor musun?`)) return;
          rollbackButton.disabled = true;
          try {
            await callWorkspace('rollback', { approved: true, backup_id: event.detail.backup_id });
            await callTasks('record_workspace_rollback', {
              task_id: task.task_id,
              backup_id: event.detail.backup_id,
              approved: true,
            });
            await loadTaskDetails(task.task_id);
            await loadTasks();
          } catch (error) {
            rollbackButton.disabled = false;
            rollbackButton.title = error.message;
            rollbackButton.textContent = `Geri alma başarısız: ${error.message}`;
          }
        });
        entry.append(document.createTextNode(' '), rollbackButton);
      }
      if (event.action === 'test_run') {
        const testStatus = document.createElement('strong');
        testStatus.className = event.detail.passed ? 'task-test-passed' : 'task-test-failed';
        testStatus.textContent = event.detail.passed ? ' Testler geçti' : ` Testler kaldı (${event.detail.returncode})`;
        entry.append(testStatus);
        if (event.detail.output) {
          const outputDetails = document.createElement('details');
          const outputSummary = document.createElement('summary');
          outputSummary.textContent = 'Test çıktısı';
          const output = document.createElement('pre');
          output.className = 'task-diff';
          output.textContent = event.detail.output;
          outputDetails.append(outputSummary, output);
          entry.append(outputDetails);
        }
      }
      history.append(entry);
    }
    taskDetail.append(historyHeading, history);
  }
}

async function loadTasks() {
  taskList.replaceChildren();
  try {
    const result = await callTasks('list', { limit: 50 });
    if (!result.tasks?.length) {
      const empty = document.createElement('p');
      empty.className = 'diagnostics-empty';
      empty.textContent = 'Henüz görev planı yok.';
      taskList.append(empty);
      return;
    }
    for (const task of result.tasks) {
      const item = document.createElement('article');
      item.className = 'memory-item';
      const heading = document.createElement('div');
      heading.className = 'memory-item-heading';
      const request = document.createElement('strong');
      request.textContent = task.request;
      const metadata = document.createElement('span');
      metadata.textContent = `${taskStatusLabels[task.status] || task.status} · ${task.completed_steps || 0}/${task.step_count} adım`;
      heading.append(request, metadata);
      const detailsButton = document.createElement('button');
      detailsButton.className = 'task-step-action';
      detailsButton.type = 'button';
      detailsButton.textContent = 'Ayrıntıları aç';
      detailsButton.addEventListener('click', () => loadTaskDetails(task.task_id));
      item.append(heading, detailsButton);
      taskList.append(item);
    }
  } catch (error) {
    const message = document.createElement('p');
    message.className = 'diagnostics-summary';
    message.textContent = error.message;
    taskList.append(message);
  }
}

openTasksButton.addEventListener('click', () => {
  stopJobPolling();
  diagnosticsPanel.hidden = true;
  memoryPanel.hidden = true;
  codeGraphPanel.hidden = true;
  documentsPanel.hidden = true;
  jobsPanel.hidden = true;
  researchPanel.hidden = true;
  tasksPanel.hidden = false;
  loadTasks();
});

closeTasksButton.addEventListener('click', () => {
  tasksPanel.hidden = true;
});

openJobsButton.addEventListener('click', () => {
  diagnosticsPanel.hidden = true;
  memoryPanel.hidden = true;
  codeGraphPanel.hidden = true;
  documentsPanel.hidden = true;
  tasksPanel.hidden = true;
  researchPanel.hidden = true;
  jobsPanel.hidden = false;
  refreshJobCenter();
  if (jobsRefreshTimer !== null) window.clearInterval(jobsRefreshTimer);
  jobsRefreshTimer = window.setInterval(refreshJobCenter, 3000);
});

closeJobsButton.addEventListener('click', () => {
  jobsPanel.hidden = true;
  stopJobPolling();
});

jobsRefreshButton.addEventListener('click', refreshJobCenter);

openResearchButton.addEventListener('click', () => {
  stopJobPolling();
  diagnosticsPanel.hidden = true;
  memoryPanel.hidden = true;
  codeGraphPanel.hidden = true;
  documentsPanel.hidden = true;
  tasksPanel.hidden = true;
  jobsPanel.hidden = true;
  researchPanel.hidden = false;
  loadRepoWatch();
});

closeResearchButton.addEventListener('click', () => {
  researchPanel.hidden = true;
});

function renderRepoWatchResult(result) {
  repoWatchResult.replaceChildren();
  const heading = document.createElement('p');
  heading.className = 'memory-status';
  const changes = [];
  if (result.release_changed) changes.push('yeni release');
  if (result.commit_changed) changes.push('yeni commit');
  heading.textContent = result.baseline
    ? 'İlk metadata snapshot’ı kaydedildi.'
    : changes.length ? `Değişiklik: ${changes.join(' · ')}` : 'Yeni release veya commit yok.';
  repoWatchResult.append(heading);

  const release = document.createElement('p');
  release.className = 'repo-watch-metadata';
  release.textContent = result.release ? `Release · ${result.release.tag} · ${result.release.title}` : 'Release · bulunamadı';
  repoWatchResult.append(release);
  if (result.release?.url) {
    const releaseLink = document.createElement('a');
    releaseLink.href = result.release.url;
    releaseLink.target = '_blank';
    releaseLink.rel = 'noopener noreferrer';
    releaseLink.textContent = result.release.url;
    repoWatchResult.append(releaseLink);
  }

  const commit = document.createElement('p');
  commit.className = 'repo-watch-metadata';
  commit.textContent = `Son commit · ${result.latest_commit.sha.slice(0, 12)} · ${result.latest_commit.message}`;
  repoWatchResult.append(commit);
  const commitLink = document.createElement('a');
  commitLink.href = result.latest_commit.url;
  commitLink.target = '_blank';
  commitLink.rel = 'noopener noreferrer';
  commitLink.textContent = result.latest_commit.url;
  repoWatchResult.append(commitLink);
  repoWatchStatus.textContent = `Kontrol tamamlandı · saatte ${result.rate_limit.local_remaining_this_hour}/${result.rate_limit.max_per_hour} yerel kontrol kaldı.`;
}

async function loadRepoWatch() {
  repoWatchList.replaceChildren();
  repoWatchResult.replaceChildren();
  await loadRepoPollingStatus();
  try {
    const result = await callRepoWatch('list');
    if (!result.repositories.length) {
      const empty = document.createElement('p');
      empty.className = 'diagnostics-empty';
      empty.textContent = 'Allowlist boş.';
      repoWatchList.append(empty);
      return;
    }
    for (const repository of result.repositories) {
      const item = document.createElement('article');
      item.className = 'memory-item repo-watch-item';
      const heading = document.createElement('div');
      heading.className = 'memory-item-heading';
      const name = document.createElement('strong');
      name.textContent = repository.repository;
      const checked = document.createElement('span');
      checked.textContent = repository.checked_at ? `Son kontrol · ${repository.checked_at}` : 'Henüz kontrol edilmedi';
      heading.append(name, checked);

      const actions = document.createElement('div');
      actions.className = 'job-actions';
      const checkButton = document.createElement('button');
      checkButton.className = 'task-step-action';
      checkButton.type = 'button';
      checkButton.textContent = 'Metadata kontrol et';
      checkButton.addEventListener('click', async () => {
        if (!window.confirm(`${repository.repository} için api.github.com üzerinde release ve son commit metadata’sı kontrol edilsin? Kod indirilmez.`)) return;
        checkButton.disabled = true;
        repoWatchStatus.textContent = 'Public GitHub metadata kontrol ediliyor...';
        try {
          const checkedResult = await callRepoWatch('check', { repository: repository.repository, approved: true });
          await loadRepoWatch();
          renderRepoWatchResult(checkedResult);
        } catch (error) {
          repoWatchStatus.textContent = error.message;
        } finally {
          checkButton.disabled = false;
        }
      });

      const snapshotButton = document.createElement('button');
      snapshotButton.className = 'task-step-action';
      snapshotButton.type = 'button';
      snapshotButton.textContent = 'README’yi indeksle';
      snapshotButton.addEventListener('click', async () => {
        if (!window.confirm(`${repository.repository} deposunun README dosyası yerel belge aramasına eklensin mi? Kaynak kodu indirilmez veya çalıştırılmaz.`)) return;
        snapshotButton.disabled = true;
        repoWatchStatus.textContent = 'Onaylı README snapshot’ı alınıyor...';
        try {
          const snapshot = await callRepoWatch('snapshot_readme', {
            repository: repository.repository,
            approved: true,
          });
          await loadRepoWatch();
          repoWatchStatus.textContent = snapshot.already_indexed
            ? 'Bu README blob’u zaten indekslenmiş.'
            : `README belge indeksine eklendi · ${snapshot.document_id}`;
          repoWatchResult.replaceChildren();
          const source = document.createElement('a');
          source.href = snapshot.source_url;
          source.target = '_blank';
          source.rel = 'noopener noreferrer';
          source.textContent = `Kaynak README · ${snapshot.blob_sha.slice(0, 12)}`;
          repoWatchResult.append(source);
        } catch (error) {
          repoWatchStatus.textContent = error.message;
        } finally {
          snapshotButton.disabled = false;
        }
      });

      const removeButton = document.createElement('button');
      removeButton.className = 'document-delete-button';
      removeButton.type = 'button';
      removeButton.textContent = 'Allowlist’ten çıkar';
      removeButton.addEventListener('click', async () => {
        if (!window.confirm(`${repository.repository} allowlist’ten çıkarılsın mı?`)) return;
        removeButton.disabled = true;
        try {
          await callRepoWatch('remove', { repository: repository.repository, approved: true });
          repoWatchStatus.textContent = `${repository.repository} çıkarıldı.`;
          await loadRepoWatch();
        } catch (error) {
          repoWatchStatus.textContent = error.message;
          removeButton.disabled = false;
        }
      });
      actions.append(checkButton, snapshotButton, removeButton);

      const filesDetails = document.createElement('details');
      filesDetails.className = 'repo-watch-files';
      const filesSummary = document.createElement('summary');
      filesSummary.textContent = 'Seçili kaynak dosyaları';
      const filesForm = document.createElement('form');
      filesForm.className = 'repo-watch-files-form';
      const filesLabel = document.createElement('label');
      filesLabel.textContent = 'Repo içindeki açık dosya yolları';
      const filesInput = document.createElement('textarea');
      filesInput.maxLength = 1_500;
      filesInput.rows = 3;
      filesInput.required = true;
      filesInput.placeholder = 'src/main.ts\npackage.json';
      filesLabel.append(filesInput);
      const filesButton = document.createElement('button');
      filesButton.className = 'task-step-action';
      filesButton.type = 'submit';
      filesButton.textContent = 'Seçilenleri indeksle';
      filesForm.append(filesLabel, filesButton);
      filesForm.addEventListener('submit', async (event) => {
        event.preventDefault();
        const paths = [...new Set(filesInput.value.split(/\r?\n/).map((path) => path.trim()).filter(Boolean))];
        if (!paths.length || paths.length > 5) {
          repoWatchStatus.textContent = '1–5 açık dosya yolu gerekli.';
          return;
        }
        if (!window.confirm(`${repository.repository} içinden yalnızca bu ${paths.length} dosya alınacak; kod çalıştırılmayacak. Devam edilsin mi?\n\n${paths.join('\n')}`)) return;
        filesButton.disabled = true;
        repoWatchStatus.textContent = 'Seçilen dosyalar doğrulanıp indeksleniyor...';
        try {
          const snapshot = await callRepoWatch('snapshot_files', {
            repository: repository.repository,
            paths,
            approved: true,
          });
          await loadRepoWatch();
          const freshDetails = [...repoWatchList.querySelectorAll('.repo-watch-item')]
            .find((entry) => entry.querySelector('strong')?.textContent === repository.repository)
            ?.querySelector('.repo-watch-files');
          if (freshDetails) freshDetails.open = true;
          const added = snapshot.indexed_files.filter((file) => !file.already_indexed).length;
          repoWatchStatus.textContent = `${added} yeni belge indekslendi · ${snapshot.indexed_files.length - added} tekrar atlandı · ${snapshot.total_bytes} byte.`;
          repoWatchResult.replaceChildren();
          for (const file of snapshot.indexed_files) {
            const resultItem = document.createElement('article');
            resultItem.className = 'research-result';
            const link = document.createElement('a');
            link.href = file.source_url;
            link.target = '_blank';
            link.rel = 'noopener noreferrer';
            link.textContent = `${file.path} · ${file.blob_sha.slice(0, 12)}`;
            const reviewButton = document.createElement('button');
            reviewButton.className = 'task-step-action';
            reviewButton.type = 'button';
            reviewButton.textContent = 'Statik incele';
            reviewButton.disabled = !file.document_id;
            reviewButton.addEventListener('click', async () => {
              if (!window.confirm(`${file.path} yerel modelle salt-okunur incelensin mi? Dosya çalıştırılmaz, web’e gönderilmez ve rapor otomatik kaydedilmez.`)) return;
              reviewButton.disabled = true;
              repoWatchStatus.textContent = `${file.path} yerel modelle inceleniyor...`;
              try {
                const report = await callAnalysis('run', {
                  approved: true,
                  document_id: file.document_id,
                  question: 'Summarize architecture, entrypoints, dependencies, trust boundaries, and concrete review risks. Cite exact source lines; do not propose exploit steps.',
                  model: modelSelect.value || null,
                });
                repoWatchStatus.textContent = report.unverified_findings
                  ? `Analiz tamamlandı · ${report.model} · ${report.unverified_findings} kanıtlanamayan bulgu gösterilmedi.`
                  : `Statik analiz tamamlandı · ${report.model}`;
                resultItem.replaceChildren(link);
                const summary = document.createElement('p');
                summary.className = 'repo-watch-metadata';
                summary.textContent = `Otomatik model özeti · ${report.summary}`;
                resultItem.append(summary);
                if (report.unverified_findings) {
                  const warning = document.createElement('p');
                  warning.className = 'repo-watch-metadata';
                  warning.textContent = `${report.unverified_findings} bulgu, kaynakta birebir satır kanıtı doğrulanamadığı için gizlendi.`;
                  resultItem.append(warning);
                }
                for (const finding of report.findings) {
                  const detail = document.createElement('p');
                  detail.className = 'repo-watch-metadata';
                  detail.textContent = `${finding.severity.toUpperCase()} · ${finding.title} · ${finding.evidence} · ${finding.analysis}`;
                  resultItem.append(detail);
                }
                repoWatchResult.append(resultItem);
              } catch (error) {
                repoWatchStatus.textContent = error.message;
                reviewButton.disabled = false;
              }
            });
            const vectorButton = document.createElement('button');
            vectorButton.className = 'task-step-action';
            vectorButton.type = 'button';
            vectorButton.textContent = 'Qdrant’a indeksle';
            vectorButton.disabled = !file.document_id;
            vectorButton.addEventListener('click', async () => {
              if (!window.confirm(`${file.path} yerel Nomic embedding’iyle Qdrant’a eklensin mi?`)) return;
              vectorButton.disabled = true;
              knowledgeStatus.textContent = `${file.path} yerel embedding ile indeksleniyor...`;
              try {
                const indexed = await callKnowledge('index', { document_id: file.document_id, approved: true });
                knowledgeStatus.textContent = `${indexed.chunks} chunk Qdrant’a eklendi · ${indexed.embedding_model} · ${indexed.dimensions} boyut.`;
                const deleteButton = document.createElement('button');
                deleteButton.className = 'document-delete-button';
                deleteButton.type = 'button';
                deleteButton.textContent = 'Qdrant kaydını sil';
                deleteButton.addEventListener('click', async () => {
                  if (!window.confirm(`${file.path} için Qdrant vektörleri silinsin mi? Belge indeksi korunur.`)) return;
                  deleteButton.disabled = true;
                  try {
                    await callKnowledge('delete', { document_id: file.document_id, approved: true });
                    deleteButton.remove();
                    knowledgeStatus.textContent = `${file.path} için vektörler silindi; belge indeksi korundu.`;
                  } catch (error) {
                    deleteButton.disabled = false;
                    knowledgeStatus.textContent = error.message;
                  }
                });
                resultItem.append(deleteButton);
              } catch (error) {
                knowledgeStatus.textContent = error.message;
                vectorButton.disabled = false;
              }
            });
            resultItem.append(link, reviewButton, vectorButton);
            repoWatchResult.append(resultItem);
          }
          filesInput.value = '';
        } catch (error) {
          repoWatchStatus.textContent = error.message;
        } finally {
          filesButton.disabled = false;
        }
      });
      filesDetails.append(filesSummary, filesForm);
      item.append(heading, actions);
      item.append(filesDetails);
      repoWatchList.append(item);
    }
  } catch (error) {
    repoWatchStatus.textContent = error.message;
  }
}

async function loadRepoPollingStatus() {
  try {
    const status = await callRepoWatch('polling_status');
    repoWatchPollingEnabledInput.checked = status.enabled;
    repoWatchPollingIntervalInput.value = String(status.interval_minutes);
    const details = [status.enabled ? 'Otomatik kontrol etkin' : 'Otomatik kontrol kapalı'];
    if (status.next_run_at) details.push(`Sonraki çalışma · ${status.next_run_at}`);
    if (status.last_completed_at) {
      details.push(`Son çalışma · ${status.last_completed_at} · ${status.last_check_count} repo`);
    }
    if (status.last_changes?.length) details.push(`Değişiklik görülenler · ${status.last_changes.join(', ')}`);
    if (status.last_error) details.push(`Son hata · ${status.last_error}`);
    repoWatchPollingStatus.textContent = details.join(' · ');
  } catch (error) {
    repoWatchPollingStatus.textContent = error.message;
  }
}

window.setInterval(() => {
  if (!researchPanel.hidden) void loadRepoPollingStatus();
}, 30_000);

repoWatchAddForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const repository = repoWatchRepositoryInput.value.trim();
  if (!repository || !window.confirm(`${repository} public repository olarak allowlist’e eklensin mi? Otomatik kod indirme yapılmaz.`)) return;
  try {
    const result = await callRepoWatch('add', { repository, approved: true });
    repoWatchStatus.textContent = result.added ? `${repository} allowlist’e eklendi.` : `${repository} zaten allowlist’te.`;
    repoWatchRepositoryInput.value = '';
    await loadRepoWatch();
  } catch (error) {
    repoWatchStatus.textContent = error.message;
  }
});

repoWatchPollingForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const enabled = repoWatchPollingEnabledInput.checked;
  const intervalMinutes = Number(repoWatchPollingIntervalInput.value);
  if (!Number.isInteger(intervalMinutes) || intervalMinutes < 5 || intervalMinutes > 1440) {
    repoWatchPollingStatus.textContent = 'Aralık 5–1440 dakika arasında tam sayı olmalı.';
    return;
  }
  const confirmation = enabled
    ? `Allowlist’teki public depoların release/commit metadata’sı her ${intervalMinutes} dakikada bir kontrol edilsin mi? Saatte en fazla 20 metadata kontrolü yapılır; kaynak kodu indirilmez.`
    : 'Otomatik repo metadata kontrolleri durdurulsun mu?';
  if (!window.confirm(confirmation)) {
    await loadRepoPollingStatus();
    return;
  }
  const button = repoWatchPollingForm.querySelector('button[type="submit"]');
  button.disabled = true;
  repoWatchPollingStatus.textContent = 'Polling ayarı kaydediliyor...';
  try {
    const status = await callRepoWatch('configure_polling', {
      enabled,
      interval_minutes: intervalMinutes,
      approved: true,
    });
    repoWatchPollingEnabledInput.checked = status.enabled;
    repoWatchPollingIntervalInput.value = String(status.interval_minutes);
    await loadRepoPollingStatus();
  } catch (error) {
    repoWatchPollingStatus.textContent = error.message;
    await loadRepoPollingStatus();
  } finally {
    button.disabled = false;
  }
});

knowledgeSearchForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = knowledgeQueryInput.value.trim();
  if (!query) return;
  knowledgeStatus.textContent = 'Yerel embedding ve Qdrant araması çalışıyor...';
  knowledgeResults.replaceChildren();
  try {
    const result = await callKnowledge('search', { query, limit: 5 });
    knowledgeStatus.textContent = `${result.count} eşleşme · ${result.embedding_model}`;
    for (const match of result.results) {
      const item = document.createElement('article');
      item.className = 'research-result';
      const source = document.createElement('a');
      source.href = match.source_url;
      if (source.href.startsWith('http')) {
        source.target = '_blank';
        source.rel = 'noopener noreferrer';
      }
      source.textContent = `${match.filename} · parça ${match.chunk_index + 1} · ${match.sha256.slice(0, 12)}`;
      const score = document.createElement('span');
      score.className = 'job-progress-label';
      score.textContent = `Eşleşme ${match.score.toFixed(3)} · karakter ${match.start_char}-${match.end_char}`;
      const text = document.createElement('p');
      text.className = 'repo-watch-metadata';
      text.textContent = match.text;
      item.append(source, score, text);
      knowledgeResults.append(item);
    }
  } catch (error) {
    knowledgeStatus.textContent = error.message;
  }
});

binaryInspectionApprovedInput.addEventListener('change', updateBinaryInspectionAvailability);
binaryInspectionFileInput.addEventListener('change', updateBinaryInspectionAvailability);

binaryInspectionForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = binaryInspectionFileInput.files?.[0];
  if (!file || !binaryInspectionApprovedInput.checked) return;
  if (file.size > 10_000_000) {
    binaryInspectionStatus.textContent = 'Binary 10 MB sınırını aşıyor.';
    return;
  }
  if (!window.confirm(`${file.name} dosyası çalıştırılmadan statik metadata, sınırlı disassembly ve strings için incelensin mi?`)) return;
  binaryInspectionButton.disabled = true;
  binaryInspectionStatus.textContent = 'Dosya yerel LIEF parser ile inceleniyor...';
  binaryInspectionResult.replaceChildren();
  try {
    const result = await fetch('/api/plugins/binary_analysis/actions/inspect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payload: {
          approved: true,
          filename: file.name,
          content_base64: await fileToBase64(file),
        },
      }),
    });
    const payload = await readApiJson(result, 'Statik inceleme');
    if (!result.ok) throw new Error(payload.detail || `Statik inceleme başarısız · HTTP ${result.status}`);
    renderBinaryInspection(payload);
  } catch (error) {
    binaryInspectionStatus.textContent = error.message;
  } finally {
    binaryInspectionButton.disabled = false;
  }
});

browserInspectionApprovedInput.addEventListener('change', () => {
  browserInspectionButton.disabled = !browserInspectionApprovedInput.checked;
});

browserInspectionForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const url = browserInspectionUrlInput.value.trim();
  if (!url || !browserInspectionApprovedInput.checked) return;
  if (!window.confirm(`${url} allowlist’e göre salt-okunur snapshot alınsın mı? Yalnızca GET, en fazla 10.000 karakter; etkileşim yapılmaz.`)) return;
  browserInspectionButton.disabled = true;
  browserInspectionStatus.textContent = 'Headless browser local snapshot alıyor...';
  browserInspectionResult.replaceChildren();
  try {
    const snapshot = await callBrowserInspection('inspect', { url, approved: true });
    const heading = document.createElement('p');
    heading.className = 'repo-watch-metadata';
    heading.textContent = `${snapshot.title} · HTTP ${snapshot.http_status ?? 'n/a'} · ${snapshot.blocked_requests} istek engellendi · etkileşim ${snapshot.interactions_performed}`;
    const link = document.createElement('a');
    link.href = snapshot.final_url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = snapshot.final_url;
    const text = document.createElement('pre');
    text.className = 'browser-snapshot-text';
    text.textContent = snapshot.text;
    browserInspectionResult.append(heading, link, text);
    if (snapshot.text_error) {
      browserInspectionStatus.textContent = `Kısmi snapshot · sayfa metni çıkarılamadı: ${snapshot.text_error}`;
    } else {
      browserInspectionStatus.textContent = snapshot.text_truncated ? 'Snapshot alındı · metin 10.000 karakterde kesildi.' : 'Snapshot alındı · salt-okunur.';
    }
  } catch (error) {
    browserInspectionStatus.textContent = error.message;
  } finally {
    browserInspectionButton.disabled = !browserInspectionApprovedInput.checked;
  }
});

researchSearchForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = researchQueryInput.value.trim();
  if (!query) return;
  researchSearchButton.disabled = true;
  researchResults.replaceChildren();
  const loading = document.createElement('p');
  loading.className = 'memory-status';
  loading.textContent = 'DuckDuckGo sonuçları alınıyor...';
  researchResults.append(loading);
  try {
    const result = await callResearch('search', { query, limit: 5 });
    researchStatus.textContent = `Arama sağlayıcısı: ${result.provider === 'yandex' ? 'Yandex' : 'DuckDuckGo'}`;
    researchResults.replaceChildren();
    if (!result.results.length) {
      loading.textContent = 'Public sonuç bulunamadı.';
      researchResults.append(loading);
      return;
    }
    for (const candidate of result.results) {
      const item = document.createElement('article');
      item.className = 'research-result';
      const title = document.createElement('strong');
      title.textContent = candidate.title;
      const link = document.createElement('a');
      link.href = candidate.url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = candidate.url;
      const snippet = document.createElement('p');
      snippet.textContent = candidate.snippet;
      const selectButton = document.createElement('button');
      selectButton.className = 'task-step-action';
      selectButton.type = 'button';
      selectButton.textContent = 'Kaynaklara ekle';
      selectButton.addEventListener('click', () => {
        const selected = researchUrlsInput.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean);
        if (selected.includes(candidate.url)) {
          researchStatus.textContent = 'Bu URL zaten kaynak listesinde.';
          return;
        }
        if (selected.length >= 5) {
          researchStatus.textContent = 'En fazla 5 kaynak seçilebilir.';
          return;
        }
        selected.push(candidate.url);
        researchUrlsInput.value = selected.join('\n');
        researchStatus.textContent = `Kaynak eklendi · ${selected.length}/5`;
      });
      item.append(title, link, snippet, selectButton);
      researchResults.append(item);
    }
  } catch (error) {
    loading.textContent = error.message;
  } finally {
    researchSearchButton.disabled = false;
  }
});

researchForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = researchQuestionInput.value.trim();
  const urls = [...new Set(researchUrlsInput.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean))];
  if (!question || urls.length < 1 || urls.length > 5) {
    researchStatus.textContent = 'Soru ve 1–5 public URL gerekli.';
    return;
  }
  if (!window.confirm(`${urls.length} URL public olarak okunacak; içerikleri güvenilmeyen kaynak kabul edilip yerel modelle özetlenecek. Devam edilsin mi?`)) return;
  researchStartButton.disabled = true;
  researchStatus.textContent = 'Public kaynaklar job kuyruğuna ekleniyor...';
  try {
    const job = await callResearch('start', {
      question,
      urls,
      model: modelSelect.value || null,
      approved: true,
    });
    researchStatus.textContent = `Araştırma işi oluşturuldu · ${job.job_id}`;
    openJobsButton.click();
    await loadJobDetails(job.job_id);
  } catch (error) {
    researchStatus.textContent = error.message;
  } finally {
    researchStartButton.disabled = false;
  }
});

githubResearchForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = githubResearchQuestionInput.value.trim();
  const repositories = [...new Set(githubRepositoryUrlsInput.value.split(/\r?\n/).map((url) => url.trim()).filter(Boolean))];
  if (!question || repositories.length < 1 || repositories.length > 3) {
    githubResearchStatus.textContent = 'Soru ve 1–3 public GitHub repository URL’si gerekli.';
    return;
  }
  if (!window.confirm(`${repositories.length} GitHub public README’si okunacak; repository kodu clone edilmeyecek veya çalıştırılmayacak. Devam edilsin mi?`)) return;
  githubResearchStartButton.disabled = true;
  githubResearchStatus.textContent = 'GitHub README job’u kuyruğa ekleniyor...';
  try {
    const job = await callResearch('start_github', {
      question,
      repositories,
      model: modelSelect.value || null,
      approved: true,
    });
    githubResearchStatus.textContent = `GitHub araştırması oluşturuldu · ${job.job_id}`;
    openJobsButton.click();
    await loadJobDetails(job.job_id);
  } catch (error) {
    githubResearchStatus.textContent = error.message;
  } finally {
    githubResearchStartButton.disabled = false;
  }
});

jobsRecoverStaleButton.addEventListener('click', async () => {
  if (jobsRecoverStaleButton.disabled) return;
  jobsRecoveryPreview.replaceChildren();
  jobsRecoveryStatus.textContent = '';
  const staleAfterSeconds = Number(jobsStaleAfterInput.value);
  if (!Number.isInteger(staleAfterSeconds) || staleAfterSeconds < 60 || staleAfterSeconds > 604_800) {
    jobsStatus.textContent = 'Lease süresi 60 ile 604800 saniye arasında olmalı.';
    return;
  }
  jobsRecoverStaleButton.disabled = true;
  jobsStaleAfterInput.disabled = true;
  try {
    jobsRecoveryStatus.textContent = 'Toparlama adayları salt-okunur olarak kontrol ediliyor...';
    const preview = await callJobs('recovery_candidates', { stale_after_seconds: staleAfterSeconds, limit: 100 });
    if (!preview || !Number.isSafeInteger(preview.candidate_count) || preview.candidate_count < 0
        || preview.lease_seconds !== staleAfterSeconds || typeof preview.observed_at !== 'string'
        || !Array.isArray(preview.jobs) || preview.jobs.length !== Math.min(preview.candidate_count, 100)
        || preview.jobs.some((job) => !job || typeof job.job_id !== 'string' || typeof job.kind !== 'string'
          || !['running', 'cancel_requested'].includes(job.status)
          || job.recovery_status !== (job.status === 'running' ? 'failed' : 'cancelled'))) {
      throw new Error('Toparlama önizlemesi geçersiz; işlem onaylanmadı.');
    }
    if (preview.candidate_count === 0) {
      jobsRecoveryStatus.textContent = 'Toparlama adayı yok; hiçbir iş değiştirilmedi.';
      return;
    }
    for (const job of preview.jobs) {
      const item = document.createElement('li');
      item.textContent = `${job.kind} · ${job.job_id} · ${job.status} → ${job.recovery_status}`;
      jobsRecoveryPreview.append(item);
    }
    const summary = `${preview.candidate_count} aday · gösterilen ${preview.jobs.length} · önizleme ${preview.observed_at}`;
    jobsRecoveryStatus.textContent = `${summary}. Çalışanlar failed, iptal bekleyenler cancelled olur.`;
    if (!window.confirm(`${summary}\n${staleAfterSeconds} saniyeden uzun süredir güncellenmeyen tüm işler yeniden değerlendirilecek. Liste limiti işlem sayısını sınırlamaz. Çalışanlar failed, iptal bekleyenler cancelled olarak işaretlenecek; otomatik retry yapılmayacak. Önizleme sonrası yenilenen lease korunur; adaylar değişebilir. Toparlama onaylansın mı?`)) {
      jobsRecoveryStatus.textContent = `${summary}. Onay verilmedi; hiçbir iş değiştirilmedi.`;
      return;
    }
    const result = await callJobs('recover_stale', { approved: true, stale_after_seconds: staleAfterSeconds });
    if (!result || !Number.isSafeInteger(result.recovered_count) || result.recovered_count < 0) {
      throw new Error('Toparlama yanıtı geçersiz; iş durumlarını yenileyip kontrol edin.');
    }
    jobsRecoveryStatus.textContent = `${result.recovered_count} stale job toparlandı. Üstteki liste işlem öncesi önizlemedir; güncel işler yeniden değerlendirildi.`;
    await refreshJobCenter();
  } catch (error) {
    jobsRecoveryStatus.textContent = error.message;
  } finally {
    jobsRecoverStaleButton.disabled = false;
    jobsStaleAfterInput.disabled = false;
  }
});

taskRefreshButton.addEventListener('click', loadTasks);

taskDraftButton.addEventListener('click', async () => {
  const request = taskRequestInput.value.trim();
  if (!request) {
    taskRequestInput.focus();
    taskCreateStatus.textContent = 'Önce görev isteğini yaz.';
    return;
  }
  taskDraftButton.disabled = true;
  taskCreateStatus.textContent = 'Seçili yerel model görev adımları hazırlıyor...';
  try {
    const response = await fetch('/api/tasks/draft', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ request, model: modelSelect.value || null }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Görev taslağı oluşturulamadı.');
    taskStepsInput.value = result.steps.join('\n');
    taskCreateStatus.textContent = `Taslak hazır · ${result.model || 'yerel model'} · gözden geçirip planı kaydet.`;
  } catch (error) {
    taskCreateStatus.textContent = error.message;
  } finally {
    taskDraftButton.disabled = false;
  }
});

taskCreateForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const request = taskRequestInput.value.trim();
  const steps = taskStepsInput.value.split(/\r?\n/).map((step) => step.trim()).filter(Boolean);
  if (!request || !steps.length) return;
  taskCreateStatus.textContent = 'Plan kaydediliyor...';
  try {
    const task = await callTasks('create', { request, steps });
    taskCreateForm.reset();
    taskCreateStatus.textContent = 'Plan kaydedildi; adımlara geçmeden önce onay gerekli.';
    await loadTasks();
    await loadTaskDetails(task.task_id);
  } catch (error) {
    taskCreateStatus.textContent = error.message;
  }
});

function updateDocumentUploadAvailability() {
  documentUploadButton.disabled = !documentApprovedInput.checked || !documentFileInput.files?.length;
}

function renderDocumentResults(items, source = 'search') {
  documentResults.replaceChildren();
  if (!items.length) {
    const empty = document.createElement('p');
    empty.className = 'diagnostics-empty';
    empty.textContent = source === 'search' ? 'Eşleşen belge parçası bulunamadı.' : 'Yüklü belge yok.';
    documentResults.append(empty);
    return;
  }

  for (const documentItem of items) {
    const item = document.createElement('article');
    item.className = 'memory-item';
    const heading = document.createElement('div');
    heading.className = 'memory-item-heading';
    const filename = document.createElement('strong');
    filename.textContent = documentItem.filename;
    const metadata = document.createElement('span');
    metadata.textContent = source === 'search'
      ? `Karakter ${documentItem.start_char}-${documentItem.end_char} · parça ${documentItem.chunk_index + 1}`
      : `${documentItem.extension} · ${documentItem.indexed_characters} karakter · ${documentItem.created_at}`;
    heading.append(filename, metadata);
    item.append(heading);

    const previewButton = document.createElement('button');
    previewButton.className = 'document-preview-button';
    previewButton.type = 'button';
    previewButton.textContent = 'Önizle';
    previewButton.addEventListener('click', async () => {
      previewButton.disabled = true;
      try {
        const preview = await callDocuments('preview', { document_id: documentItem.document_id });
        documentPreviewTitle.textContent = preview.filename;
        documentPreviewContent.textContent = preview.content;
        documentPreviewStatus.textContent = preview.truncated
          ? `İlk ${preview.content.length.toLocaleString('tr-TR')} karakter gösteriliyor · toplam ${preview.indexed_characters.toLocaleString('tr-TR')} karakter`
          : `${preview.indexed_characters.toLocaleString('tr-TR')} karakter`;
        documentPreviewDialog.showModal();
      } catch (error) {
        documentUploadStatus.textContent = error.message;
      } finally {
        previewButton.disabled = false;
      }
    });
    item.append(previewButton);

    const deleteButton = document.createElement('button');
    deleteButton.className = 'document-delete-button';
    deleteButton.type = 'button';
    deleteButton.textContent = 'Belgeyi sil';
    deleteButton.addEventListener('click', async () => {
      if (!window.confirm(`“${documentItem.filename}” ve yerel arama indeksindeki parçaları kalıcı olarak silmek istiyor musun?`)) return;
      deleteButton.disabled = true;
      documentUploadStatus.textContent = 'Belge ve indeks kayıtları siliniyor...';
      try {
        await callDocuments('delete', { document_id: documentItem.document_id, approved: true });
        await loadDocuments();
        documentUploadStatus.textContent = `${documentItem.filename} silindi.`;
      } catch (error) {
        deleteButton.disabled = false;
        documentUploadStatus.textContent = error.message;
      }
    });
    item.append(deleteButton);

    if (source === 'search') {
      const content = document.createElement('p');
      content.textContent = documentItem.content;
      const download = document.createElement('a');
      download.className = 'document-source-link';
      download.href = documentItem.source_url;
      download.textContent = 'Kaynak dosyayı indir';
      download.download = documentItem.filename;
      item.append(content, download);
    }
    documentResults.append(item);
  }
}

closeDocumentPreviewButton.addEventListener('click', () => documentPreviewDialog.close());

function bytesToBase64(bytes) {
  let binary = '';
  const chunkSize = 0x8000;
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return btoa(binary);
}

openDocumentsButton.addEventListener('click', () => {
  stopJobPolling();
  diagnosticsPanel.hidden = true;
  memoryPanel.hidden = true;
  codeGraphPanel.hidden = true;
  tasksPanel.hidden = true;
  jobsPanel.hidden = true;
  researchPanel.hidden = true;
  documentsPanel.hidden = false;
  loadDocuments();
});

closeDocumentsButton.addEventListener('click', () => {
  documentsPanel.hidden = true;
});

documentFileInput.addEventListener('change', updateDocumentUploadAvailability);
documentApprovedInput.addEventListener('change', updateDocumentUploadAvailability);

documentUploadForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = documentFileInput.files?.[0];
  updateDocumentUploadAvailability();
  if (!file || documentUploadButton.disabled) return;
  if (file.size > 20_000_000) {
    documentUploadStatus.textContent = 'Dosya 20 MB sınırını aşıyor.';
    return;
  }

  documentUploadButton.disabled = true;
  documentUploadStatus.textContent = 'Belge yerel olarak çıkarılıp indeksleniyor...';
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    const result = await callDocuments('ingest', {
      approved: true,
      filename: file.name,
      content_base64: bytesToBase64(bytes),
    });
    documentUploadStatus.textContent = `${result.indexed_chunks} parça indekslendi · ${result.extracted_characters} karakter`;
    documentApprovedInput.checked = false;
    documentFileInput.value = '';
    updateDocumentUploadAvailability();
    await loadDocuments();
  } catch (error) {
    documentUploadStatus.textContent = error.message;
    updateDocumentUploadAvailability();
  }
});

async function loadDocuments() {
  try {
    const result = await callDocuments('list', { limit: 100 });
    renderDocumentResults(result.documents || [], 'list');
  } catch (error) {
    documentResults.replaceChildren();
    const message = document.createElement('p');
    message.className = 'diagnostics-summary';
    message.textContent = error.message;
    documentResults.append(message);
  }
}

documentListButton.addEventListener('click', loadDocuments);

documentSearchForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const query = documentQueryInput.value.trim();
  if (!query) return;
  documentResults.replaceChildren();
  const status = document.createElement('p');
  status.className = 'diagnostics-summary';
  status.textContent = 'Yerel belgeler aranıyor...';
  documentResults.append(status);
  try {
    const result = await callDocuments('search', { query, limit: 10 });
    renderDocumentResults(result.results || []);
  } catch (error) {
    status.textContent = error.message;
  }
});

function renderGraphNodes(nodes) {
  graphResults.replaceChildren();
  if (!nodes.length) {
    const empty = document.createElement('p');
    empty.className = 'diagnostics-empty';
    empty.textContent = 'Eşleşen sembol bulunamadı.';
    graphResults.append(empty);
    return;
  }
  for (const node of nodes) {
    const item = document.createElement('article');
    item.className = 'memory-item';
    const heading = document.createElement('div');
    heading.className = 'memory-item-heading';
    const name = document.createElement('strong');
    name.textContent = node.qualified_name || node.name;
    const metadata = document.createElement('span');
    metadata.textContent = `${node.kind} · ${node.path}:${node.line || 1}`;
    heading.append(name, metadata);
    item.append(heading);
    graphResults.append(item);
  }
}

openCodeGraphButton.addEventListener('click', () => {
  stopJobPolling();
  diagnosticsPanel.hidden = true;
  memoryPanel.hidden = true;
  documentsPanel.hidden = true;
  tasksPanel.hidden = true;
  jobsPanel.hidden = true;
  researchPanel.hidden = true;
  codeGraphPanel.hidden = false;
});

closeCodeGraphButton.addEventListener('click', () => {
  codeGraphPanel.hidden = true;
});

buildCodeGraphButton.addEventListener('click', async () => {
  buildCodeGraphButton.disabled = true;
  graphStatus.textContent = 'Python AST grafı salt okunur oluşturuluyor...';
  graphResults.replaceChildren();
  try {
    const result = await callCodeGraph('build');
    const summary = result.summary || {};
    graphStatus.textContent = `${result.scanned_files} dosya · ${summary.modules} modül · ${summary.classes} sınıf · ${summary.functions} fonksiyon · ${summary.edges} ilişki${result.truncated ? ' · limit nedeniyle kısmi' : ''}`;
  } catch (error) {
    graphStatus.textContent = error.message;
  } finally {
    buildCodeGraphButton.disabled = false;
  }
});

graphSearchForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  graphStatus.textContent = 'Graf aranıyor...';
  try {
    const result = await callCodeGraph('search', { query: graphSearchQuery.value.trim(), limit: 50 });
    graphStatus.textContent = `${result.results.length} sembol bulundu${result.truncated ? ' · sonuç sınırına ulaşıldı' : ''}`;
    renderGraphNodes(result.results || []);
  } catch (error) {
    graphStatus.textContent = error.message;
  }
});

graphPathForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  graphStatus.textContent = 'Semboller arası yol aranıyor...';
  try {
    const result = await callCodeGraph('path', {
      source: graphPathSource.value.trim(),
      target: graphPathTarget.value.trim(),
    });
    graphResults.replaceChildren();
    if (!result.found) {
      graphStatus.textContent = 'Bu semboller arasında statik yol bulunamadı.';
      return;
    }
    graphStatus.textContent = `${result.hops} adımlı yol bulundu`;
    renderGraphNodes(result.nodes || []);
  } catch (error) {
    graphStatus.textContent = error.message;
  }
});

modelSelect.addEventListener('change', updateModelDetails);
modelSearch.addEventListener('input', renderModelOptions);
refreshModelsButton.addEventListener('click', loadModels);

async function runDiagnostics() {
  stopJobPolling();
  memoryPanel.hidden = true;
  codeGraphPanel.hidden = true;
  documentsPanel.hidden = true;
  tasksPanel.hidden = true;
  jobsPanel.hidden = true;
  researchPanel.hidden = true;
  diagnosticsPanel.hidden = false;
  diagnosticsSummary.textContent = 'Workspace salt okunur olarak taranıyor...';
  diagnosticsResults.replaceChildren();
  scanDiagnosticsButton.disabled = true;
  try {
    const response = await fetch('/api/plugins/diagnostics/scan', { method: 'POST' });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Tarama tamamlanamadı.');
    renderDiagnostics(result);
  } catch (error) {
    diagnosticsSummary.textContent = error.message;
  } finally {
    scanDiagnosticsButton.disabled = false;
  }
}

scanDiagnosticsButton.addEventListener('click', runDiagnostics);

closeDiagnosticsButton.addEventListener('click', () => {
  diagnosticsPanel.hidden = true;
});

sessionSelect.addEventListener('change', async () => {
  activeSessionId = sessionSelect.value;
  if (!activeSessionId) {
    startNewChat();
    return;
  }
  localStorage.setItem(SESSION_STORAGE_KEY, activeSessionId);
  deleteSessionButton.disabled = false;
  await loadSessionMessages(activeSessionId);
});

newChatButton.addEventListener('click', startNewChat);

deleteSessionButton.addEventListener('click', async () => {
  if (!activeSessionId || !window.confirm('Seçili sohbeti ve mesajlarını kalıcı olarak silmek istiyor musun?')) return;
  deleteSessionButton.disabled = true;
  try {
    const response = await fetch(`/api/chat/sessions/${encodeURIComponent(activeSessionId)}`, {
      method: 'DELETE',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ approved: true }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || 'Sohbet silinemedi');
    startNewChat();
    await loadSessions();
    sessionStatus.textContent = result.deleted ? 'Sohbet silindi' : 'Sohbet bulunamadı';
  } catch (error) {
    deleteSessionButton.disabled = !activeSessionId;
    sessionStatus.textContent = error.message;
  }
});

openMemoryButton.addEventListener('click', () => {
  stopJobPolling();
  diagnosticsPanel.hidden = true;
  codeGraphPanel.hidden = true;
  documentsPanel.hidden = true;
  tasksPanel.hidden = true;
  jobsPanel.hidden = true;
  researchPanel.hidden = true;
  memoryPanel.hidden = false;
});

closeMemoryButton.addEventListener('click', () => {
  memoryPanel.hidden = true;
});

for (const input of [memoryApprovedInput, memoryTitleInput, memoryContentInput]) {
  input.addEventListener('input', updateMemorySaveAvailability);
  input.addEventListener('change', updateMemorySaveAvailability);
}

memorySaveForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  updateMemorySaveAvailability();
  if (memorySaveButton.disabled) return;
  memorySaveButton.disabled = true;
  memorySaveStatus.textContent = 'Yerel hafızaya kaydediliyor...';
  try {
    const result = await callMemory('remember', {
      approved: true,
      title: memoryTitleInput.value.trim(),
      project: memoryProjectInput.value.trim(),
      category: memoryCategoryInput.value.trim() || 'general',
      content: memoryContentInput.value.trim(),
    });
    memorySaveStatus.textContent = `Kaydedildi · #${result.id}`;
    memoryContentInput.value = '';
    memoryApprovedInput.checked = false;
    updateMemorySaveAvailability();
  } catch (error) {
    memorySaveStatus.textContent = error.message;
    updateMemorySaveAvailability();
  }
});

async function searchMemories(query) {
  memoryResults.replaceChildren();
  const status = document.createElement('p');
  status.className = 'diagnostics-summary';
  status.textContent = 'Yerel hafıza aranıyor...';
  memoryResults.append(status);
  try {
    const result = await callMemory('search', {
      query,
      project: memoryProjectFilter.value.trim(),
      category: memoryCategoryFilter.value.trim(),
      source: memorySourceFilter.value.trim(),
      limit: 20,
    });
    renderMemories(result.memories || []);
  } catch (error) {
    status.textContent = error.message;
  }
}

memorySearchForm.addEventListener('submit', (event) => {
  event.preventDefault();
  const query = memoryQueryInput.value.trim();
  if (query) searchMemories(query);
});

async function loadMemoryTimeline() {
  memoryResults.replaceChildren();
  try {
    const result = await callMemory('timeline', {
      project: memoryProjectFilter.value.trim(),
      limit: 20,
    });
    renderMemories(result.memories || []);
  } catch (error) {
    const message = document.createElement('p');
    message.className = 'diagnostics-summary';
    message.textContent = error.message;
    memoryResults.append(message);
  }
}

memoryTimelineButton.addEventListener('click', loadMemoryTimeline);

memoryTaxonomyButton.addEventListener('click', async () => {
  memoryResults.replaceChildren();
  try {
    const taxonomy = await callMemory('taxonomy', {});
    const groups = [
      ['Kategoriler', taxonomy.categories],
      ['Projeler', taxonomy.projects],
      ['Kaynaklar', taxonomy.sources],
    ];
    for (const [label, values] of groups) {
      const item = document.createElement('article');
      item.className = 'memory-item';
      const heading = document.createElement('strong');
      heading.textContent = label;
      const content = document.createElement('p');
      content.textContent = values.length ? values.join(' · ') : 'Kayıt yok';
      item.append(heading, content);
      memoryResults.append(item);
    }
  } catch (error) {
    memoryToolsStatus.textContent = error.message;
  }
});

memoryExportButton.addEventListener('click', async () => {
  if (!window.confirm('Yerel hafıza JSON dosyası olarak dışa aktarılsın mı? Dosya indirilecektir.')) return;
  memoryExportButton.disabled = true;
  memoryToolsStatus.textContent = 'Hafıza dışa aktarılıyor...';
  try {
    const exported = await callMemory('export', { approved: true });
    const blob = new Blob([JSON.stringify(exported, null, 2)], { type: 'application/json' });
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = objectUrl;
    link.download = `deep-panda-memory-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    memoryToolsStatus.textContent = `${exported.memories.length} not dışa aktarıldı.`;
  } catch (error) {
    memoryToolsStatus.textContent = error.message;
  } finally {
    memoryExportButton.disabled = false;
  }
});

function updateMemoryImportAvailability() {
  memoryImportButton.disabled = !memoryImportApprovedInput.checked || !memoryImportFileInput.files?.length;
}

memoryImportApprovedInput.addEventListener('change', updateMemoryImportAvailability);
memoryImportFileInput.addEventListener('change', updateMemoryImportAvailability);

memoryImportForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const file = memoryImportFileInput.files?.[0];
  if (!file || !memoryImportApprovedInput.checked) return;
  if (file.size > 10_000_000) {
    memoryToolsStatus.textContent = 'Import dosyası 10 MB sınırını aşıyor.';
    return;
  }
  if (!window.confirm(`${file.name} içindeki notlar yerel hafızaya eklensin mi? Mevcut notlar silinmez.`)) return;
  memoryImportButton.disabled = true;
  memoryToolsStatus.textContent = 'JSON dosyası doğrulanıyor...';
  try {
    const importedData = JSON.parse(await file.text());
    const result = await callMemory('import', { ...importedData, approved: true });
    memoryToolsStatus.textContent = `${result.imported} yeni not eklendi · ${result.duplicates} tekrar atlandı.`;
    memoryImportForm.reset();
    updateMemoryImportAvailability();
    await loadMemoryTimeline();
  } catch (error) {
    memoryToolsStatus.textContent = error instanceof SyntaxError ? 'Import dosyası geçerli JSON değil.' : error.message;
    updateMemoryImportAvailability();
  }
});

memorySourcePreviewForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const source = memorySourceQueryInput.value.trim();
  if (!source) return;
  memorySourcePreview.replaceChildren();
  try {
    const preview = await callMemory('preview_source', { source });
    const summary = document.createElement('p');
    summary.className = 'memory-status';
    summary.textContent = `${preview.count} not bulundu: ${source}`;
    memorySourcePreview.append(summary);
    for (const memory of preview.memories) {
      const item = document.createElement('article');
      item.className = 'memory-item';
      const title = document.createElement('strong');
      title.textContent = memory.title;
      const content = document.createElement('p');
      content.textContent = memory.content;
      item.append(title, content);
      memorySourcePreview.append(item);
    }
    if (preview.count) {
      const deleteButton = document.createElement('button');
      deleteButton.className = 'document-delete-button';
      deleteButton.type = 'button';
      deleteButton.textContent = 'Onayla ve bu kaynağı sil';
      deleteButton.addEventListener('click', async () => {
        if (!window.confirm(`${source} kaynağındaki ${preview.count} not silinecek; önce backup alınacak. Devam edilsin mi?`)) return;
        deleteButton.disabled = true;
        try {
          const result = await callMemory('delete_source', { source, approved: true });
          memoryToolsStatus.textContent = `${result.deleted} not silindi · backup: ${result.backup_path}`;
          memorySourcePreview.replaceChildren();
          await loadMemoryTimeline();
        } catch (error) {
          deleteButton.disabled = false;
          memoryToolsStatus.textContent = error.message;
        }
      });
      memorySourcePreview.append(deleteButton);
    }
  } catch (error) {
    const message = document.createElement('p');
    message.className = 'diagnostics-summary';
    message.textContent = error.message;
    memorySourcePreview.append(message);
  }
});

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const message = messageInput.value.trim();
  if (!message) return;
  messageInput.value = '';
  await sendChatMessage(message, modelSelect.value || null);
});

async function sendChatMessage(message, model, { echo = true } = {}) {
  clearIntentPanel();
  welcome.hidden = true;
  if (echo) addMessage(message, 'user');
  sendButton.disabled = true;
  modelStatus.textContent = 'Yanıt hazırlanıyor';

  try {
    const response = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message,
        model,
        workflow: workflowSelect.value || 'standard',
        session_id: activeSessionId || null,
      }),
    });
    const result = await response.json();
    if (response.status === 401 && result.auth) {
      window.DeepPandaCloud?.renderAuthRequired(result.auth, () => sendChatMessage(message, model, { echo: false }));
      modelStatus.textContent = 'Oturum gerekli · istek gönderilmedi';
      return;
    }
    if (!response.ok) throw new Error(result.detail || 'İstek tamamlanamadı');
    if (result.status === 'auth_required') {
      window.DeepPandaCloud?.renderAuthRequired(result.auth, () => sendChatMessage(message, model, { echo: false }));
      modelStatus.textContent = 'Oturum gerekli · istek gönderilmedi';
      return;
    }
    activeSessionId = result.session_id || activeSessionId;
    if (activeSessionId) localStorage.setItem(SESSION_STORAGE_KEY, activeSessionId);
    const answer = result.message?.content || 'Model boş yanıt döndürdü.';
    addMessage(answer, 'assistant');
    window.DeepPandaCloud?.renderAnswerActions(message, answer, result.cloud_suggestion);
    renderToolActivity(result.tools_used);
    renderIntentRoute(result.intent_route, message);
    modelStatus.textContent = result.model || 'Yanıt hazır';
    if (activeSessionId) {
      sessionStatus.textContent = 'Sohbet kaydedildi';
      await loadSessions();
    }
  } catch (error) {
    addMessage(error.message, 'assistant', true);
    window.DeepPandaCloud?.renderAnswerActions(message, '', { reason: 'Yerel model yanıt veremedi.' });
    modelStatus.textContent = 'İstek başarısız';
  } finally {
    sendButton.disabled = false;
    messageInput.focus();
  }
}

loadStatus();
runDiagnostics();