/**
 * TAT & Batch Monitoring System — Frontend JavaScript
 * Handles API calls, DOM updates, and user interactions.
 */

const API = '';  // Same origin

// ========== State ==========
let selectedTest = null;
let searchTimeout = null;
let allTests = [];

// ========== Init ==========
document.addEventListener('DOMContentLoaded', () => {
    loadStats();
    loadTests('');
    loadSamples();
    loadNotifications();
    // Auto-refresh every 30s
    setInterval(() => {
        loadStats();
        loadSamples();
        loadNotifications();
    }, 30000);
});

// ========== API Helpers ==========
async function apiFetch(url, options = {}) {
    try {
        const resp = await fetch(API + url, {
            headers: { 'Content-Type': 'application/json' },
            ...options,
        });
        const data = await resp.json();
        if (!resp.ok) {
            throw new Error(data.detail || 'API Error');
        }
        return data;
    } catch (err) {
        console.error('API Error:', err);
        throw err;
    }
}

// ========== Stats ==========
async function loadStats() {
    try {
        const stats = await apiFetch('/api/stats');
        document.getElementById('statCatalog').textContent = stats.total_tests_in_catalog;
        document.getElementById('statActive').textContent = stats.active_samples;
        document.getElementById('statMissed').textContent = stats.missed_batches;
        document.getElementById('statTotal').textContent = stats.total_samples;

        const countEl = document.getElementById('notifCount');
        if (stats.unread_notifications > 0) {
            countEl.textContent = stats.unread_notifications;
            countEl.style.display = 'inline';
        } else {
            countEl.style.display = 'none';
        }
    } catch (e) {
        console.error('Failed to load stats:', e);
    }
}

// ========== Test Search ==========
function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        const q = document.getElementById('searchInput').value.trim();
        loadTests(q);
    }, 300);
}

async function loadTests(query) {
    const listEl = document.getElementById('testList');

    try {
        const url = query
            ? `/api/tests?q=${encodeURIComponent(query)}&limit=50`
            : `/api/tests?limit=50`;
        const data = await apiFetch(url);
        allTests = data.tests;

        if (data.tests.length === 0) {
            listEl.innerHTML = `
                <div class="empty-state">
                    <div class="empty-icon">🔍</div>
                    <p>No tests found${query ? ` for "${query}"` : ''}</p>
                </div>`;
            return;
        }

        listEl.innerHTML = data.tests.map(t => `
            <div class="test-item" onclick="selectTest('${t.test_code}')">
                <div class="test-info">
                    <div class="test-code">${escHtml(t.test_code)}</div>
                    <div class="test-name">${escHtml(t.test_name)}</div>
                </div>
                <span class="test-schedule-badge">${escHtml(t.test_schedule || 'N/A')}</span>
            </div>
        `).join('');
    } catch (e) {
        listEl.innerHTML = `<div class="empty-state"><p>Error loading tests</p></div>`;
    }
}

async function selectTest(code) {
    try {
        const data = await apiFetch(`/api/tests/${code}`);
        selectedTest = data.test;

        const area = document.getElementById('selectedTestArea');
        const info = document.getElementById('selectedTestInfo');
        area.style.display = 'block';

        info.innerHTML = `
            <div class="st-code">${escHtml(data.test.test_code)}</div>
            <div class="st-name">${escHtml(data.test.test_name)}</div>
            <div class="st-meta">
                <span>📅 <strong>${escHtml(data.test.test_schedule)}</strong></span>
                <span>⏱ TAT: <strong>${escHtml(data.test.tat)}</strong></span>
                <span>💰 ₹${data.test.mrp.toLocaleString()}</span>
                <span>🧫 ${escHtml(data.test.method)}</span>
            </div>
        `;

        // Show ETA preview
        if (data.next_batch_from_now && data.eta_from_now) {
            const etaEl = document.getElementById('etaPreview');
            etaEl.style.display = 'block';
            etaEl.innerHTML = `
                <div class="eta-label">If Accessioned Now</div>
                <div class="eta-value">${formatDT(data.eta_from_now)}</div>
                <div class="eta-batch">Next batch: ${formatDT(data.next_batch_from_now)}</div>
            `;
        }
    } catch (e) {
        showToast('Error', 'Failed to load test details', 'error');
    }
}

// ========== Accession ==========
async function accessionSample() {
    if (!selectedTest) {
        showToast('Select a Test', 'Please search and select a test first', 'error');
        return;
    }

    const btn = document.getElementById('accessionBtn');
    btn.disabled = true;
    btn.textContent = '⏳ Processing...';

    const timeInput = document.getElementById('accessionTimeInput').value;
    const body = {
        test_code: selectedTest.test_code,
    };
    if (timeInput) {
        body.accession_time = new Date(timeInput).toISOString();
    }

    try {
        const data = await apiFetch('/api/accession', {
            method: 'POST',
            body: JSON.stringify(body),
        });

        showToast('✅ Sample Accessioned',
            `${data.sample.sample_id} — ETA: ${formatDT(data.sample.eta)}`,
            'success');

        // Refresh
        loadSamples();
        loadStats();

        // Clear selection
        document.getElementById('accessionTimeInput').value = '';
    } catch (e) {
        showToast('Error', e.message, 'error');
    } finally {
        btn.disabled = false;
        btn.textContent = '🧪 Accession Sample';
    }
}

// ========== Samples ==========
async function loadSamples() {
    try {
        const data = await apiFetch('/api/samples?limit=50');
        const tbody = document.getElementById('samplesBody');

        if (data.samples.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7">
                <div class="empty-state"><div class="empty-icon">📭</div>
                <p>No samples yet. Accession a test to get started.</p></div>
            </td></tr>`;
            return;
        }

        tbody.innerHTML = data.samples.map(s => `
            <tr>
                <td><strong style="color:var(--accent-secondary)">${escHtml(s.sample_id)}</strong></td>
                <td>
                    <div style="font-size:0.7rem;color:var(--text-muted)">${escHtml(s.test_code)}</div>
                    <div style="font-size:0.8rem;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${escHtml(s.test_name)}</div>
                </td>
                <td style="font-size:0.78rem">${formatDT(s.accession_time)}</td>
                <td style="font-size:0.78rem">${formatDT(s.assigned_batch)}</td>
                <td style="font-size:0.78rem;font-weight:600;color:var(--success)">${formatDT(s.eta)}</td>
                <td><span class="status-badge ${s.status}">${statusIcon(s.status)} ${s.status.replace('_',' ')}</span></td>
                <td>
                    <div style="display:flex;gap:4px;flex-wrap:wrap">
                        <button class="btn btn-sm btn-warning" onclick="missBatch('${s.sample_id}')" 
                                title="Simulate missed batch">⚠️ Miss</button>
                        <button class="btn btn-sm btn-outline" onclick="deleteSample('${s.sample_id}')"
                                title="Delete sample">🗑</button>
                    </div>
                </td>
            </tr>
        `).join('');
    } catch (e) {
        console.error('Failed to load samples:', e);
    }
}

async function missBatch(sampleId) {
    try {
        const data = await apiFetch(`/api/samples/${sampleId}/miss-batch`, {
            method: 'POST',
        });

        showToast('⚠️ Batch Missed', data.message, 'warning');
        loadSamples();
        loadStats();
        loadNotifications();
    } catch (e) {
        showToast('Error', e.message, 'error');
    }
}

async function deleteSample(sampleId) {
    try {
        await apiFetch(`/api/samples/${sampleId}`, { method: 'DELETE' });
        showToast('Deleted', `Sample ${sampleId} removed`, 'success');
        loadSamples();
        loadStats();
    } catch (e) {
        showToast('Error', e.message, 'error');
    }
}

// ========== Notifications ==========
async function loadNotifications() {
    try {
        const data = await apiFetch('/api/notifications?limit=30');
        const listEl = document.getElementById('notifList');
        const countEl = document.getElementById('notifHeaderCount');
        countEl.textContent = `${data.unread_count} unread`;

        if (data.notifications.length === 0) {
            listEl.innerHTML = `<div class="empty-state"><div class="empty-icon">🔕</div><p>No notifications yet</p></div>`;
            return;
        }

        listEl.innerHTML = data.notifications.map(n => `
            <div class="notif-item ${n.read ? '' : 'unread'}" onclick="markRead('${n.notification_id}', this)">
                <div class="notif-time">${formatDT(n.created_at)}</div>
                <div class="notif-message">${escHtml(n.message)}</div>
            </div>
        `).join('');
    } catch (e) {
        console.error('Failed to load notifications:', e);
    }
}

async function markRead(notifId, el) {
    try {
        await apiFetch(`/api/notifications/${notifId}/read`, { method: 'POST' });
        el.classList.remove('unread');
        loadStats();
        loadNotifications();
    } catch (e) {
        console.error('Failed to mark notification:', e);
    }
}

function toggleNotifications() {
    const rightCol = document.querySelector('.right-col');
    if (rightCol) {
        rightCol.scrollIntoView({ behavior: 'smooth' });
    }
}

// ========== Utilities ==========
function formatDT(isoStr) {
    if (!isoStr) return 'N/A';
    try {
        const dt = new Date(isoStr);
        const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
        const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
        const day = days[dt.getDay()];
        const month = months[dt.getMonth()];
        const date = dt.getDate();
        let hours = dt.getHours();
        const mins = dt.getMinutes().toString().padStart(2, '0');
        const ampm = hours >= 12 ? 'PM' : 'AM';
        hours = hours % 12 || 12;
        return `${day}, ${month} ${date} ${hours}:${mins} ${ampm}`;
    } catch {
        return isoStr;
    }
}

function escHtml(str) {
    if (!str) return '';
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
}

function statusIcon(status) {
    const icons = {
        batch_assigned: '📋',
        processing: '⚙️',
        completed: '✅',
        missed_batch: '⚠️',
        accessioned: '🧪',
    };
    return icons[status] || '❓';
}

function refreshAll() {
    loadStats();
    loadTests(document.getElementById('searchInput').value.trim());
    loadSamples();
    loadNotifications();
    showToast('Refreshed', 'All data refreshed', 'success');
}

// ========== Toast ==========
function showToast(title, message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `
        <div class="toast-title">${escHtml(title)}</div>
        <div class="toast-message">${escHtml(message)}</div>
    `;
    container.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease forwards';
        setTimeout(() => toast.remove(), 300);
    }, 5000);
}

// ========== Modal ==========
function closeModal() {
    document.getElementById('notifModal').classList.remove('active');
}
