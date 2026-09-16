const $ = (selector) => document.querySelector(selector);

const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

let panelOpen = false;
let currentPage = 1;
let sortCol = '';
let sortDir = 'desc';

function sortableHeaderHtml(column) {
  const isActive = sortCol === column;
  const arrow = isActive ? (sortDir === 'asc' ? ' ▲' : ' ▼') : '';
  return `<th class="sortable ${isActive ? 'sorted' : ''}" data-column="${esc(column)}">${esc(column)}${arrow}</th>`;
}

function renderPagination(page, totalPages) {
  const box = $('#lowStockPagination');
  if (!box) return;
  if (totalPages <= 1) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = `
    <button type="button" class="ghost small" id="lowPrevPage" ${page <= 1 ? 'disabled' : ''}>← 이전</button>
    <span>${page} / ${totalPages} 페이지</span>
    <button type="button" class="ghost small" id="lowNextPage" ${page >= totalPages ? 'disabled' : ''}>다음 →</button>
  `;
  box.querySelector('#lowPrevPage')?.addEventListener('click', () => {
    if (currentPage <= 1) return;
    currentPage -= 1;
    loadLowStock();
  });
  box.querySelector('#lowNextPage')?.addEventListener('click', () => {
    if (currentPage >= totalPages) return;
    currentPage += 1;
    loadLowStock();
  });
}

async function loadLowStock() {
  const table = $('#lowStockTable');
  const meta = $('#lowStockMeta');
  if (!table || !meta) return;

  meta.textContent = '조회 중…';

  try {
    const params = new URLSearchParams({low: '1', page: String(currentPage), page_size: '10'});
    if (sortCol) { params.set('sort', sortCol); params.set('dir', sortDir); }
    const response = await fetch('/api/search?' + params.toString());
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '저재고 조회에 실패했습니다.');

    const columns = data.columns || [];
    const rows = data.items || [];

    table.querySelector('thead').innerHTML = `<tr>${columns.map((column) => sortableHeaderHtml(column)).join('')}<th>파일</th></tr>`;

    table.querySelector('tbody').innerHTML = rows.map((row) => `
      <tr>
        ${columns.map((column) => {
          const value = row.data?.[column];
          const isCode = row.identifier && value !== null && value !== '' && String(value) === String(row.identifier);
          const cell = isCode
            ? `<a class="code-link" href="/ebay/${encodeURIComponent(row.identifier)}" title="eBay 최저가 조회">${esc(value)}</a>`
            : esc(value ?? '');
          return `<td>${cell}</td>`;
        }).join('')}
        <td>${esc(row.file_name || '')}</td>
      </tr>
    `).join('') || '<tr><td class="empty">저재고 항목이 없습니다.</td></tr>';

    currentPage = data.page || 1;
    renderPagination(currentPage, data.total_pages || 1);
    meta.textContent = `저재고 ${data.count || 0}건`;

    table.querySelectorAll('th.sortable').forEach((th) => {
      th.addEventListener('click', () => {
        const column = th.dataset.column;
        if (sortCol === column) {
          sortDir = sortDir === 'asc' ? 'desc' : 'asc';
        } else {
          sortCol = column;
          sortDir = 'asc';
        }
        currentPage = 1;
        loadLowStock();
      });
    });
  } catch (error) {
    meta.textContent = error.message;
  }
}

$('#lowStockToggle')?.addEventListener('click', async () => {
  const panel = $('#lowStockPanel');
  if (!panel) return;

  panelOpen = !panelOpen;
  panel.style.display = panelOpen ? 'block' : 'none';
  $('#lowStockToggle').textContent = panelOpen ? '저재고 접기 ↑' : '저재고만 조회 ↓';

  if (panelOpen) {
    currentPage = 1;
    await loadLowStock();
    panel.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
});
