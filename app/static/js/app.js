function escHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[c]));
}

function showResultModal(message, type) {
  document.querySelectorAll('.result-modal-overlay').forEach((el) => el.remove());

  const overlay = document.createElement('div');
  overlay.className = 'result-modal-overlay';
  overlay.innerHTML = `
    <div class="result-modal-box ${type === 'error' ? 'error' : 'success'}">
      <div class="result-modal-icon">${type === 'error' ? '✕' : '✓'}</div>
      <p class="result-modal-message">${escHtml(message)}</p>
      <button type="button" class="primary result-modal-ok">확인</button>
    </div>
  `;
  document.body.appendChild(overlay);

  const close = () => overlay.remove();
  overlay.querySelector('.result-modal-ok').addEventListener('click', close);
  overlay.addEventListener('click', (event) => {
    if (event.target === overlay) close();
  });

  const timer = setTimeout(close, 2600);
  overlay.querySelector('.result-modal-ok').addEventListener('click', () => clearTimeout(timer));
}

window.showResultModal = showResultModal;

document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('flash-data');
  if (!el) return;

  try {
    const messages = JSON.parse(el.textContent);
    messages.forEach(([category, message], index) => {
      setTimeout(() => showResultModal(message, category === 'error' ? 'error' : 'success'), index * 2800);
    });
  } catch (error) {
    console.error('flash 메시지 파싱 실패', error);
  }
});
