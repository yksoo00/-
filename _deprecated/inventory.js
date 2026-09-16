const $ = (selector) => document.querySelector(selector);

let timer;
let files = [];
let sheets = [];
let activeFilter = '';
let selectedSheets = [];
let currentPage = 1;
let lowOnly = new URLSearchParams(window.location.search).get('low') === '1';

const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

function sheetIds() { return selectedSheets.join(','); }

function renderPagination(page, totalPages) {
  const box = $('#pagination');
  if (!box) return;
  if (totalPages <= 1) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = `
    <button type="button" class="ghost small" id="prevPage" ${page <= 1 ? 'disabled' : ''}>← 이전</button>
    <span>${page} / ${totalPages} 페이지</span>
    <button type="button" class="ghost small" id="nextPage" ${page >= totalPages ? 'disabled' : ''}>다음 →</button>
  `;
  box.querySelector('#prevPage')?.addEventListener('click', async () => {
    if (currentPage <= 1) return;
    currentPage -= 1;
    await search();
  });
  box.querySelector('#nextPage')?.addEventListener('click', async () => {
    if (currentPage >= totalPages) return;
    currentPage += 1;
    await search();
  });
}

function updateSheetText() {
  const element = $('#sheetSelectionText');
  if (element) element.textContent = selectedSheets.length ? `${selectedSheets.length}개 선택` : '전체';
}

function renderLowBar() {
  const box = $('#lowStockBar');
  if (!box) return;
  if (!lowOnly) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }
  box.style.display = 'flex';
  box.innerHTML = `
    <span>⚠ 저재고(수량 1개 이하 · 용량 정보 있음) 항목만 보고 있습니다.</span>
    <button type="button" id="clearLowFilter">전체 보기</button>
  `;
  $('#clearLowFilter').addEventListener('click', async () => {
    lowOnly = false;
    currentPage = 1;
    history.replaceState(null, '', '/inventory');
    renderLowBar();
    await search();
  });
}

function renderSheetPicker() {
  const box = $('#sheetPickerMenu');
  if (!box) return;
  box.innerHTML = sheets.length ? sheets.map((sheet) => `
    <label class="sheet-option">
      <input type="checkbox" value="${sheet.id}" ${selectedSheets.includes(sheet.id) ? 'checked' : ''}>
      <span>${esc(sheet.name)}</span>
    </label>
  `).join('') : '<div class="sheet-option-empty">Sheet 없음</div>';
  box.querySelectorAll('input').forEach((input) => input.addEventListener('change', async () => {
    selectedSheets = [...box.querySelectorAll('input:checked')].map((item) => Number(item.value));
    updateSheetText();
    currentPage = 1;
    await loadFilters();
    await search();
  }));
}

async function loadFiles() {
  const response = await fetch('/api/files');
  if (!response.ok) throw new Error('Excel 목록을 불러오지 못했습니다.');
  const data = await response.json();
  files = data.items || [];
  $('#fileFilter').innerHTML = '<option value="">모든 Excel</option>' + files.map((file) =>
    `<option value="${file.id}">${esc(file.name)}</option>`
  ).join('');
}

async function loadSheets() {
  const fileId = $('#fileFilter').value;
  selectedSheets = [];
  sheets = [];
  if (fileId) {
    const response = await fetch(`/api/sheets/${fileId}`);
    if (!response.ok) throw new Error('Sheet 목록을 불러오지 못했습니다.');
    const data = await response.json();
    sheets = data.items || [];
  } else {
    const results = await Promise.all(files.map(async (file) => {
      const response = await fetch(`/api/sheets/${file.id}`);
      if (!response.ok) return {items: []};
      const data = await response.json();
      return data.items || [];
    }));
    sheets = results.flat();
  }
  renderSheetPicker();
  updateSheetText();
}

function renderFilters(filterList) {
  const box = $('#dynamicFilters');
  if (!box) return;
  box.innerHTML = filterList.length ? `
    <div class="filter-bar"><span class="filter-label">검색 기준</span><div class="filter-buttons">
      <button type="button" class="filter-button ${!activeFilter ? 'active' : ''}" data-filter="">전체</button>
      ${filterList.map((filter) => `
        <button type="button" class="filter-button ${activeFilter === filter.name ? 'active' : ''}" data-filter="${esc(filter.name)}">${esc(filter.name)}</button>
      `).join('')}
    </div></div>
    <div class="filter-help">버튼으로 검색 기준만 고르고, 검색어는 <b>하나의 전체 검색창</b>에 입력하세요.</div>
  ` : '';
  box.querySelectorAll('.filter-button').forEach((button) => button.addEventListener('click', () => {
    activeFilter = button.dataset.filter || '';
    currentPage = 1;
    const searchInput = $('#globalSearch');
    searchInput.placeholder = activeFilter ? `${activeFilter} 기준으로 검색` : 'Code, 품명, 모델, 용량, 위치, 비고 등 전체 검색';
    renderFilters(filterList);
    searchInput.focus();
    search();
  }));
}

async function loadFilters() {
  const params = new URLSearchParams();
  const fileId = $('#fileFilter').value;
  if (fileId) params.set('file_id', fileId);
  if (sheetIds()) params.set('sheet_ids', sheetIds());
  const response = await fetch('/api/filters?' + params.toString());
  if (!response.ok) throw new Error('검색 필드를 불러오지 못했습니다.');
  const data = await response.json();
  const names = data.filters || [];
  if (activeFilter && !names.some((item) => item.name === activeFilter)) activeFilter = '';
  renderFilters(names);
}

async function search() {
  const text = $('#globalSearch').value || '';
  const filters = activeFilter && text.trim() ? {[activeFilter]: text.trim()} : {};
  const params = new URLSearchParams({
    q: activeFilter ? '' : text,
    file_id: $('#fileFilter').value || '',
    filters: JSON.stringify(filters),
  });
  if (sheetIds()) params.set('sheet_ids', sheetIds());
  if (lowOnly) params.set('low', '1');
  params.set('page', currentPage);
  const response = await fetch('/api/search?' + params.toString());
  const data = await response.json();
  if (!response.ok) {
    if ($('#resultMeta')) $('#resultMeta').textContent = data.error || '검색에 실패했습니다.';
    return;
  }
  const columns = data.columns || [];
  $('#inventoryTable thead').innerHTML = '<tr>' + columns.map((column) => `<th>${esc(column)}</th>`).join('') + '<th>출처</th></tr>';
  $('#inventoryTable tbody').innerHTML = (data.items || []).map((row) => `
    <tr>
      ${columns.map((column) => {
        const value = row.data?.[column];
        const low = /수량|재고|qty|quantity/i.test(column) && value !== null && value !== '' && !Number.isNaN(Number(value)) && Number(value) <= 1;
        const isCode = lowOnly && row.identifier && value !== null && value !== '' && String(value) === String(row.identifier);
        const cell = isCode
          ? `<a class="code-link" href="/ebay/${encodeURIComponent(row.identifier)}" title="eBay 최저가 조회">${esc(value)}</a>`
          : esc(value ?? '');
        return `<td class="${low ? 'qty low' : ''}">${cell}</td>`;
      }).join('')}
      <td><a href="/files/${row.file_id}">${esc(files.find((file) => file.id === row.file_id)?.name || '')}</a></td>
    </tr>
  `).join('');
  currentPage = data.page || 1;
  renderPagination(currentPage, data.total_pages || 1);
  $('#resultMeta').textContent = `검색 결과 ${data.count || 0}건 · ${columns.length}개 컬럼 · ${selectedSheets.length ? selectedSheets.length + '개 Sheet' : '전체 Sheet'}`;
}

$('#globalSearch').addEventListener('input', () => {
  clearTimeout(timer);
  currentPage = 1;
  timer = setTimeout(search, 250);
});

$('#fileFilter').addEventListener('change', async () => {
  activeFilter = '';
  currentPage = 1;
  await loadSheets();
  await loadFilters();
  await search();
});

$('#sheetPicker').addEventListener('click', (event) => {
  if (event.target.closest('.sheet-picker-button')) $('#sheetPicker').classList.toggle('open');
});

document.addEventListener('click', (event) => {
  if (!event.target.closest('.sheet-picker')) document.querySelectorAll('.sheet-picker').forEach((element) => element.classList.remove('open'));
});

(async function init() {
  try {
    renderLowBar();
    await loadFiles();
    await loadSheets();
    await loadFilters();
    await search();
  } catch (error) {
    if ($('#resultMeta')) $('#resultMeta').textContent = error.message;
  }
}());
