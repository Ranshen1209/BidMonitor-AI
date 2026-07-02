const API = '';
let currentConfig = {}, currentSites = [], currentUsers = [], currentUser = null;
let currentResults = [], resultSettings = null, selectedResultIds = new Set(), activeResultId = null;
let editingUserId = null;
let nextRunTime = null, countdownInterval = null;
let statusTimer = null, logsTimer = null;
const ACCESS_STATUS_OPTIONS = [
    { value: 'unknown', label: '未知' },
    { value: 'public_no_antibot', label: '公开可访问' },
    { value: 'login_no_antibot', label: '需登录' },
    { value: 'login_with_antibot', label: '登录+反爬' },
    { value: 'js_limited', label: 'JS受限' },
    { value: 'commercial_limited', label: '会员/商业限制' },
    { value: 'unavailable', label: '失效/不可用' },
];
const RESULT_LABELS = {
    fit_status: { pending: '待判断', fit: '适合', not_fit: '不适合' },
    follow_decision: { pending: '待判断', follow: '跟进', not_follow: '不跟进' },
    urgency: { low: '低', medium: '中', high: '高', urgent: '紧急' },
    project_stage: { lead: '线索', screening: '筛选', following: '跟进中', submitted: '已投', ended: '结束' },
};

async function apiFetch(path, options = {}) {
    const headers = options.headers || {};
    const res = await fetch(API + path, { ...options, headers });
    if (res.status === 401 && !path.startsWith('/api/auth/')) {
        showLoginView();
        throw new Error('未登录或会话已失效');
    }
    return res;
}

function icon(name, className = 'icon') {
    return `<svg class="${className}" aria-hidden="true"><use href="#icon-${name}"></use></svg>`;
}

function stripUiEmoji(text) {
    return String(text || '').replace(/[\u{1F000}-\u{1FAFF}\u2600-\u27BF]\uFE0F?/gu, '').trim();
}

function syncNavTabs() {
    document.querySelectorAll('.nav-tab').forEach(tab => {
        if (!tab.dataset.page) {
            const match = tab.getAttribute('onclick') && tab.getAttribute('onclick').match(/showPage\('([^']+)'\)/);
            if (match) tab.dataset.page = match[1];
        }
    });
}

async function showPage(name, tabElement) {
    syncNavTabs();
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    document.getElementById('page-' + name).classList.add('active');
    const activeTab = tabElement || document.querySelector('.nav-tab[data-page="' + name + '"]');
    if (activeTab) activeTab.classList.add('active');
    if (name === 'results') {
        await loadResultSettings();
        await loadResults();
    }
    if (name === 'config') loadConfig();
    if (name === 'sites') loadSites();
    if (name === 'users') loadUsers();
}

async function refreshAll() { await refreshStatus(); loadLogs(); }

async function checkAuth() {
    try {
        const res = await apiFetch('/api/auth/me');
        if (!res.ok) throw new Error('not authenticated');
        const data = await res.json();
        currentUser = data.user;
        showAppShell();
        refreshAll();
        startTimers();
    } catch (e) {
        showLoginView();
    }
}

function showAppShell() {
    document.getElementById('loginView').classList.remove('active');
    document.getElementById('appShell').classList.add('active');
    document.getElementById('currentUserLabel').textContent = currentUser ? `${currentUser.username} · ${currentUser.role === 'admin' ? '管理员' : '用户'}` : '';
    document.querySelectorAll('[data-admin-only]').forEach(el => {
        el.classList.toggle('is-hidden', !(currentUser && currentUser.role === 'admin'));
    });
}

function showLoginView() {
    currentUser = null;
    document.getElementById('appShell').classList.remove('active');
    document.getElementById('loginView').classList.add('active');
    if (statusTimer) clearInterval(statusTimer);
    if (logsTimer) clearInterval(logsTimer);
    statusTimer = null;
    logsTimer = null;
}

function startTimers() {
    if (!statusTimer) statusTimer = setInterval(refreshStatus, 5000);
    if (!logsTimer) logsTimer = setInterval(loadLogs, 5000);
}

async function login(event) {
    event.preventDefault();
    const username = document.getElementById('loginUsername').value.trim();
    const password = document.getElementById('loginPassword').value;
    const errorBox = document.getElementById('loginError');
    errorBox.textContent = '';
    try {
        const res = await apiFetch('/api/auth/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.detail || data.message || '登录失败');
        currentUser = data.user;
        showAppShell();
        refreshAll();
        startTimers();
    } catch (e) {
        errorBox.textContent = e.message || '登录失败';
    }
}

async function logout() {
    try {
        await apiFetch('/api/auth/logout', { method: 'POST' });
    } finally {
        showLoginView();
    }
}

async function refreshStatus() {
    try {
        const res = await apiFetch('/api/status');
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

        const countdownBox = document.getElementById('countdownBox');
        const progressBox = document.getElementById('progressBox');

        if (data.is_running && data.next_run_time) {
            nextRunTime = new Date(data.next_run_time.replace(' ', 'T'));
            countdownBox.classList.add('is-visible');
            startCountdown();
        } else {
            nextRunTime = null;
            countdownBox.classList.remove('is-visible');
            if (countdownInterval) clearInterval(countdownInterval);
        }

        if (data.is_crawling && data.progress_total > 0) {
            progressBox.classList.add('is-visible');
            document.getElementById('progressText').textContent = data.progress_current + '/' + data.progress_total;
            const percent = Math.round((data.progress_current / data.progress_total) * 100);
            document.getElementById('progressBar').style.width = percent + '%';
            document.getElementById('progressSite').textContent = data.progress_site || '准备中...';
        } else {
            progressBox.classList.remove('is-visible');
        }

        document.getElementById('nextRun').textContent = data.next_run_time ? '下次: ' + data.next_run_time.split(' ')[1] : '';
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
        const res = await apiFetch('/api/logs?limit=50');
        const data = await res.json();
        const c = document.getElementById('logsContainer');
        const isNearBottom = (c.scrollHeight - c.scrollTop - c.clientHeight) < 50;
        if (data.logs && data.logs.length > 0) {
            c.innerHTML = data.logs.map(log => {
                let cls = 'log-line';
                if (/\u2705/.test(log) || log.includes('成功') || log.includes('[OK]')) cls += ' success';
                else if (/\u274c/i.test(log) || log.includes('失败') || log.includes('[ERROR]') || log.includes('[FAILED]')) cls += ' error';
                return `<div class="${cls}">${escapeHtml(stripUiEmoji(log))}</div>`;
            }).join('');
            if (isNearBottom) c.scrollTop = c.scrollHeight;
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

function buildResultQuery() {
    const params = new URLSearchParams({ limit: '50', offset: '0' });
    const mapping = {
        q: 'resultSearchInput',
        fit_status: 'resultFitStatusFilter',
        follow_decision: 'resultFollowDecisionFilter',
        urgency: 'resultUrgencyFilter',
        project_stage: 'resultProjectStageFilter',
        source: 'resultSourceFilter',
        region: 'resultRegionFilter',
        category: 'resultCategoryFilter',
    };
    Object.entries(mapping).forEach(([key, id]) => {
        const el = document.getElementById(id);
        const value = el ? el.value.trim() : '';
        if (value) params.set(key, value);
    });
    return params;
}

function renderStatusLabel(value, map) {
    return map[value] || value || '-';
}

function formatResultDate(value) {
    return value ? escapeHtml(value) : '-';
}

function renderAiStatus(item) {
    const status = item.ai_extract_status || item.detail_fetch_status || 'pending';
    return escapeHtml(status);
}

function renderResultsTable(data) {
    currentResults = Array.isArray(data.items) ? data.items : [];
    const body = document.getElementById('resultsTableBody');
    const selectAll = document.getElementById('resultsSelectAll');
    if (!currentResults.length) {
        body.innerHTML = '<tr><td colspan="15" class="table-empty"><div class="empty-state-compact">暂无结果</div></td></tr>';
        selectAll.checked = false;
        return;
    }

    body.innerHTML = currentResults.map(item => {
        const selected = selectedResultIds.has(item.id);
        const activeClass = item.id === activeResultId ? ' is-active' : '';
        const href = safeResultUrl(item.url);
        return `<tr class="result-row${activeClass}" data-result-id="${item.id}">
            <td><input type="checkbox" class="result-checkbox" ${selected ? 'checked' : ''} onchange="toggleResultSelection(${item.id}, this.checked)"></td>
            <td><button class="result-link" onclick="openResultDetail(${item.id})">${escapeHtml(item.title || '-')}</button></td>
            <td>${renderStatusLabel(item.fit_status, RESULT_LABELS.fit_status)}</td>
            <td>${renderStatusLabel(item.follow_decision, RESULT_LABELS.follow_decision)}</td>
            <td>${renderStatusLabel(item.urgency, RESULT_LABELS.urgency)}</td>
            <td>${renderStatusLabel(item.project_stage, RESULT_LABELS.project_stage)}</td>
            <td>${escapeHtml(item.organization || '-')}</td>
            <td>${escapeHtml([item.amount, item.amount_unit].filter(Boolean).join(' ') || '-')}</td>
            <td>${escapeHtml(item.region || '-')}</td>
            <td>${escapeHtml(item.category || '-')}</td>
            <td>${formatResultDate(item.registration_deadline)}</td>
            <td>${formatResultDate(item.submission_deadline)}</td>
            <td>${formatResultDate(item.bid_opening_time)}</td>
            <td>${renderAiStatus(item)}</td>
            <td><a href="${href}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.source || '-')}</a></td>
        </tr>`;
    }).join('');
    selectAll.checked = currentResults.length > 0 && currentResults.every(item => selectedResultIds.has(item.id));
}

async function loadResultSettings() {
    if (resultSettings) return resultSettings;
    const res = await apiFetch('/api/result-settings');
    resultSettings = await res.json();
    populateResultSettingSelect('resultFitStatusFilter', resultSettings.fit_statuses, RESULT_LABELS.fit_status, true);
    populateResultSettingSelect('resultFollowDecisionFilter', resultSettings.follow_decisions, RESULT_LABELS.follow_decision, true);
    populateResultSettingSelect('resultUrgencyFilter', resultSettings.urgencies, RESULT_LABELS.urgency, true);
    populateResultSettingSelect('resultProjectStageFilter', resultSettings.project_stages, RESULT_LABELS.project_stage, true);
    populateResultSettingSelect('bulkFitStatus', resultSettings.fit_statuses, RESULT_LABELS.fit_status, false, '不修改');
    populateResultSettingSelect('bulkFollowDecision', resultSettings.follow_decisions, RESULT_LABELS.follow_decision, false, '不修改');
    populateResultSettingSelect('bulkUrgency', resultSettings.urgencies, RESULT_LABELS.urgency, false, '不修改');
    populateResultSettingSelect('bulkProjectStage', resultSettings.project_stages, RESULT_LABELS.project_stage, false, '不修改');
    renderReasonCheckboxes('bulkNonFollowReasons', []);
    return resultSettings;
}

function populateResultSettingSelect(id, values, labels, allowBlank, blankLabel = '') {
    const select = document.getElementById(id);
    if (!select) return;
    const currentValue = select.value;
    const options = [];
    if (allowBlank || blankLabel) options.push(`<option value="">${escapeHtml(blankLabel || select.options[0]?.textContent || '')}</option>`);
    (values || []).forEach(value => {
        options.push(`<option value="${escapeAttr(value)}">${escapeHtml(renderStatusLabel(value, labels))}</option>`);
    });
    select.innerHTML = options.join('');
    if (currentValue) select.value = currentValue;
}

async function loadResults() {
    try {
        await loadResultSettings();
        const res = await apiFetch('/api/results?' + buildResultQuery().toString());
        const data = await res.json();
        const validIds = new Set((data.items || []).map(item => item.id));
        selectedResultIds = new Set([...selectedResultIds].filter(id => validIds.has(id)));
        if (activeResultId && !validIds.has(activeResultId)) activeResultId = null;
        renderResultsTable(data);
        if (activeResultId) {
            await openResultDetail(activeResultId);
        } else {
            renderEmptyDetailPanel();
        }
    } catch (e) {
        console.error(e);
        document.getElementById('resultsTableBody').innerHTML = '<tr><td colspan="15" class="table-empty">加载失败，请刷新重试</td></tr>';
        renderEmptyDetailPanel('加载详情失败');
    }
}

function renderEmptyDetailPanel(message = '选择一条结果查看详情') {
    const panel = document.getElementById('resultDetailPanel');
    panel.classList.remove('active');
    document.getElementById('detailSourceLabel').textContent = '未选择结果';
    document.getElementById('detailTitle').textContent = '选择一条结果查看详情';
    document.getElementById('detailSourceLink').setAttribute('href', '#');
    document.getElementById('detailEmptyMessage').textContent = message;
    document.getElementById('detailEmptyState').classList.remove('is-hidden');
    document.getElementById('detailGrid').classList.add('is-hidden');
    document.getElementById('detailFieldsSaveButton').disabled = true;
    document.getElementById('detailReviewSaveButton').disabled = true;
}

function detailInputValue(detail, key) {
    const resolved = detail.resolved || {};
    return resolved[key] || detail[key] || '';
}

async function openResultDetail(id) {
    try {
        activeResultId = id;
        document.querySelectorAll('.result-row').forEach(row => row.classList.toggle('is-active', Number(row.dataset.resultId) === id));
        const res = await apiFetch(`/api/results/${id}`);
        const detail = await res.json();
        renderResultDetail(detail);
    } catch (e) {
        console.error(e);
        renderEmptyDetailPanel('结果详情加载失败');
    }
}

function renderResultDetail(detail) {
    const panel = document.getElementById('resultDetailPanel');
    panel.classList.add('active');
    document.getElementById('detailSourceLabel').textContent = detail.source || '-';
    document.getElementById('detailTitle').textContent = detail.title || '-';
    document.getElementById('detailSourceLink').setAttribute('href', safeResultUrl(detail.url));
    document.getElementById('detailEmptyState').classList.add('is-hidden');
    document.getElementById('detailGrid').classList.remove('is-hidden');
    document.getElementById('detailFieldsSaveButton').disabled = false;
    document.getElementById('detailReviewSaveButton').disabled = false;
    document.getElementById('detailFitStatus').innerHTML = buildOptions(resultSettings.fit_statuses, RESULT_LABELS.fit_status, detail.fit_status);
    document.getElementById('detailFollowDecision').innerHTML = buildOptions(resultSettings.follow_decisions, RESULT_LABELS.follow_decision, detail.follow_decision);
    document.getElementById('detailUrgency').innerHTML = buildOptions(resultSettings.urgencies, RESULT_LABELS.urgency, detail.urgency);
    document.getElementById('detailProjectStage').innerHTML = buildOptions(resultSettings.project_stages, RESULT_LABELS.project_stage, detail.project_stage);
    document.getElementById('detailReviewNotes').value = detail.review_notes || '';
    document.getElementById('detailOrganization').value = detailInputValue(detail, 'organization');
    document.getElementById('detailAmount').value = detailInputValue(detail, 'amount');
    document.getElementById('detailAmountUnit').value = detailInputValue(detail, 'amount_unit');
    document.getElementById('detailRegion').value = detailInputValue(detail, 'region');
    document.getElementById('detailCategory').value = detailInputValue(detail, 'category');
    document.getElementById('detailPurchaser').value = detail.purchaser || '';
    document.getElementById('detailRegistrationDeadline').value = detailInputValue(detail, 'registration_deadline');
    document.getElementById('detailSubmissionDeadline').value = detailInputValue(detail, 'submission_deadline');
    document.getElementById('detailBidOpeningTime').value = detailInputValue(detail, 'bid_opening_time');
    document.getElementById('detailStatusLine').textContent = `${detail.ai_extract_status || '-'} / ${detail.detail_fetch_status || '-'}`;
    document.getElementById('detailTextBlock').textContent = detail.detail_text || detail.content || '';
    document.getElementById('detailAiJson').textContent = JSON.stringify(detail.ai_extracted_data || {}, null, 2);
    renderReasonCheckboxes('detailNonFollowReasons', detail.non_follow_reasons || []);
}

function buildOptions(values, labels, selected) {
    return (values || []).map(value => `<option value="${escapeAttr(value)}" ${value === selected ? 'selected' : ''}>${escapeHtml(renderStatusLabel(value, labels))}</option>`).join('');
}

function collectReasonSelections(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return [];
    return Array.from(container.querySelectorAll('input[type="checkbox"]:checked')).map(input => input.value);
}

function renderReasonCheckboxes(containerId, selected) {
    const container = document.getElementById(containerId);
    if (!container || !resultSettings) return;
    container.innerHTML = (resultSettings.non_follow_reason_tags || []).map(tag => {
        const checked = (selected || []).includes(tag) ? 'checked' : '';
        return `<label class="reason-item"><input type="checkbox" value="${escapeAttr(tag)}" ${checked}><span>${escapeHtml(tag)}</span></label>`;
    }).join('');
}

async function saveResultReview(id) {
    const payload = {
        fit_status: document.getElementById('detailFitStatus').value,
        follow_decision: document.getElementById('detailFollowDecision').value,
        urgency: document.getElementById('detailUrgency').value,
        project_stage: document.getElementById('detailProjectStage').value,
        non_follow_reasons: collectReasonSelections('detailNonFollowReasons'),
        review_notes: document.getElementById('detailReviewNotes').value.trim(),
    };
    if (payload.follow_decision === 'not_follow' && payload.non_follow_reasons.length === 0) {
        alert('选择不跟进时必须至少选择一个原因');
        return;
    }
    try {
        const res = await apiFetch(`/api/results/${id}/review`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.detail || data.message || '保存失败');
        await loadResults();
        await openResultDetail(id);
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

async function saveResultFields(id) {
    const payload = {
        organization: document.getElementById('detailOrganization').value.trim(),
        amount: document.getElementById('detailAmount').value.trim(),
        amount_unit: document.getElementById('detailAmountUnit').value.trim(),
        region: document.getElementById('detailRegion').value.trim(),
        category: document.getElementById('detailCategory').value.trim(),
        registration_deadline: document.getElementById('detailRegistrationDeadline').value.trim(),
        submission_deadline: document.getElementById('detailSubmissionDeadline').value.trim(),
        bid_opening_time: document.getElementById('detailBidOpeningTime').value.trim(),
    };
    try {
        const res = await apiFetch(`/api/results/${id}/fields`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.detail || data.message || '保存失败');
        await openResultDetail(id);
        await loadResults();
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

function saveActiveResultFields() {
    if (activeResultId) saveResultFields(activeResultId);
}

function saveActiveResultReview() {
    if (activeResultId) saveResultReview(activeResultId);
}

function toggleResultSelection(id, checked) {
    if (checked) selectedResultIds.add(id);
    else selectedResultIds.delete(id);
    const selectAll = document.getElementById('resultsSelectAll');
    selectAll.checked = currentResults.length > 0 && currentResults.every(item => selectedResultIds.has(item.id));
}

function toggleSelectAllResults(checked) {
    currentResults.forEach(item => {
        if (checked) selectedResultIds.add(item.id);
        else selectedResultIds.delete(item.id);
    });
    renderResultsTable({ items: currentResults });
}

function openBulkReview() {
    if (!selectedResultIds.size) {
        alert('请先选择至少一条结果');
        return;
    }
    document.getElementById('bulkFitStatus').value = '';
    document.getElementById('bulkFollowDecision').value = '';
    document.getElementById('bulkUrgency').value = '';
    document.getElementById('bulkProjectStage').value = '';
    document.getElementById('bulkReviewNotes').value = '';
    renderReasonCheckboxes('bulkNonFollowReasons', []);
    document.getElementById('bulkReviewModal').classList.add('active');
}

async function saveBulkReview() {
    const payload = {
        ids: Array.from(selectedResultIds),
        update: {},
    };
    const fieldMap = {
        fit_status: 'bulkFitStatus',
        follow_decision: 'bulkFollowDecision',
        urgency: 'bulkUrgency',
        project_stage: 'bulkProjectStage',
    };
    Object.entries(fieldMap).forEach(([key, id]) => {
        const value = document.getElementById(id).value;
        if (value) payload.update[key] = value;
    });
    const reasons = collectReasonSelections('bulkNonFollowReasons');
    const notes = document.getElementById('bulkReviewNotes').value.trim();
    if (reasons.length) payload.update.non_follow_reasons = reasons;
    if (notes) payload.update.review_notes = notes;
    if (payload.update.follow_decision === 'not_follow' && !payload.update.non_follow_reasons) {
        alert('批量设置为不跟进时必须至少选择一个原因');
        return;
    }
    if (!Object.keys(payload.update).length) {
        alert('请选择至少一个要更新的字段');
        return;
    }
    try {
        const res = await apiFetch('/api/results/bulk-review', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.detail || data.message || '保存失败');
        closeModal('bulkReviewModal');
        await loadResults();
        if (activeResultId) await openResultDetail(activeResultId);
    } catch (e) {
        alert('保存失败: ' + e.message);
    }
}

async function loadConfig() {
    try {
        const res = await apiFetch('/api/config');
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
        await apiFetch('/api/config', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentConfig) });
        alert('配置已保存！');
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function loadSites() {
    try {
        const res = await apiFetch('/api/sites');
        currentSites = await res.json();
        renderSites();
    } catch (e) {
        console.error(e);
        document.getElementById('sitesList').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

function renderSites() {
    const c = document.getElementById('sitesList');
    const canManageSites = currentUser && currentUser.role === 'admin';
    const disabledAttr = canManageSites ? '' : ' disabled';
    if (currentSites.length > 0) {
        c.innerHTML = currentSites.map((s, i) => {
            const displayName = s.display_name || s.name || s.key || '';
            const url = s.url || '';
            const checkedAt = s.last_checked_at ? escapeHtml(formatSiteDate(s.last_checked_at)) : '未检测';
            const diagnostic = s.last_diagnostic ? `<div class="site-diagnostic">${escapeHtml(s.last_diagnostic)}</div>` : '';
            return `<div class="site-row">
                <div class="site-toggle">
                    <input type="checkbox" id="site_${i}" ${s.enabled ? 'checked' : ''}${disabledAttr} onchange="updateSiteField(${i}, 'enabled', this.checked)">
                    <label for="site_${i}">启用</label>
                </div>
                <div class="site-main">
                    <label class="site-field">
                        <span>显示名称</span>
                        <input type="text" class="config-input" value="${escapeAttr(displayName)}"${disabledAttr} oninput="updateSiteField(${i}, 'display_name', this.value)">
                    </label>
                    <div class="site-url">${escapeHtml(url || s.key || '')}</div>
                    <div class="site-meta">最近检测：${checkedAt}</div>
                    ${diagnostic}
                </div>
                <label class="site-field">
                    <span>访问状态</span>
                    <select class="config-input siteAccessStatus"${disabledAttr} onchange="updateSiteField(${i}, 'access_status', this.value)">
                        ${renderSiteAccessOptions(s.access_status)}
                    </select>
                </label>
                <div class="site-flags">
                    <label class="site-check"><input type="checkbox" ${s.requires_login ? 'checked' : ''}${disabledAttr} onchange="updateSiteField(${i}, 'requires_login', this.checked)"><span>需登录</span></label>
                    <label class="site-check"><input type="checkbox" ${s.has_antibot ? 'checked' : ''}${disabledAttr} onchange="updateSiteField(${i}, 'has_antibot', this.checked)"><span>反爬/验证码</span></label>
                </div>
                <label class="site-field site-note-field">
                    <span>备注</span>
                    <textarea class="config-input site-note" rows="2"${disabledAttr} oninput="updateSiteField(${i}, 'note', this.value)">${escapeHtml(s.note || '')}</textarea>
                </label>
            </div>`;
        }).join('');
    } else {
        c.innerHTML = '<div class="empty-state">暂无网站配置</div>';
    }
}

function renderSiteAccessOptions(value) {
    const selectedValue = value || 'unknown';
    return ACCESS_STATUS_OPTIONS.map(option => `<option value="${option.value}" ${option.value === selectedValue ? 'selected' : ''}>${option.label}</option>`).join('');
}

function updateSiteField(index, field, value) {
    if (!currentSites[index]) return;
    currentSites[index][field] = value;
}

function formatSiteDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('zh-CN', { hour12: false });
}

function selectAllSites() { currentSites.forEach(s => s.enabled = true); renderSites(); }
function deselectAllSites() { currentSites.forEach(s => s.enabled = false); renderSites(); }

async function saveSites() {
    try {
        await apiFetch('/api/sites', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sites: currentSites.map(s => ({
                key: s.key,
                enabled: !!s.enabled,
                display_name: s.display_name || '',
                access_status: s.access_status || 'unknown',
                requires_login: !!s.requires_login,
                has_antibot: !!s.has_antibot,
                note: s.note || '',
                last_checked_at: s.last_checked_at || null,
                last_diagnostic: s.last_diagnostic || '',
            })) }),
        });
        alert('网站配置已保存！');
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function loadUsers() {
    if (!(currentUser && currentUser.role === 'admin')) return;
    try {
        const res = await apiFetch('/api/users');
        const data = await res.json();
        currentUsers = data.users || [];
        renderUsers();
    } catch (e) {
        console.error(e);
        document.getElementById('usersList').innerHTML = '<div class="empty-state">加载失败</div>';
    }
}

function renderUsers() {
    const c = document.getElementById('usersList');
    if (currentUsers.length > 0) {
        c.innerHTML = currentUsers.map((u, i) => {
            const enabled = u.is_active !== false;
            const badgeClass = enabled ? 'status-badge status-badge-on' : 'status-badge status-badge-off';
            const badgeText = enabled ? '启用' : '停用';
            return `<div class="list-item"><div class="list-item-content"><div class="list-item-title"><span>${escapeHtml(u.username)}</span><span class="${badgeClass}">${badgeText}</span></div><div class="list-item-subtitle">${u.role === 'admin' ? '管理员' : '普通用户'}</div></div><div class="list-item-actions"><button class="btn btn-sm btn-outline" onclick="editUser(${i})">编辑</button><button class="btn btn-sm btn-outline" onclick="toggleUser(${i})">${enabled ? '停用' : '启用'}</button></div></div>`;
        }).join('');
    } else {
        c.innerHTML = `<div class="empty-state"><div class="empty-state-icon">${icon('users', 'icon icon-lg')}</div><div>暂无用户</div></div>`;
    }
}

function showAddUser() {
    editingUserId = null;
    document.getElementById('userModalTitle').textContent = '添加用户';
    document.getElementById('userUsername').disabled = false;
    document.getElementById('userUsername').value = '';
    document.getElementById('userPassword').value = '';
    document.getElementById('userRole').value = 'user';
    document.getElementById('userActive').checked = true;
    document.getElementById('userModal').classList.add('active');
}

function editUser(i) {
    const user = currentUsers[i];
    editingUserId = user.id;
    document.getElementById('userModalTitle').textContent = '编辑用户';
    document.getElementById('userUsername').disabled = true;
    document.getElementById('userUsername').value = user.username || '';
    document.getElementById('userPassword').value = '';
    document.getElementById('userRole').value = user.role || 'user';
    document.getElementById('userActive').checked = user.is_active !== false;
    document.getElementById('userModal').classList.add('active');
}

async function saveUser() {
    const username = document.getElementById('userUsername').value.trim();
    const password = document.getElementById('userPassword').value;
    const role = document.getElementById('userRole').value;
    const is_active = document.getElementById('userActive').checked;
    if (!editingUserId && (!username || !password)) { alert('请填写账号和密码'); return; }
    const payload = editingUserId ? { role, is_active } : { username, password, role };
    if (editingUserId && password) payload.password = password;
    try {
        const path = editingUserId ? `/api/users/${editingUserId}` : '/api/users';
        const method = editingUserId ? 'PATCH' : 'POST';
        const res = await apiFetch(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.detail || data.message || '保存失败');
        closeModal('userModal');
        loadUsers();
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function toggleUser(i) {
    const user = currentUsers[i];
    try {
        await apiFetch(`/api/users/${user.id}`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ is_active: user.is_active === false })
        });
        loadUsers();
    } catch (e) { alert('操作失败: ' + e.message); }
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
        const res = await apiFetch('/api/test/sms', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) });
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
        const res = await apiFetch('/api/test/voice', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ phone }) });
        const data = await res.json();
        alert(data.message);
    } catch (e) { alert('测试失败: ' + e.message); }
}

function showAiConfig() {
    document.getElementById('aiEnabled').checked = currentConfig.ai_enabled || false;
    const ac = currentConfig.ai_config || {};
    document.getElementById('aiUrl').value = ac.base_url || ac.url || 'https://api.deepseek.com/chat/completions';
    document.getElementById('aiEndpointType').value = ac.endpoint_type || 'responses';
    document.getElementById('aiKey').value = '';
    document.getElementById('aiModel').value = ac.model || 'deepseek-chat';
    document.getElementById('aiModal').classList.add('active');
}

async function saveAiConfig() {
    currentConfig.ai_enabled = document.getElementById('aiEnabled').checked;
    const newKey = document.getElementById('aiKey').value;
    currentConfig.ai_config = {
        enable: document.getElementById('aiEnabled').checked,
        base_url: document.getElementById('aiUrl').value,
        endpoint_type: document.getElementById('aiEndpointType').value || 'responses',
        api_key: newKey || (currentConfig.ai_config ? currentConfig.ai_config.api_key : ''),
        model: document.getElementById('aiModel').value
    };
    await saveFullConfig();
    closeModal('aiModal');
}

async function testAi() {
    await saveAiConfig();
    try {
        const res = await apiFetch('/api/test/ai', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) });
        const data = await res.json();
        alert(data.message);
    } catch (e) { alert('测试失败: ' + e.message); }
}

async function saveFullConfig() {
    try {
        await apiFetch('/api/config/full', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(currentConfig) });
        alert('配置已保存！');
    } catch (e) { alert('保存失败: ' + e.message); }
}

async function startMonitor() {
    try {
        const res = await apiFetch('/api/start', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
        refreshStatus();
        loadLogs();
    } catch (e) { alert('操作失败: ' + e.message); }
}

async function stopMonitor() {
    try {
        const res = await apiFetch('/api/stop', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
        refreshStatus();
    } catch (e) { alert('操作失败: ' + e.message); }
}

async function runOnce() {
    try {
        const res = await apiFetch('/api/run-once', { method: 'POST' });
        const data = await res.json();
        alert(data.message);
        refreshStatus();
        setTimeout(loadLogs, 1000);
    } catch (e) { alert('操作失败: ' + e.message); }
}

async function clearLogs() {
    if (!confirm('确定要清除所有日志吗？')) return;
    try {
        await apiFetch('/api/logs', { method: 'DELETE' });
        document.getElementById('logsContainer').innerHTML = '<div class="log-line">日志已清除</div>';
    } catch (e) { alert('清除失败: ' + e.message); }
}

async function clearHistory() {
    if (!confirm('确定要清空所有历史数据吗？')) return;
    try {
        const res = await apiFetch('/api/history', { method: 'DELETE' });
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

function escapeAttr(t) {
    return escapeHtml(t).replace(/"/g, '&quot;');
}

syncNavTabs();
checkAuth();
