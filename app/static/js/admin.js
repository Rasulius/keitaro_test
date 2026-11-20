document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('settings-form');
  const resultEl = document.getElementById('settings-result');
  const keyStatus = document.getElementById('api-key-status');
  if (!form) return;

  function setResult(html, isError = false) {
    if (!resultEl) return;
    resultEl.innerHTML = html;
    resultEl.classList.remove('hidden');
    resultEl.style.borderColor = isError ? '#fecaca' : '';
    resultEl.style.background = isError ? '#fef2f2' : '';
  }

  function setVal(id, value) {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = value == null ? '' : String(value);
  }

  function fillForm(s) {
    setVal('keitaro_url', s.keitaro_url || '');
    // never prefill secret; show status only
    setVal('keitaro_api_key', '');
    setVal('campaign_name_prefix', s.campaign_name_prefix || '');
    setVal('google_redirect_url', s.google_redirect_url || '');
    setVal('default_offer_id', s.default_offer_id);
    setVal('default_domain_id', s.default_domain_id);
    setVal('default_group_id', s.default_group_id);
    setVal('default_traffic_source_id', s.default_traffic_source_id);

    if (keyStatus) {
      if (s.keitaro_api_key_set) {
        keyStatus.textContent = `Ключ сохранён (${s.keitaro_api_key_masked || 'скрыт'}). Оставьте поле пустым, чтобы не менять.`;
      } else {
        keyStatus.textContent = 'Ключ не задан. Введите Admin API key из Keitaro.';
      }
    }
  }

  async function loadSettings() {
    try {
      const data = await api('/api/settings');
      fillForm((data && data.settings) || {});
    } catch (err) {
      setResult(`<div style="color:#991b1b"><strong>Ошибка загрузки настроек:</strong> ${escapeHtml(err.message)}</div>`, true);
    }
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = document.getElementById('save-settings-btn');
    const fd = new FormData(form);
    const numOrNull = (v) => {
      const s = (v ?? '').toString().trim();
      if (!s) return null;
      const n = Number(s);
      return Number.isFinite(n) ? n : null;
    };

    const payload = {
      keitaro_url: (fd.get('keitaro_url') || '').toString().trim(),
      // empty => backend keeps existing key
      keitaro_api_key: (fd.get('keitaro_api_key') || '').toString().trim(),
      campaign_name_prefix: (fd.get('campaign_name_prefix') || '').toString().trim(),
      google_redirect_url: (fd.get('google_redirect_url') || '').toString().trim(),
      default_offer_id: numOrNull(fd.get('default_offer_id')),
      default_domain_id: numOrNull(fd.get('default_domain_id')),
      default_group_id: numOrNull(fd.get('default_group_id')),
      default_traffic_source_id: numOrNull(fd.get('default_traffic_source_id')),
    };

    setLoading(btn, true, 'Сохранение...');
    try {
      const data = await api('/api/settings', { method: 'POST', body: payload });
      const s = (data && data.settings) || {};
      fillForm(s);
      setResult(`<div><strong>Настройки сохранены.</strong></div><div class="field-hint" style="margin-top:6px;">Локальный файл: <code>runtime_config.json</code> (не коммитить в Git).</div>`);
      showToast('Настройки сохранены', 'success');
    } catch (err) {
      setResult(`<div style="color:#991b1b"><strong>Ошибка:</strong> ${escapeHtml(err.message)}</div>`, true);
      showToast(err.message, 'error', 6000);
    } finally {
      setLoading(btn, false);
    }
  });

  loadSettings();
});