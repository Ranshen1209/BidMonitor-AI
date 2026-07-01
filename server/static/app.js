const API = '';
let currentConfig = {}, currentContacts = [], currentSites = [], currentCustomSites = [], editingContactIndex = -1;
let nextRunTime = null, countdownInterval = null;

function syncNavTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        if (!tab.dataset.page) {
            const match = tab.getAttribute('onclick') && tab.getAttribute('onclick').match(/showPage\('([^']+)'\)/);
            if (match) tab.dataset.page = match[1];
        }
    });
}

function showPage(name, tabElement) {
    syncNavTabs();
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('page-' + name).classList.add('active');
    const activeTab = tabElement || document.querySelector('.nav-tab[data-page="' + name + '"]');
    if (activeTab) activeTab.classList.add('active');
    if (name === 'results') loadResults();
    if (name === 'config') loadConfig();
    if (name === 'sites') loadSites();
    if (name === 'contacts') loadContacts();
}

async function refreshAll() { await refreshStatus(); loadLogs(); }

async function refreshStatus() {
    try {
        console.log('[DEBUG] Calling /api/status'); const res = await fetch(API + '/api/status');
        const data = await res.json();
        const dot = document.getElementById('statusDot'), text = document.getElementById('statusText');
        if (data.is_running) {
            dot.className = 'status-dot running'; text.textContent = '监控中';
            document.getElementById('btnStart').disabled = true;
            document.getElementById('btnStop').disabled = false;
        } else {
            dot.className = 'status-dot stopped'; text.textContent = '已停止';
            document.getElementById('btnStart').disabled = false;
            document.getElementById('btnStop').disabled = true;
        }
        document.getElementById('todayNew').textContent = data.today_new || 0;
        document.getElementById('todayRounds').textContent = data.today_rounds || 0;
        document.getElementById('totalBids').textContent = data.total_bids || 0;

        if (data.is_running && data.next_run_time) {
            nextRunTime = new Date(data.next_run_time.replace(' ', 'T'));
            document.getElementById('countdownBox').style.display = 'block';
            startCountdown();
        } else {
            nextRunTime = null;
            document.getElementById('countdownBox').style.display = 'none';
            if (countdownInterval) clearInterval(countdownInterval);
        }

        if (data.is_crawling && data.progress_total > 0) {
            document.getElementById('progressBox').style.display = 'block';
            document.getElementById('progressText').textContent = data.progress_current + '/' + data.progress_total;
            const percent = Math.round((data.progress_current / data.progress_total) * 100);
            document.getElementById('progressBar').style.width = percent + '%';
            document.getElementById('progressSite').textContent = data.progress_site || '准备中...';
        } else {
            document.getElementById('progressBox').style.display = 'none';
        }

        if (data.next_run_time) {
            document.getElementById('nextRun').textContent = '下次: ' + data.next_run_time.split(' ')[1];
        } else {
            document.getElementById('nextRun').textContent = '';
        }
    } catch (e) {
        console.error(e);
        document.getElementById('statusText').textContent = '连接失败';
        document.getElementById('statusDot').className = 'status-dot stopped';
    }
}

function startCountdown() {
    if (countdownInterval) clearInterval(countdownInterval);
    updateCountdown();
    countdownInterval = setInterval(updateCountdown, 1000);
}

function updateCountdown() {
    if (!nextRunTime) return;
    const now = new Date();
    const diff = Math.max(0, Math.floor((nextRunTime - now) / 1000));
    const mins = Math.floor(diff / 60);
    const secs = diff % 60;
    document.getElementById('countdownValue').textContent =
        String(mins).padStart(2, '0') + ':' + String(secs).padStart(2, '0');
    if (diff <= 0) {
        document.getElementById('countdownValue').textContent = '检索中...';
    }
}

async function loadLogs() {
    try {
        const res = await fetch(API + '/api/logs?limit=50');
        const data = await res.json();
        const c = document.getElementById('logsContainer');
        const isNearBottom = (c.scrollHeight - c.scrollTop - c.clientHeight) < 50;
        if (data.logs && data.logs.length > 0) {
            c.innerHTML = data.logs.map(log => {
                let cls = 'log-line';
                if (log.includes('✅') || log.includes('成功') || log.includes('[OK]')) cls += ' success';
                else if (log.includes('❌') || log.includes('失败') || log.includes('[ERROR]') || log.includes('[FAILED]')) cls += ' error';
                return `<div class="${cls}">${escapeHtml(log)}</div>`;
            }).join('');
            if (isNearBottom) {
                c.scrollTop = c.scrollHeight;
            }
        } else {
            c.innerHTML = '<div class="log-line">暂无日志</div>';
        }
    } catch (e) {
        console.error(e);
        document.getElementById('logsContainer').innerHTML = '<div class="log-line error">无法加载日志</div>';
    }
}

function safeResultUrl(url) {
    if (!url) return '#';
    try {
        const parsed = new URL(url, window.location.origin);
        if (parsed.protocol === 'http:' || parsed.protocol === 'https:') return parsed.href;
    } catch (e) {
        console.warn('Invalid result URL', e);
    }
    return '#';
}

async function loadResults() {
    try {
        const res = await fetch(API + '/api/results?limit=50');
        const data = await res.json();
        const c = document.getElementById('resultsList');
        if (data.items && data.items.length > 0) {
            c.innerHTML = data.items.map(i => {
                const href = safeResultUrl(i.url);
                return `<div class="result-item"><div class="result-title"><a href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(i.title)}</a></div><div class="result-meta"><span>📅 ${i.pub_date || '未知'}</span><span>📍 ${escapeHtml(i.source)}</span></div></div>`;
            }).join('');
        } else {
            c.innerHTML = '<div class="empty-state"><div class="empty-state-icon">📭</div><div>暂无招标信息</div></div>';
        }
    } catch (e) {
        console.error(e);
        document.getElementById('resultsList').innerHTML = '<div class="empty-state"><div class="empty-state-icon">⚠️</div><div>加载失败，请刷新重试</div></div>';
    }
}

async function loadConfig() {
    try {
        const res = await fetch(API + '/api/config');
        currentConfig = await res.json();
        document.getElementById('cfgKeywords').value = currentConfig.keywords || '';
        document.getElementById('cfgExclude').value = currentConfig.exclude || '';
        document.getElementById('cfgMustContain').value = currentConfig.must_contain || '';
        document.getElementById('cfgInterval').value = currentConfig.interval || 20;
        document.getElementById('cfgSelenium').checked = currentConfig.use_selenium || false;
    } catch (e) { console.error(e); }
}

async function saveConfig() {
    try {
        currentConfig.keywords = document.getElementById('cfgKeywords').value;
        currentConfig.exclude = document.getElementById('cfgExclude').value;
        currentConfig.must_contain = document.getElementById('cfgMustContain').value;
        currentConfig.interval = parseInt(document.getElementById('cfgInterval').value);
        currentConfig.use_selenium = document.getElementById('cfgSelenium').checked;
        await fetch(API + '/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentConfig) });
        alert('配置已保存！');
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function loadSites() {
    try {
        const res = await fetch(API + '/api/sites');
        currentSites = await res.json();
        renderSites();
        loadCustomSites();
    } catch (e) {
        console.error(e);
        document.getElementById('sitesList').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

function renderSites() {
    const c = document.getElementById('sitesList');
    if (currentSites.length > 0) {
        c.innerHTML = currentSites.map((s, i) => `<div class="checkbox-item"><input type="checkbox" id="site_${i}" ${s.enabled ? 'checked' : ''} onchange="currentSites[${i}].enabled=this.checked"><label for="site_${i}">${escapeHtml(s.name)}</label></div>`).join('');
    } else {
        c.innerHTML = '<div class="empty-state">暂无网站配置</div>';
    }
}

async function loadCustomSites() {
    try {
        const res = await fetch(API + '/api/custom-sites');
        currentCustomSites = await res.json();
        renderCustomSites();
    } catch (e) {
        console.error(e);
        currentCustomSites = [];
        renderCustomSites();
    }
}

function renderCustomSites() {
    const c = document.getElementById('customSitesList');
    if (currentCustomSites.length > 0) {
        c.innerHTML = currentCustomSites.map((s, i) => `<div class="list-item"><div class="list-item-content"><div class="list-item-title">${escapeHtml(s.name)}</div><div class="list-item-subtitle">${escapeHtml(s.url)}</div></div><div class="list-item-actions"><button class="btn btn-sm btn-danger" onclick="deleteCustomSite(${i})">删除</button></div></div>`).join('');
    } else {
        c.innerHTML = '<div class="empty-state" style="padding:20px"><div class="empty-state-icon">🔗</div><div>暂无自定义网站</div></div>';
    }
}

function showAddCustomSite() {
    document.getElementById('customSiteName').value = '';
    document.getElementById('customSiteUrl').value = '';
    document.getElementById('customSiteModal').classList.add('active');
}

async function saveCustomSite() {
    const name = document.getElementById('customSiteName').value.trim();
    const url = document.getElementById('customSiteUrl').value.trim();
    if (!name || !url) { alert('请填写网站名称和URL'); return; }
    currentCustomSites.push({ name, url });
    try {
        await fetch(API + '/api/custom-sites', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentCustomSites) });
        closeModal('customSiteModal');
        renderCustomSites();
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function deleteCustomSite(i) {
    if (!confirm('确定删除此自定义网站？')) return;
    currentCustomSites.splice(i, 1);
    try {
        await fetch(API + '/api/custom-sites', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentCustomSites) });
        renderCustomSites();
    } catch (e) { alert('删除失败: ' + e.message); }
}

function selectAllSites() { currentSites.forEach(s => s.enabled = true); renderSites(); }
function deselectAllSites() { currentSites.forEach(s => s.enabled = false); renderSites(); }

async function saveSites() {
    try {
        const enabledSites = currentSites.filter(s => s.enabled).map(s => s.key);
        await fetch(API + '/api/sites', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(enabledSites) });
        alert('网站配置已保存！');
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function loadContacts() {
    try {
        const res = await fetch(API + '/api/contacts');
        currentContacts = await res.json();
        renderContacts();
    } catch (e) {
        console.error(e);
        document.getElementById('contactsList').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

function renderContacts() {
    const c = document.getElementById('contactsList');
    if (currentContacts.length > 0) {
        c.innerHTML = currentContacts.map((x, i) => `<div class="list-item"><div class="list-item-content"><div class="list-item-title">${escapeHtml(x.name)} ${x.enabled ? '✅' : '❌'}</div><div class="list-item-subtitle">${x.phone || ''} ${x.email || ''}</div></div><div class="list-item-actions"><button class="btn btn-sm btn-outline" onclick="editContact(${i})">编辑</button><button class="btn btn-sm btn-danger" onclick="deleteContact(${i})">删除</button></div></div>`).join('');
    } else {
        c.innerHTML = '<div class="empty-state"><div class="empty-state-icon">👥</div><div>暂无联系人</div></div>';
    }
}

function showAddContact() {
    editingContactIndex = -1;
    document.getElementById('contactModalTitle').textContent = '添加联系人';
    document.getElementById('contactName').value = '';
    document.getElementById('contactPhone').value = '';
    document.getElementById('contactEmail').value = '';
    document.getElementById('contactEmailType').value = 'QQ邮箱';
    document.getElementById('contactEmailPassword').value = '';
    document.getElementById('contactWechatToken').value = '';
    document.getElementById('contactEnabled').checked = true;
    document.getElementById('contactModal').classList.add('active');
}

function editContact(i) {
    editingContactIndex = i;
    const c = currentContacts[i];
    document.getElementById('contactModalTitle').textContent = '编辑联系人';
    document.getElementById('contactName').value = c.name || '';
    document.getElementById('contactPhone').value = c.phone || '';
    document.getElementById('contactEmail').value = c.email || '';
    document.getElementById('contactEmailType').value = c.email_type || 'QQ邮箱';
    document.getElementById('contactEmailPassword').value = c.email_password || '';
    document.getElementById('contactWechatToken').value = c.wechat_token || '';
    document.getElementById('contactEnabled').checked = c.enabled !== false;
    document.getElementById('contactModal').classList.add('active');
}

function closeContactModal() { document.getElementById('contactModal').classList.remove('active'); }

async function saveContact() {
    const contact = {
        name: document.getElementById('contactName').value,
        phone: document.getElementById('contactPhone').value,
        email: document.getElementById('contactEmail').value,
        email_type: document.getElementById('contactEmailType').value,
        email_password: document.getElementById('contactEmailPassword').value,
        wechat_token: document.getElementById('contactWechatToken').value,
        enabled: document.getElementById('contactEnabled').checked
    };
    if (!contact.name) { alert('请输入姓名'); return; }
    if (editingContactIndex >= 0) {
        if (!contact.email_password) contact.email_password = currentContacts[editingContactIndex].email_password;
        currentContacts[editingContactIndex] = contact;
    } else {
        currentContacts.push(contact);
    }
    try {
        await fetch(API + '/api/contacts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentContacts) });
        closeContactModal();
        renderContacts();
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function deleteContact(i) {
    if (!confirm('确定删除此联系人？')) return;
    currentContacts.splice(i, 1);
    try {
        await fetch(API + '/api/contacts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentContacts) });
        renderContacts();
    } catch (e) { alert('删除失败: ' + e.message); }
}

function closeModal(id) { document.getElementById(id).classList.remove('active'); }

function showSmsConfig() {
    document.getElementById('smsEnabled').checked = currentConfig.sms_enabled || false;
    const sc = currentConfig.sms_config || {};
    document.getElementById('smsAkid').value = sc.access_key_id || '';
    document.getElementById('smsAksecret').value = sc.access_key_secret || '';
    document.getElementById('smsSign').value = sc.sign_name || '';
    document.getElementById('smsTemplate').value = sc.template_code || '';
    document.getElementById('smsTestPhone').value = '';
    document.getElementById('smsModal').classList.add('active');
}

async function saveSmsConfig() {
    currentConfig.sms_enabled = document.getElementById('smsEnabled').checked;
    const newSecret = document.getElementById('smsAksecret').value;
    currentConfig.sms_config = {
        provider: 'aliyun',
        access_key_id: document.getElementById('smsAkid').value,
        access_key_secret: newSecret || (currentConfig.sms_config ? currentConfig.sms_config.access_key_secret : ''),
        sign_name: document.getElementById('smsSign').value,
        template_code: document.getElementById('smsTemplate').value
    };
    await saveFullConfig();
    closeModal('smsModal');
}

async function testSms() {
    const phone = document.getElementById('smsTestPhone').value;
    if (!phone) { alert('请输入测试手机号'); return; }
    await saveSmsConfig();
    try {
        const res = await fetch(API + '/api/test/sms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) });
        const data = await res.json();
        alert(data.message);
    } catch (e) { alert('测试失败: ' + e.message); }
}

function showVoiceConfig() {
    document.getElementById('voiceEnabled').checked = currentConfig.voice_enabled || false;
    const vc = currentConfig.voice_config || {};
    document.getElementById('voiceAkid').value = vc.access_key_id || '';
    document.getElementById('voiceAksecret').value = vc.access_key_secret || '';
    document.getElementById('voiceTtsCode').value = vc.tts_code || '';
    document.getElementById('voiceShowNumber').value = vc.called_show_number || '';
    document.getElementById('voiceTestPhone').value = '';
    document.getElementById('voiceModal').classList.add('active');
}

async function saveVoiceConfig() {
    currentConfig.voice_enabled = document.getElementById('voiceEnabled').checked;
    const newSecret = document.getElementById('voiceAksecret').value;
    currentConfig.voice_config = {
        provider: 'aliyun',
        access_key_id: document.getElementById('voiceAkid').value,
        access_key_secret: newSecret || (currentConfig.voice_config ? currentConfig.voice_config.access_key_secret : ''),
        tts_code: document.getElementById('voiceTtsCode').value,
        called_show_number: document.getElementById('voiceShowNumber').value
    };
    await saveFullConfig();
    closeModal('voiceModal');
}

async function testVoice() {
    const phone = document.getElementById('voiceTestPhone').value;
    if (!phone) { alert('请输入测试手机号'); return; }
    await saveVoiceConfig();
    try {
        const res = await fetch(API + '/api/test/voice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) });
        const data = await res.json();
        alert(data.message);
    } catch (e) { alert('测试失败: ' + e.message); }
}

function showAiConfig() {
    document.getElementById('aiEnabled').checked = currentConfig.ai_enabled || false;
    const ac = currentConfig.ai_config || {};
    document.getElementById('aiUrl').value = ac.base_url || ac.url || 'https://api.deepseek.com/chat/completions';
    document.getElementById('aiKey').value = ac.api_key || '';
    document.getElementById('aiModel').value = ac.model || 'deepseek-chat';
    document.getElementById('aiModal').classList.add('active');
}

async function saveAiConfig() {
    currentConfig.ai_enabled = document.getElementById('aiEnabled').checked;
    const newKey = document.getElementById('aiKey').value;
    currentConfig.ai_config = {
        enable: document.getElementById('aiEnabled').checked,
        base_url: document.getElementById('aiUrl').value,
        api_key: newKey || (currentConfig.ai_config ? currentConfig.ai_config.api_key : ''),
        model: document.getElementById('aiModel').value
    };
    await saveFullConfig();
    closeModal('aiModal');
}

async function testAi() {
    await saveAiConfig();
    try {
        const res = await fetch(API + '/api/test/ai', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
        const data = await res.json();
        alert(data.message);
    } catch (e) { alert('测试失败: ' + e.message); }
}

async function saveFullConfig() {
    try {
        await fetch(API + '/api/config/full', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentConfig) });
        alert('配置已保存！');
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function testContactNotify() {
    const phone = document.getElementById('contactPhone').value;
    const email = document.getElementById('contactEmail').value;
    const token = document.getElementById('contactWechatToken').value;
    if (!phone && !email && !token) { alert('请先输入手机号、邮箱或微信Token'); return; }
    let results = [];
    if (phone) {
        try {
            let res = await fetch(API + '/api/test/sms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) });
            let data = await res.json();
            results.push('短信: ' + data.message);
        } catch (e) { results.push('短信测试失败'); }
        try {
            let res = await fetch(API + '/api/test/voice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) });
            let data = await res.json();
            results.push('语音: ' + data.message);
        } catch (e) { results.push('语音测试失败'); }
    }
    if (email) {
        try {
            let res = await fetch(API + '/api/test/email', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ email }) });
            let data = await res.json();
            results.push('邮件: ' + data.message);
        } catch (e) { results.push('邮件测试失败'); }
    }
    if (token) {
        try {
            let res = await fetch(API + '/api/test/wechat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) });
            let data = await res.json();
            results.push('微信: ' + data.message);
        } catch (e) { results.push('微信测试失败'); }
    }
    alert(results.join('\n'));
}

async function startMonitor() {
    try {
        const res = await fetch(API + '/api/start', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
        refreshStatus();
        loadLogs();
    } catch (e) { alert('操作失败: ' + e.message); }
}

async function stopMonitor() {
    try {
        const res = await fetch(API + '/api/stop', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
        refreshStatus();
    } catch (e) { alert('操作失败: ' + e.message); }
}

async function runOnce() {
    try {
        const res = await fetch(API + '/api/run-once', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
        refreshStatus();
        setTimeout(loadLogs, 1000);
    } catch (e) { alert('操作失败: ' + e.message); }
}

async function clearLogs() {
    if (!confirm('确定要清除所有日志吗？')) return;
    try {
        await fetch(API + '/api/logs', { method: 'DELETE' });
        document.getElementById('logsContainer').innerHTML = '<div class="log-line">日志已清除</div>';
    } catch (e) { alert('清除失败: ' + e.message); }
}

async function clearHistory() {
    if (!confirm('确定要清空所有历史数据吗？')) return;
    try {
        const res = await fetch(API + '/api/history', { method: 'DELETE' });
        const data = await res.json();
        alert(data.message);
        refreshStatus();
    } catch (e) { alert('操作失败: ' + e.message); }
}

function escapeHtml(t) {
    if (!t) return '';
    const d = document.createElement('div');
    d.textContent = t;
    return d.innerHTML;
}

syncNavTabs();
refreshStatus();
loadLogs();
setInterval(refreshStatus, 5000);
setInterval(loadLogs, 5000);
