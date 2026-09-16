const $ = (selector) => document.querySelector(selector);

const esc = (value) => String(value ?? '').replace(/[&<>'"]/g, (char) => ({
  '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
}[char]));

let currentPage = 1;
let timer = null;

const STATUS_LABEL = {
  requested: '요청됨',
  approved: '승인완료',
  arrived: '입고완료',
};

const SOURCE_LABEL = {
  auto: '자동',
  manual: '수동',
};

function fmtQty(value) {
  const num = Number(value);
  return Number.isInteger(num) ? String(num) : String(value);
}

function renderPagination(page, totalPages) {
  const box = $('#requestPagination');
  if (!box) return;
  if (totalPages <= 1) {
    box.innerHTML = '';
    return;
  }
  box.innerHTML = `
    <button type="button" class="ghost small" id="reqPrevPage" ${page <= 1 ? 'disabled' : ''}>← 이전</button>
    <span>${page} / ${totalPages} 페이지</span>
    <button type="button" class="ghost small" id="reqNextPage" ${page >= totalPages ? 'disabled' : ''}>다음 →</button>
  `;
  box.querySelector('#reqPrevPage')?.addEventListener('click', () => {
    if (currentPage <= 1) return;
    currentPage -= 1;
    search();
  });
  box.querySelector('#reqNextPage')?.addEventListener('click', () => {
    if (currentPage >= totalPages) return;
    currentPage += 1;
    search();
  });
}

function actionsHtml(item) {
  if (item.status === 'requested') {
    if (window.IS_ADMIN) {
      return `<button type="button" class="primary small approve-btn" data-id="${item.id}">승인</button>`;
    }
    return '<span class="status">요청됨</span>';
  }

  if (item.status === 'approved') {
    if (window.IS_ADMIN) {
      return `<button type="button" class="primary small arrive-btn" data-id="${item.id}">물품도착</button>`;
    }
    return '<span class="status completed">승인완료</span>';
  }

  return '<span class="status completed">입고완료</span>';
}

async function search() {
  const table = $('#requestTable');
  const meta = $('#requestMeta');
  if (!table || !meta) return;

  meta.textContent = '조회 중…';

  const params = new URLSearchParams({
    page: String(currentPage),
    page_size: '10',
    q: $('#requestSearch')?.value.trim() || '',
    status: $('#requestStatus')?.value || '',
    date: $('#requestDate')?.value || '',
  });

  try {
    const response = await fetch(`/api/stockrequest?${params.toString()}`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '요청 목록을 불러오지 못했습니다.');

    const items = data.items || [];

    table.querySelector('tbody').innerHTML = items.map((item) => `
      <tr data-identifier="${esc(item.identifier || '')}">
        <td>${esc(item.created_at)}</td>
        <td>${esc(SOURCE_LABEL[item.source] || item.source)}</td>
        <td>${esc(item.identifier || '')}</td>
        <td>${esc(item.item_name || '')}</td>
        <td>${esc(item.site || '')}</td>
        <td>${fmtQty(item.quantity)}ea</td>
        <td>${esc(item.reason || '')}</td>
        <td>${esc(item.requested_by || '-')}</td>
        <td><span class="status ${item.status === 'arrived' ? 'completed' : ''}">${esc(STATUS_LABEL[item.status] || item.status)}</span></td>
        <td>${actionsHtml(item)}</td>
      </tr>
    `).join('') || '<tr><td class="empty" colspan="10">요청 내역이 없습니다.</td></tr>';

    currentPage = data.page || 1;
    renderPagination(currentPage, data.total_pages || 1);
    meta.textContent = `총 ${data.count || 0}건`;

    table.querySelectorAll('.approve-btn').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        approve(button);
      });
    });
    table.querySelectorAll('.arrive-btn').forEach((button) => {
      button.addEventListener('click', (event) => {
        event.stopPropagation();
        arrive(button);
      });
    });

    if (window.IS_ADMIN) {
      table.querySelectorAll('tbody tr[data-identifier]:not([data-identifier=""])').forEach((tr) => {
        tr.classList.add('row-clickable');
        tr.addEventListener('click', () => {
          window.location.href = '/ebay/' + encodeURIComponent(tr.dataset.identifier);
        });
      });
    }
  } catch (error) {
    meta.textContent = error.message;
  }
}

async function approve(button) {
  const id = button.dataset.id;
  button.disabled = true;
  button.textContent = '처리 중…';

  try {
    const response = await fetch(`/api/stockrequest/${id}/approve`, {method: 'POST'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '승인에 실패했습니다.');
    await search();
    showResultModal('승인되었습니다.', 'success');
  } catch (error) {
    button.disabled = false;
    button.textContent = '승인';
    showResultModal('승인 실패하였습니다. ' + error.message, 'error');
  }
}

async function arrive(button) {
  const id = button.dataset.id;
  button.disabled = true;
  button.textContent = '처리 중…';

  try {
    const response = await fetch(`/api/stockrequest/${id}/arrive`, {method: 'POST'});
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || '물품도착 처리에 실패했습니다.');
    await search();
    showResultModal('입고되었습니다.', 'success');
  } catch (error) {
    button.disabled = false;
    button.textContent = '물품도착';
    showResultModal('입고 실패하였습니다. ' + error.message, 'error');
  }
}

$('#requestSearch')?.addEventListener('input', () => {
  clearTimeout(timer);
  currentPage = 1;
  timer = setTimeout(search, 250);
});

$('#requestDate')?.addEventListener('change', () => {
  currentPage = 1;
  search();
});

$('#requestStatus')?.addEventListener('change', () => {
  currentPage = 1;
  search();
});

search();
