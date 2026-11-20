document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('create-campaign-form');
  const resultEl = document.getElementById('create-result');
  if (!form) return;

  function setRefStatus(msg, isError = false) {
    const el = document.getElementById('refs-status');
    if (!el) return;
    el.textContent = msg || '';
    el.style.color = isError ? '#b91c1c' : '';
  }

  function populateSelect(selectId, items, idField = 'id', nameField = 'name') {
    const select = document.getElementById(selectId);
    if (!select) return;
    const targetId = select.dataset.target;
    const targetInput = targetId ? document.getElementById(targetId) : null;
    const placeholder = select.dataset.placeholder || '— выберите —';
    const current = targetInput ? String(targetInput.value || '') : '';

    const opts = [`<option value="">${escapeHtml(placeholder)}</option>`];
    (items || []).forEach(item => {
      const id = item[idField];
      const name = item[nameField] ?? `ID ${id}`;
      const selected = String(id) === current ? ' selected' : '';
      opts.push(`<option value="${escapeHtml(id)}"${selected}>${escapeHtml(name)} (ID ${escapeHtml(id)})</option>`);
    });
    select.innerHTML = opts.join('');

    // If current value not in list but exists, keep ID visible (readonly) and add a synthetic option
    if (current && !Array.from(select.options).some(o => o.value === current)) {
      const opt = document.createElement('option');
      opt.value = current;
      opt.textContent = `Текущее значение (ID ${current})`;
      opt.selected = true;
      select.appendChild(opt);
    }

    // Ensure ID input matches selection
    if (targetInput) {
      targetInput.value = select.value || current || '';
    }
  }

  function bindSelect(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return;
    select.addEventListener('change', () => {
      const targetId = select.dataset.target;
      const targetInput = targetId ? document.getElementById(targetId) : null;
      if (targetInput) targetInput.value = select.value || '';
    });
  }

  function getNextCampaignSeq() {
    const key = 'campaign_seq';
    let n = parseInt(localStorage.getItem(key) || '0', 10);
    if (!Number.isFinite(n) || n < 0) n = 0;
    n += 1;
    localStorage.setItem(key, String(n));
    return n;
  }

  function generateCampaignName() {
    return `campaign_${getNextCampaignSeq()}`;
  }

  function setDefaultCampaignName(force = false) {
    const nameInput = document.getElementById('name');
    if (!nameInput) return;
    if (force || !nameInput.value.trim()) {
      nameInput.value = generateCampaignName();
    }
  }

  async function loadReferences() {
    bindSelect('domain_select');
    bindSelect('group_select');
    bindSelect('traffic_source_select');

    const results = await Promise.allSettled([
      api('/api/reference/domains'),
      api('/api/reference/groups?type=campaigns'),
      api('/api/reference/traffic-sources'),
    ]);

    const [domainsRes, groupsRes, sourcesRes] = results;
    let okCount = 0;

    if (domainsRes.status === 'fulfilled') {
      populateSelect('domain_select', domainsRes.value.items || []);
      okCount++;
    } else {
      const sel = document.getElementById('domain_select');
      if (sel) sel.innerHTML = '<option value="">Не удалось загрузить домены</option>';
    }

    if (groupsRes.status === 'fulfilled') {
      populateSelect('group_select', groupsRes.value.items || []);
      okCount++;
    } else {
      const sel = document.getElementById('group_select');
      if (sel) sel.innerHTML = '<option value="">Не удалось загрузить группы</option>';
    }

    if (sourcesRes.status === 'fulfilled') {
      populateSelect('traffic_source_select', sourcesRes.value.items || []);
      okCount++;
    } else {
      const sel = document.getElementById('traffic_source_select');
      if (sel) sel.innerHTML = '<option value="">Не удалось загрузить источники</option>';
    }

    if (okCount === 3) {
      setRefStatus('Справочники Keitaro загружены: выберите значения по названию, ID подставится автоматически.');
    } else if (okCount > 0) {
      setRefStatus('Часть справочников загружена. Для остальных проверьте подключение к Keitaro.', true);
    } else {
      setRefStatus('Не удалось загрузить справочники Keitaro. Проверьте KEITARO_URL/KEY и доступность API. Текущие ID из настроек сохранены (только для чтения).', true);
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('create-btn');
    const fd = new FormData(form);
    const payload = {
      name: (fd.get('name') || '').trim(),
      country_code: (fd.get('country_code') || '').trim(),
      offer_id: Number(fd.get('offer_id')),
      google_url: (fd.get('google_url') || '').trim() || null,
      domain_id: fd.get('domain_id') ? Number(fd.get('domain_id')) : null,
      group_id: fd.get('group_id') ? Number(fd.get('group_id')) : null,
      traffic_source_id: fd.get('traffic_source_id') ? Number(fd.get('traffic_source_id')) : null,
    };

    setLoading(btn, true, 'Создание...');
    resultEl.classList.add('hidden');
    try {
      const data = await api('/api/campaigns', { method: 'POST', body: payload });
      const camp = data.campaign || {};
      const errors = data.errors || [];
      let html = `<div><strong>Кампания создана</strong></div>`;
      html += `<div>ID: <code>${escapeHtml(camp.id)}</code></div>`;
      html += `<div>Название: <code>${escapeHtml(camp.name || '')}</code></div>`;
      if (camp.alias) html += `<div>Alias: <code>${escapeHtml(camp.alias)}</code></div>`;
      if (Array.isArray(data.streams) && data.streams.length) {
        html += `<div style="margin-top:8px"><strong>Потоки:</strong></div><ul>`;
        data.streams.forEach(s => {
          html += `<li>ID ${escapeHtml(s.id)} — ${escapeHtml(s.name || '')} (${escapeHtml(s.type || '')})</li>`;
        });
        html += `</ul>`;
      }
      if (errors.length) {
        html += `<div style="margin-top:8px;color:#b45309"><strong>Предупреждения/ошибки потоков:</strong><ul>${errors.map(e => `<li>${escapeHtml(e)}</li>`).join('')}</ul></div>`;
      }
      if (camp.id) {
        html += `<div style="margin-top:10px"><a class="btn primary" href="/editor?campaign_id=${encodeURIComponent(camp.id)}">Открыть в редакторе</a></div>`;
      }
      resultEl.innerHTML = html;
      resultEl.classList.remove('hidden');
      showToast('Кампания создана', 'success');

      // Reset only main fields; keep Keitaro selections/default IDs for convenience
      const keep = new Set(['domain_id', 'group_id', 'traffic_source_id', 'google_url']);
      Array.from(form.elements).forEach(el => {
        if (!el.name) return;
        if (keep.has(el.name)) return;
        if (el.type === 'submit' || el.type === 'button') return;
        if (el.name === 'name') return;
        el.value = '';
      });
      // restore ID inputs to current select values (they were kept anyway)
      ['domain_select','group_select','traffic_source_select'].forEach(id => {
        const sel = document.getElementById(id);
        const target = sel && sel.dataset.target ? document.getElementById(sel.dataset.target) : null;
        if (sel && target) target.value = sel.value || target.value || '';
      });
      // generate a new campaign name for the next creation
      setDefaultCampaignName(true);
    } catch (err) {
      resultEl.innerHTML = `<div style="color:#991b1b"><strong>Ошибка:</strong> ${escapeHtml(err.message)}</div>`;
      resultEl.classList.remove('hidden');
      showToast(err.message, 'error', 6000);
    } finally {
      setLoading(btn, false);
    }
  });

  setDefaultCampaignName(false);
  loadReferences();
});
