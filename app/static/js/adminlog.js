const $ = (selector) => document.querySelector(selector);

const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

let currentPage = 1;
let timer = null;

function renderPagination(page, totalPages) {
  const box = $('#logPagination');
  if (!box) return;
  if (totalPages <= 1) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = `
    <button type="button" class="ghost small" id="logPrev" ${page <= 1 ? 'disabled' : ''}>← 이전</button>
    <span>${page} / ${totalPages} 페이지</span>
    <button type="button" class="ghost small" id="logNext" ${page >= totalPages ? 'disabled' : ''}>다음 →</button>
  `;
  box.querySelector('#logPrev')?.addEventListener('click', () => {
    if (currentPage <= 1) return;
    currentPage -= 1;
    search();
  });
  box.querySelector('#logNext')?.addEventListener('click', () => {
    if (currentPage >= totalPages) return;
    currentPage += 1;
    search();
  });
}

async function search() {
  const table = $('#logTable');
  const meta = $('#logMeta');
  if (!table || !meta) return;

  meta.textContent = '조회 중…';

  const params = new URLSearchParams({
    page: String(currentPage),
    page_size: '10',
    q: $('#logSearch')?.value.trim() || '',
    action: $('#logAction')?.value || '',
    date: $('#logDate')?.value || '',
  });

  try {
    const response = await fetch(`/api/adminlog?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '조회에 실패했습니다.');

    const items = data.items || [];

    table.querySelector('tbody').innerHTML = items.map((item) => `
      <tr>
        <td>${esc(item.created_at)}</td>
        <td>${esc(item.user || '-')}</td>
        <td><span class="status">${esc(item.action_label)}</span></td>
        <td>${esc(item.detail || '')}</td>
      </tr>
    `).join('') || '<tr><td class="empty" colspan="4">로그가 없습니다.</td></tr>';

    currentPage = data.page || 1;
    renderPagination(currentPage, data.total_pages || 1);
    meta.textContent = `총 ${data.count || 0}건`;
  } catch (error) {
    meta.textContent = error.message;
  }
}

$('#logSearch')?.addEventListener('input', () => {
  clearTimeout(timer);
  currentPage = 1;
  timer = setTimeout(search, 250);
});

$('#logDate')?.addEventListener('change', () => {
  currentPage = 1;
  search();
});

$('#logAction')?.addEventListener('change', () => {
  currentPage = 1;
  search();
});

search();
