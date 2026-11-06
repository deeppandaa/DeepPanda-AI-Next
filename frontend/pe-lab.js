const fileInput = document.querySelector('#pe-file');
const dropZone = document.querySelector('#drop-zone');
const fileName = document.querySelector('#file-name');
const fileMeta = document.querySelector('#file-meta');
const approvedInput = document.querySelector('#pe-approved');
const inspectButton = document.querySelector('#inspect-button');
const analysisStatus = document.querySelector('#analysis-status');
const results = document.querySelector('#results');
const tabs = [...document.querySelectorAll('.view-tab')];
const pageSize = 100;
let selectedFile = null;
let analysisResult = null;
let activeInstructionPage = 0;

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

function updateAvailability() {
  inspectButton.disabled = !selectedFile || !approvedInput.checked;
}

function setSelectedFile(file) {
  selectedFile = file || null;
  analysisResult = null;
  fileName.textContent = selectedFile?.name || 'Dosya seçilmedi';
  fileMeta.textContent = selectedFile
    ? `${formatBytes(selectedFile.size)} · ${selectedFile.name.split('.').pop()?.toUpperCase() || 'PE adayı'}`
    : 'Windows PE · en fazla 10 MB';
  analysisStatus.textContent = selectedFile ? 'Yerel incelemeye hazır.' : 'Başlamak için PE dosyası seç.';
  results.hidden = true;
  updateAvailability();
}

function bytesToBase64(bytes) {
  let binary = '';
  for (let offset = 0; offset < bytes.length; offset += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
  }
  return btoa(binary);
}

function makeCell(value, className = '') {
  const cell = document.createElement('td');
  cell.textContent = value ?? '—';
  if (className) cell.className = className;
  return cell;
}

function renderFacts(result, metadata, analysis) {
  document.querySelector('#sample-title').textContent = result.filename;
  document.querySelector('#sample-hash').textContent = `SHA-256 · ${result.sha256}`;
  const facts = [
    ['FORMAT', metadata.format],
    ['ARCH', `${metadata.architecture} · ${metadata.bits}-bit`],
    ['SIZE', formatBytes(result.size_bytes)],
    ['ENTRY RVA', `0x${metadata.entrypoint_rva.toString(16)}`],
    ['IMAGE BASE', `0x${metadata.image_base.toString(16)}`],
    ['ENTRY VA', analysis.entrypoint || '—'],
  ];
  const list = document.querySelector('#sample-facts');
  list.replaceChildren();
  for (const [label, value] of facts) {
    const item = document.createElement('div');
    const term = document.createElement('dt');
    term.textContent = label;
    const definition = document.createElement('dd');
    definition.textContent = value;
    item.append(term, definition);
    list.append(item);
  }
}

function renderSections(metadata) {
  const body = document.querySelector('#sections-body');
  body.replaceChildren();
  for (const section of metadata.sections) {
    const row = document.createElement('tr');
    row.append(
      makeCell(section.name, 'mono-cell'),
      makeCell(section.virtual_size.toLocaleString()),
      makeCell(section.file_size.toLocaleString()),
      makeCell(section.executable === null ? '—' : section.executable ? 'Yes' : 'No'),
    );
    body.append(row);
  }
  document.querySelector('#section-count').textContent = `${metadata.sections.length} bölüm${metadata.truncated_sections ? ' · sınırlandı' : ''}`;
  document.querySelector('#subsystem-value').textContent = metadata.subsystem || '—';
  document.querySelector('#dll-characteristics').textContent = metadata.dll_characteristics?.join(' · ') || '—';
}

function renderInstructionPage() {
  const analysis = analysisResult.metadata.static_analysis;
  const instructions = analysis.instructions;
  const pageCount = Math.max(1, Math.ceil(instructions.length / pageSize));
  activeInstructionPage = Math.min(activeInstructionPage, pageCount - 1);
  const start = activeInstructionPage * pageSize;
  const body = document.querySelector('#instructions-body');
  body.replaceChildren();
  for (const instruction of instructions.slice(start, start + pageSize)) {
    const row = document.createElement('tr');
    row.append(
      makeCell(instruction.address, 'mono-cell'),
      makeCell(instruction.bytes, 'mono-cell'),
      makeCell(instruction.mnemonic, 'mono-cell'),
      makeCell(instruction.operands, 'mono-cell'),
    );
    body.append(row);
  }
  document.querySelector('#instruction-page-label').textContent = `${instructions.length} talimat`;
  document.querySelector('#page-position').textContent = `${activeInstructionPage + 1} / ${pageCount}`;
  document.querySelector('#previous-page').disabled = activeInstructionPage === 0;
  document.querySelector('#next-page').disabled = activeInstructionPage >= pageCount - 1;
  document.querySelector('#disassembly-note').textContent = analysis.disassembly_truncated
    ? 'Yanıt talimat veya bayt sınırına ulaştı.'
    : `Entrypoint ${analysis.entrypoint || 'yok'} · çalıştırılabilir bölümlerin sonu.`;
}

function renderStrings() {
  if (!analysisResult) return;
  const analysis = analysisResult.metadata.static_analysis;
  const query = document.querySelector('#string-filter').value.trim().toLowerCase();
  const strings = analysis.strings.filter((entry) => (
    !query || entry.value.toLowerCase().includes(query) || entry.offset.toLowerCase().includes(query)
  ));
  const body = document.querySelector('#strings-body');
  body.replaceChildren();
  for (const entry of strings) {
    const row = document.createElement('tr');
    row.append(makeCell(entry.offset, 'mono-cell'), makeCell(entry.encoding, 'mono-cell'), makeCell(entry.value));
    body.append(row);
  }
  document.querySelector('#strings-count').textContent = `${strings.length} gösteriliyor · ${analysis.strings.length} çıkarıldı`;
  document.querySelector('#strings-note').textContent = analysis.strings_truncated
    ? 'Yanıt metin dizisi sınırına ulaştı.'
    : 'Yalnızca yazdırılabilir ASCII ve UTF-16LE dizileri listelenir.';
}

function renderImports(metadata) {
  const container = document.querySelector('#imports-list');
  container.replaceChildren();
  const imports = metadata.imports || [];
  document.querySelector('#imports-count').textContent = `${imports.length} kütüphane${metadata.truncated_libraries ? ' · sınırlandı' : ''}`;
  for (const library of imports) {
    const details = document.createElement('details');
    details.className = 'import-item';
    const summary = document.createElement('summary');
    const name = document.createElement('span');
    name.className = 'import-name';
    name.textContent = library.name;
    const count = document.createElement('span');
    count.className = 'count-label';
    count.textContent = `${library.symbols.length} sembol`;
    summary.append(name, count);
    details.append(summary);
    details.addEventListener('toggle', () => {
      if (!details.open || details.dataset.loaded) return;
      const list = document.createElement('ul');
      list.className = 'import-symbols';
      for (const symbol of library.symbols) {
        const item = document.createElement('li');
        item.textContent = symbol;
        list.append(item);
      }
      details.append(list);
      details.dataset.loaded = 'true';
    });
    container.append(details);
  }
  if (!imports.length) container.textContent = 'Import kütüphanesi bulunamadı.';
}

function renderFunctionTable(records, targetId, countId, truncated) {
  const body = document.querySelector(`#${targetId}`);
  body.replaceChildren();
  for (const record of records) {
    const row = document.createElement('tr');
    row.append(makeCell(record.name || '(unnamed)'), makeCell(record.address, 'mono-cell'), makeCell(record.size.toLocaleString()));
    body.append(row);
  }
  document.querySelector(`#${countId}`).textContent = `${records.length} kayıt${truncated ? ' · sınırlandı' : ''}`;
  if (!records.length) {
    const row = document.createElement('tr');
    const cell = makeCell('Mevcut sembol verisinde kayıt bulunamadı.', 'empty-row');
    cell.colSpan = 3;
    row.append(cell);
    body.append(row);
  }
}

function renderAnalysis(result) {
  const metadata = result.metadata;
  const analysis = metadata.static_analysis;
  activeInstructionPage = 0;
  renderFacts(result, metadata, analysis);
  renderSections(metadata);
  renderInstructionPage();
  renderStrings();
  renderImports(metadata);
  renderFunctionTable(analysis.functions, 'functions-body', 'functions-count', analysis.functions_truncated);
  renderFunctionTable(analysis.exports, 'exports-body', 'exports-count', analysis.exports_truncated);
  results.hidden = false;
  results.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function selectView(name) {
  for (const tab of tabs) {
    const selected = tab.dataset.view === name;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.querySelector(`#view-${tab.dataset.view}`).hidden = !selected;
  }
}

function exportReport() {
  if (!analysisResult) return;
  const report = new Blob([JSON.stringify(analysisResult, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(report);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${analysisResult.filename.replace(/[^A-Za-z0-9._-]/g, '_')}.analysis.json`;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

document.querySelector('#choose-file').addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => setSelectedFile(fileInput.files?.[0] || null));
approvedInput.addEventListener('change', updateAvailability);

for (const eventName of ['dragenter', 'dragover']) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add('is-dragging');
  });
}
for (const eventName of ['dragleave', 'drop']) {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove('is-dragging');
  });
}
dropZone.addEventListener('drop', (event) => setSelectedFile(event.dataTransfer?.files?.[0] || null));

document.querySelector('#pe-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!selectedFile || !approvedInput.checked) return;
  if (selectedFile.size < 2 || selectedFile.size > 10_000_000) {
    analysisStatus.textContent = 'Dosya 2 bayt ile 10 MB arasında olmalı.';
    return;
  }
  inspectButton.disabled = true;
  analysisStatus.textContent = 'PE başlığı doğrulanıp yerel statik analiz yapılıyor...';
  results.hidden = true;
  try {
    const bytes = new Uint8Array(await selectedFile.arrayBuffer());
    if (bytes[0] !== 0x4d || bytes[1] !== 0x5a) throw new Error('Dosyada Windows MZ başlığı bulunamadı.');
    const response = await fetch('/api/plugins/binary_analysis/actions/inspect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        payload: { approved: true, filename: selectedFile.name, content_base64: bytesToBase64(bytes) },
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || `Analiz başarısız · HTTP ${response.status}`);
    if (payload.metadata?.format !== 'PE') throw new Error('Dosya PE biçiminde tanımlanmadı.');
    analysisResult = payload;
    renderAnalysis(payload);
    analysisStatus.textContent = 'Statik analiz tamamlandı · örnek çalıştırılmadı.';
  } catch (error) {
    analysisStatus.textContent = error.message;
  } finally {
    updateAvailability();
  }
});

for (const tab of tabs) {
  tab.addEventListener('click', () => selectView(tab.dataset.view));
  tab.addEventListener('keydown', (event) => {
    if (!['ArrowLeft', 'ArrowRight'].includes(event.key)) return;
    event.preventDefault();
    const direction = event.key === 'ArrowRight' ? 1 : -1;
    const next = (tabs.indexOf(tab) + direction + tabs.length) % tabs.length;
    tabs[next].focus();
    selectView(tabs[next].dataset.view);
  });
}

document.querySelector('#string-filter').addEventListener('input', renderStrings);
document.querySelector('#previous-page').addEventListener('click', () => {
  activeInstructionPage -= 1;
  renderInstructionPage();
});
document.querySelector('#next-page').addEventListener('click', () => {
  activeInstructionPage += 1;
  renderInstructionPage();
});
document.querySelector('#export-report').addEventListener('click', exportReport);