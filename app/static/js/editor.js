let currentCampaignId = null;
let editorState = null;
let addOfferStreamId = null;

function getCampaignIdInput() {
  return document.getElementById('campaign-id');
}

function setCampaignId(id) {
  currentCampaignId = id ? Number(id) : null;
  const input = getCampaignIdInput();
  if (input) input.value = currentCampaignId || '';
}

async function loadCampaignsList() {
  const select = document.getElementById('campaign-select');
  const qInput = document.getElementById('campaign-filter-q');
  const activeInput = document.getElementById('campaign-filter-active');
  const params = new URLSearchParams();
  const q = qInput ? qInput.value.trim() : '';
  if (q) params.set('q', q);
  if (activeInput && activeInput.checked) params.set('state', 'active');

  const qs = params.toString();
  try {
    const data = await api('/api/campaigns' + (qs ? `?${qs}` : ''));
    const items = data.items || [];
    if (!items.length) {
      select.innerHTML = '<option value="">— кампании не найдены —</option>';
    } else {
      select.innerHTML = '<option value="">— выбрать из списка —</option>' +
        items.map(c => {
          const state = c.state ? ` [${c.state}]` : '';
          return `<option value="${escapeHtml(c.id)}">${escapeHtml(c.id)} — ${escapeHtml(c.name || '')}${escapeHtml(state)}</option>`;
        }).join('');
    }
  } catch (err) {
    console.warn(err);
    if (select) select.innerHTML = '<option value="">— ошибка загрузки —</option>';
    showToast('Не удалось загрузить список кампаний: ' + err.message, 'error', 5000);
  }
}

async function loadEditorState(campaignId, { fetchRemote = false } = {}) {
  if (!campaignId) return;
  const btnFetch = document.getElementById('fetch-btn');
  const btnLoad = document.getElementById('load-state-btn');
  if (fetchRemote) setLoading(btnFetch, true, 'Fetch...');
  else setLoading(btnLoad, true, 'Загрузка...');
  try {
    const path = fetchRemote ? `/api/campaigns/${campaignId}/fetch` : `/api/campaigns/${campaignId}/editor`;
    const method = fetchRemote ? 'POST' : 'GET';
    const data = await api(path, { method });
    editorState = data;
    setCampaignId(campaignId);
    renderEditor();
    if (fetchRemote) showToast('Потоки загружены из Keitaro', 'success');
  } catch (err) {
    showToast(err.message, 'error', 6000);
  } finally {
    if (fetchRemote) setLoading(btnFetch, false);
    else setLoading(btnLoad, false);
  }
}

function renderEditor() {
  const info = document.getElementById('campaign-info');
  const container = document.getElementById('streams-container');
  if (!editorState) {
    info.textContent = '';
    container.innerHTML = '';
    return;
  }
  const camp = editorState.campaign || {};
  info.innerHTML = camp && camp.id
    ? `Кампания: <strong>${escapeHtml(camp.name || '')}</strong> (ID <code>${escapeHtml(camp.id)}</code>)`
    : '';

  const streams = editorState.streams || [];
  if (!streams.length) {
    container.innerHTML = `<div class="empty">Нет локального состояния потоков. Нажмите <strong>Fetch Streams</strong>, чтобы загрузить потоки из Keitaro.</div>`;
    return;
  }

  container.innerHTML = streams.map(renderStream).join('');
}

function renderStream(stream) {
  const dirty = !!stream.is_dirty;
  const draft = stream.draft || { offers: [] };
  const offers = draft.offers || [];
  const meta = stream.meta || {};
  const streamId = stream.keitaro_stream_id;
  const badge = dirty
    ? '<span class="badge yellow">Жёлтый: есть неопубликованные изменения</span>'
    : '<span class="badge green">Белый: опубликовано</span>';

  const header = `
    <div class="stream-header">
      <div>
        <div class="stream-title">${escapeHtml(stream.name || `Stream ${streamId}`)} <span class="muted">(ID ${escapeHtml(streamId)})</span></div>
        <div class="stream-meta">type: ${escapeHtml(stream.type || '-')}, schema: ${escapeHtml(stream.schema || '-')}, action: ${escapeHtml(meta.action_type || '-')} ${badge}</div>
      </div>
      <div class="stream-actions">
        <button class="btn primary small" data-action="push" data-stream="${streamId}" ${dirty ? '' : 'disabled'}>Push to KT</button>
        <button class="btn small" data-action="cancel" data-stream="${streamId}" ${dirty ? '' : 'disabled'}>Cancel</button>
        <button class="btn small" data-action="open-add" data-stream="${streamId}">+ Add offer</button>
      </div>
    </div>`;

  // Streams without offers: show simple block (per spec)
  const hasAnyOffers = offers.length > 0;
  if (!hasAnyOffers) {
    const note = `<div class="empty">Поток без офферов (детализация редиректов/фильтров не требуется). Можно добавить офферы через "Add offer".</div>`;
    return `<div class="stream-card ${dirty ? 'dirty' : ''}" data-stream-card="${streamId}">${header}${note}</div>`;
  }

  const rows = offers.map(o => renderOfferRow(streamId, o)).join('');
  const table = `
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Offer ID</th>
            <th>Название</th>
            <th>Вес (%)</th>
            <th>Pin</th>
            <th>Статус</th>
            <th>Действия</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
  return `<div class="stream-card ${dirty ? 'dirty' : ''}" data-stream-card="${streamId}">${header}${table}</div>`;
}

function renderOfferRow(streamId, offer) {
  const removed = offer.status === 'removed';
  const share = Number(offer.share || 0);
  const pinned = !!offer.pinned && !removed;
  const statusLabel = removed ? 'Removed / архив (серый, 0%)' : 'Active';
  const pinCell = removed
    ? '<span class="muted">—</span>'
    : `<div class="pin-box">
        <label class="inline" style="flex-direction:row;align-items:center;gap:6px;font-size:0.85rem;">
          <input type="checkbox" data-action="toggle-pin" data-stream="${streamId}" data-offer="${offer.offer_id}" ${pinned ? 'checked' : ''} /> pin
        </label>
        <input type="number" min="0" max="100" step="1" value="${escapeHtml(pinned ? share : share)}" data-action="pin-share" data-stream="${streamId}" data-offer="${offer.offer_id}" ${pinned ? '' : 'disabled'} title="Вес (для закрепления)" />
      </div>`;

  const actions = removed
    ? `<button class="btn small success" data-action="bring-back" data-stream="${streamId}" data-offer="${offer.offer_id}">Bring Back</button>`
    : `<button class="btn small danger" data-action="remove" data-stream="${streamId}" data-offer="${offer.offer_id}">Remove</button>`;

  return `
    <tr class="${removed ? 'removed' : ''}">
      <td><code>${escapeHtml(offer.offer_id)}</code></td>
      <td class="name">${escapeHtml(offer.name || '')}</td>
      <td><strong>${escapeHtml(share)}%</strong></td>
      <td>${pinCell}</td>
      <td>${escapeHtml(statusLabel)}</td>
      <td class="row-actions">${actions}</td>
    </tr>`;
}

function replaceStreamInState(updatedStream) {
  if (!editorState || !Array.isArray(editorState.streams)) return;
  const idx = editorState.streams.findIndex(s => Number(s.keitaro_stream_id) === Number(updatedStream.keitaro_stream_id));
  if (idx >= 0) editorState.streams[idx] = updatedStream;
  else editorState.streams.push(updatedStream);
}

async function doStreamAction(action, streamId, payload = {}) {
  try {
    let res;
    if (action === 'push') {
      res = await api('/api/editor/streams/push', { method: 'POST', body: { keitaro_stream_id: streamId } });
      showToast('Изменения опубликованы в Keitaro', 'success');
    } else if (action === 'cancel') {
      res = await api('/api/editor/streams/cancel', { method: 'POST', body: { keitaro_stream_id: streamId } });
      showToast('Изменения отменены', 'success');
    } else if (action === 'remove') {
      res = await api('/api/editor/offers/remove', { method: 'POST', body: { keitaro_stream_id: streamId, offer_id: payload.offerId } });
    } else if (action === 'bring-back') {
      res = await api('/api/editor/offers/bring-back', { method: 'POST', body: { keitaro_stream_id: streamId, offer_id: payload.offerId } });
    } else if (action === 'pin') {
      res = await api('/api/editor/offers/pin', { method: 'POST', body: { keitaro_stream_id: streamId, offer_id: payload.offerId, pinned: payload.pinned, share: payload.share } });
    }
    if (res) {
      replaceStreamInState(res);
      renderEditor();
    }
  } catch (err) {
    showToast(err.message, 'error', 6000);
  }
}

function openAddOfferModal(streamId) {
  addOfferStreamId = Number(streamId);
  document.getElementById('offer-search').value = '';
  document.getElementById('offer-search-results').innerHTML = '<div class="empty">Введите запрос и нажмите «Найти».</div>';
  document.getElementById('add-offer-modal').classList.remove('hidden');
}

function closeAddOfferModal() {
  addOfferStreamId = null;
  document.getElementById('add-offer-modal').classList.add('hidden');
}

async function searchOffers() {
  const q = (document.getElementById('offer-search').value || '').trim();
  const results = document.getElementById('offer-search-results');
  results.innerHTML = '<div class="empty">Поиск...</div>';
  try {
    const data = await api(`/api/offers/search?q=${encodeURIComponent(q)}`);
    const items = data.items || [];
    if (!items.length) {
      results.innerHTML = '<div class="empty">Ничего не найдено.</div>';
      return;
    }
    results.innerHTML = items.map(o => `
      <div class="offer-item">
        <div>
          <div><strong>${escapeHtml(o.name || '(без названия)')}</strong></div>
          <div class="muted">ID: <code>${escapeHtml(o.id)}</code> ${o.state ? `• ${escapeHtml(o.state)}` : ''}</div>
        </div>
        <button class="btn primary small" data-action="add-offer" data-offer-id="${escapeHtml(o.id)}" data-offer-name="${escapeHtml(o.name || '')}">Добавить</button>
      </div>
    `).join('');
  } catch (err) {
    results.innerHTML = `<div class="empty" style="color:#991b1b">${escapeHtml(err.message)}</div>`;
  }
}

async function addOffer(offerId, offerName) {
  if (!addOfferStreamId) return;
  try {
    const res = await api('/api/editor/offers/add', {
      method: 'POST',
      body: { keitaro_stream_id: addOfferStreamId, offer_id: Number(offerId), name: offerName || null }
    });
    replaceStreamInState(res);
    renderEditor();
    closeAddOfferModal();
    showToast('Оффер добавлен в черновик (поток жёлтый до Push)', 'success');
  } catch (err) {
    showToast(err.message, 'error', 6000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const urlParams = new URLSearchParams(window.location.search);
  const cid = urlParams.get('campaign_id');
  if (cid) setCampaignId(cid);

  document.getElementById('refresh-campaigns-btn').addEventListener('click', loadCampaignsList);
  document.getElementById('campaign-select').addEventListener('change', (e) => {
    const val = e.target.value;
    if (val) {
      setCampaignId(val);
      loadEditorState(Number(val));
    }
  });

  const filterQ = document.getElementById('campaign-filter-q');
  const filterActive = document.getElementById('campaign-filter-active');
  if (filterQ) {
    filterQ.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        loadCampaignsList();
      }
    });
  }
  if (filterActive) {
    filterActive.addEventListener('change', loadCampaignsList);
  }
  document.getElementById('load-state-btn').addEventListener('click', () => {
    const id = Number(getCampaignIdInput().value);
    if (!id) return showToast('Укажите ID кампании', 'error');
    loadEditorState(id, { fetchRemote: false });
  });
  document.getElementById('fetch-btn').addEventListener('click', () => {
    const id = Number(getCampaignIdInput().value);
    if (!id) return showToast('Укажите ID кампании', 'error');
    loadEditorState(id, { fetchRemote: true });
  });

  document.getElementById('streams-container').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    const streamId = Number(btn.dataset.stream);
    if (action === 'push' || action === 'cancel') {
      doStreamAction(action, streamId);
    } else if (action === 'remove' || action === 'bring-back') {
      doStreamAction(action, streamId, { offerId: Number(btn.dataset.offer) });
    } else if (action === 'open-add') {
      openAddOfferModal(streamId);
    } else if (action === 'toggle-pin') {
      const checked = e.target.checked;
      const row = e.target.closest('tr');
      const shareInput = row ? row.querySelector('input[data-action="pin-share"]') : null;
      if (shareInput) shareInput.disabled = !checked;
      const shareVal = shareInput ? Number(shareInput.value || 0) : undefined;
      doStreamAction('pin', streamId, { offerId: Number(btn.dataset.offer), pinned: checked, share: checked ? shareVal : undefined });
    }
  });

  // Handle pin share change on blur/change
  document.getElementById('streams-container').addEventListener('change', (e) => {
    const el = e.target.closest('input[data-action="pin-share"]');
    if (!el) return;
    const row = el.closest('tr');
    const pinCheckbox = row ? row.querySelector('input[data-action="toggle-pin"]') : null;
    if (!pinCheckbox || !pinCheckbox.checked) return;
    const streamId = Number(el.dataset.stream);
    const offerId = Number(el.dataset.offer);
    const share = Number(el.value || 0);
    doStreamAction('pin', streamId, { offerId, pinned: true, share });
  });

  document.getElementById('close-modal-btn').addEventListener('click', closeAddOfferModal);
  document.getElementById('add-offer-modal').addEventListener('click', (e) => {
    if (e.target.id === 'add-offer-modal') closeAddOfferModal();
  });
  document.getElementById('search-offers-btn').addEventListener('click', searchOffers);
  document.getElementById('offer-search').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); searchOffers(); }
  });
  document.getElementById('offer-search-results').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-action="add-offer"]');
    if (!btn) return;
    addOffer(btn.dataset.offerId, btn.dataset.offerName);
  });

  loadCampaignsList();
  if (currentCampaignId) {
    loadEditorState(currentCampaignId, { fetchRemote: false });
  }
});
