/*
 * Ultron dashboard front-end. Vanilla JS, no build step — pywebview loads
 * this straight from disk and calls the functions below via evaluate_js()
 * (or window.pywebview.api.* for the reverse direction, if ever needed).
 */

const AUTO_DISMISS_MS = 30000;
const cardTimers = {};

function setStatus(state) {
  const el = document.getElementById('status-text');
  const normalized = (state || 'idle').toLowerCase();
  el.textContent = normalized.toUpperCase();
  el.className = normalized;
}

function _escapeHtml(str) {
  const div = document.createElement('div');
  div.textContent = str == null ? '' : String(str);
  return div.innerHTML;
}

function _renderCardContent(type, content) {
  // `content` can be a plain string, or a structured payload we know how to
  // format nicely (news articles, weather, search results).
  if (typeof content === 'string') {
    return `<p>${_escapeHtml(content)}</p>`;
  }

  if (type === 'news' && Array.isArray(content.articles)) {
    return content.articles.map(a => `
      <div class="card-item">
        <a class="card-item-title" href="#" onclick="return false;">${_escapeHtml(a.title)}</a>
        <span class="card-item-meta">${_escapeHtml(a.source || '')} &middot; ${_escapeHtml(a.published_at || '')}</span>
      </div>
    `).join('');
  }

  if (type === 'weather' && content.temp !== undefined) {
    return `
      <div class="card-item">
        <span class="card-item-title">${_escapeHtml(content.location)}</span>
        <span class="card-item-meta">${_escapeHtml(content.condition)}</span>
      </div>
      <div class="card-item">${content.temp}&deg;F &middot; Humidity ${content.humidity}% &middot; Wind ${content.wind_speed} mph</div>
    `;
  }

  if (type === 'search' && Array.isArray(content.results)) {
    return content.results.map(r => `
      <div class="card-item">
        <a class="card-item-title" href="#" onclick="return false;">${_escapeHtml(r.title)}</a>
        <div class="card-item-meta">${_escapeHtml(r.snippet || '')}</div>
      </div>
    `).join('');
  }

  if (type === 'system' && content.cpu_percent !== undefined) {
    const battery = content.battery
      ? `Battery ${content.battery.percent}% ${content.battery.plugged_in ? '(charging)' : ''}`
      : 'No battery';
    const procs = (content.top_processes || []).map(p =>
      `<div class="card-item-meta">${_escapeHtml(p.name)} — ${p.cpu_percent}%</div>`
    ).join('');
    return `
      <div class="card-item">CPU ${content.cpu_percent}% &middot; Mem ${content.memory_percent}%</div>
      <div class="card-item">${battery}</div>
      ${procs}
    `;
  }

  if (content.error) {
    return `<p style="color:#ff6b6b;">${_escapeHtml(content.error)}</p>`;
  }

  // Fallback: pretty-print whatever we got.
  return `<pre style="white-space:pre-wrap;">${_escapeHtml(JSON.stringify(content, null, 2))}</pre>`;
}

function showCard(type, title, content) {
  const card = document.getElementById(`card-${type}`);
  if (!card) {
    console.warn(`showCard: unknown card type '${type}'`);
    return;
  }

  const titleEl = card.querySelector('.card-title');
  const contentEl = card.querySelector('.card-content');
  if (title) titleEl.textContent = title;
  contentEl.innerHTML = _renderCardContent(type, content);

  card.hidden = false;
  // Force reflow so the transition re-triggers even if the card was already visible.
  void card.offsetWidth;
  card.classList.add('visible');

  if (cardTimers[type]) clearTimeout(cardTimers[type]);
  cardTimers[type] = setTimeout(() => hideCard(type), AUTO_DISMISS_MS);
}

function hideCard(type) {
  const card = document.getElementById(`card-${type}`);
  if (!card) return;

  card.classList.remove('visible');
  if (cardTimers[type]) {
    clearTimeout(cardTimers[type]);
    delete cardTimers[type];
  }
  setTimeout(() => { card.hidden = true; }, 400); // match CSS transition duration
}

let transcriptTimer = null;

function showTranscript(text) {
  const el = document.getElementById('transcript-text');
  el.textContent = text || '';
  el.classList.toggle('visible', Boolean(text));

  if (transcriptTimer) clearTimeout(transcriptTimer);
  if (text) {
    transcriptTimer = setTimeout(() => el.classList.remove('visible'), AUTO_DISMISS_MS);
  }
}

// Wire up card close buttons.
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.card-close').forEach(btn => {
    btn.addEventListener('click', () => hideCard(btn.dataset.card));
  });
});

// Expose to Python (pywebview's evaluate_js just calls these as globals, but
// attaching to window explicitly keeps intent obvious).
window.setStatus = setStatus;
window.showCard = showCard;
window.hideCard = hideCard;
window.showTranscript = showTranscript;
