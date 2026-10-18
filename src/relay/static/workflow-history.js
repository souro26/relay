/**
 * Workflow History Page - Frontend Controller
 * Handles metrics loading, pagination, filtering, and exports.
 */

(function() {
    'use strict';

    const historyState = {
        workflows: [],
        total: 0,
        pages: 1,
        page: 1,
        pageSize: 25,
        status: 'all',
        search: ''
    };

    function formatNumber(num) {
        if (num == null || isNaN(num)) return '—';
        return new Intl.NumberFormat('en-US').format(num);
    }

    function formatDate(dateStr) {
        if (!dateStr) return '—';
        try {
            const d = new Date(dateStr);
            if (isNaN(d.getTime())) return dateStr;
            return d.toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });
        } catch {
            return dateStr;
        }
    }

    function escapeHtml(str) {
        if (str == null) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    function downloadBlob(content, filename, type) {
        const blob = new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }

    async function loadHistoryMetrics() {
        try {
            const res = await fetch('/api/v1/metrics');
            if (!res.ok) return;
            const data = await res.json();

            const total = data.total_workflows || 0;
            const completed = data.completed_workflows || 0;
            const running = data.running_workflows || 0;
            const uncertain = data.uncertain_workflows || 0;
            const failed = data.failed_workflows || 0;

            const elTot = document.getElementById('history-total-traces');
            const elComp = document.getElementById('history-completed-cnt');
            const elRun = document.getElementById('history-running-cnt');
            const elUnc = document.getElementById('history-uncertain-cnt');
            const elFail = document.getElementById('history-failed-cnt');

            if (elTot) elTot.textContent = formatNumber(total);
            if (elComp) elComp.textContent = formatNumber(completed);
            if (elRun) elRun.textContent = formatNumber(running);
            if (elUnc) elUnc.textContent = formatNumber(uncertain);
            if (elFail) elFail.textContent = formatNumber(failed);

            // Pill counts
            const pAll = document.getElementById('pill-cnt-all');
            const pComp = document.getElementById('pill-cnt-completed');
            const pRun = document.getElementById('pill-cnt-running');
            const pUnc = document.getElementById('pill-cnt-uncertain');
            const pFail = document.getElementById('pill-cnt-failed');

            if (pAll) pAll.textContent = formatNumber(total);
            if (pComp) pComp.textContent = formatNumber(completed);
            if (pRun) pRun.textContent = formatNumber(running);
            if (pUnc) pUnc.textContent = formatNumber(uncertain);
            if (pFail) pFail.textContent = formatNumber(failed);

        } catch (e) {
            console.error('Failed to load history metrics:', e);
        }
    }

    async function loadHistoryTable() {
        try {
            historyState.page = Math.max(1, historyState.page);
            let url = `/api/v1/workflows?page=${historyState.page}&page_size=${historyState.pageSize}`;
            if (historyState.status && historyState.status !== 'all') {
                url += `&status=${encodeURIComponent(historyState.status)}`;
            }

            const res = await fetch(url);
            if (!res.ok) throw new Error('Failed to fetch');
            const data = await res.json();

            historyState.workflows = data.items || [];
            historyState.total = data.total || 0;
            historyState.pages = data.total_pages || 1;

            renderHistoryTable();
        } catch (e) {
            console.error('Failed to load history table:', e);
            const tbody = document.getElementById('workflow-list-body');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 24px; color: var(--color-error);">
                            Failed to load workflow history: ${escapeHtml(e.message)}
                        </td>
                    </tr>
                `;
            }
        }
    }

    function renderHistoryTable() {
        const tbody = document.getElementById('workflow-list-body');
        const countEl = document.getElementById('history-entry-count');
        const paginationEl = document.getElementById('history-pagination');
        if (!tbody) return;

        let filtered = historyState.workflows;
        if (historyState.search) {
            const q = historyState.search;
            filtered = filtered.filter(w => {
                const idMatch = (w.id || '').toLowerCase().includes(q);
                const typeMatch = (w.workflow_type || '').toLowerCase().includes(q);
                const orderMatch = (w.order_id || '').toLowerCase().includes(q);
                const eventMatch = (w.external_event_id || '').toLowerCase().includes(q);
                return idMatch || typeMatch || orderMatch || eventMatch;
            });
        }

        if (countEl) {
            countEl.textContent = `Showing ${filtered.length} of ${formatNumber(historyState.total || filtered.length)} entries`;
        }

        if (filtered.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 32px; color: var(--color-text-muted);">
                        No workflow records match the active criteria.
                    </td>
                </tr>
            `;
        } else {
            tbody.innerHTML = filtered.map(w => {
                const uuidShort = (w.id || '').substring(0, 10);
                const statusLower = (w.status || 'pending').toLowerCase();
                const badgeClass = statusLower === 'completed' ? 'badge-completed' : (statusLower === 'failed' ? 'badge-failed' : (statusLower === 'running' ? 'badge-running' : 'badge-uncertain'));
                const duration = w.duration_ms != null ? `${Math.round(w.duration_ms)}ms` : '—';
                const timeFormatted = formatDate(w.created_at);

                return `
                    <tr>
                        <td><code class="table-uuid">${escapeHtml(uuidShort)}</code></td>
                        <td>
                            <span style="font-family: var(--font-mono); font-size: 11.5px;">${escapeHtml(w.order_id || '—')}</span>
                            ${w.customer_id ? `<span class="table-sub-uuid">${escapeHtml(w.customer_id)}</span>` : ''}
                        </td>
                        <td><span style="font-weight: 500;">${escapeHtml(w.workflow_type || 'order_change')}</span></td>
                        <td><span class="badge ${badgeClass}">${escapeHtml((w.status || 'PENDING').toUpperCase())}</span></td>
                        <td><code style="font-family: var(--font-mono); font-size: 11.5px;">${duration}</code></td>
                        <td style="color: var(--color-text-secondary); font-size: 11.5px;">${timeFormatted}</td>
                        <td style="text-align: right;">
                            <a href="/workflows/${w.id}" class="btn btn-secondary btn-sm" style="font-size: 11px;">Inspect</a>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // Pagination - using event delegation
        if (paginationEl) {
            if (historyState.pages <= 1) {
                paginationEl.innerHTML = '';
            } else {
                let pagHtml = '';
                for (let i = 1; i <= historyState.pages; i++) {
                    pagHtml += `<button type="button" class="btn btn-sm ${i === historyState.page ? 'btn-primary' : 'btn-secondary'}" data-page="${i}">${i}</button>`;
                }
                paginationEl.innerHTML = pagHtml;
            }
        }
    }

    function setPage(p) {
        historyState.page = p;
        loadHistoryTable();
    }

    // Auto-initialize
    document.addEventListener('DOMContentLoaded', () => {
        loadHistoryMetrics();
        loadHistoryTable();

        // Status pill filters
        const pills = document.querySelectorAll('.history-pill');
        pills.forEach(p => {
            p.addEventListener('click', () => {
                pills.forEach(b => {
                    b.style.background = '#F5EFEB';
                    b.style.color = '#573D2F';
                    b.style.border = '1px solid #E8DFD5';
                });
                p.style.background = '#121D33';
                p.style.color = '#FFFFFF';
                p.style.border = 'none';
                historyState.status = p.dataset.status;
                historyState.page = 1;
                loadHistoryTable();
            });
        });

        // Search debouncing
        let searchTimeout = null;
        const searchInput = document.getElementById('history-search-input');
        if (searchInput) {
            searchInput.addEventListener('input', (e) => {
                clearTimeout(searchTimeout);
                searchTimeout = setTimeout(() => {
                    historyState.search = e.target.value.trim();
                    historyState.page = 1;
                    loadHistoryTable();
                }, 300);
            });
        }

        // Page size
        const pageSizeSelect = document.getElementById('history-page-size');
        if (pageSizeSelect) {
            pageSizeSelect.addEventListener('change', (e) => {
                historyState.pageSize = parseInt(e.target.value, 10);
                historyState.page = 1;
                loadHistoryTable();
            });
        }

        // CSV Export
        const btnExportCsv = document.getElementById('btn-export-csv');
        if (btnExportCsv) {
            btnExportCsv.addEventListener('click', () => {
                if (historyState.workflows.length === 0) return alert('No records to export');
                const headers = ['id', 'workflow_type', 'status', 'created_at', 'duration_ms', 'order_id', 'customer_id'];
                const rows = historyState.workflows.map(w => [
                    `"${w.id}"`,
                    `"${w.workflow_type || ''}"`,
                    `"${w.status || ''}"`,
                    `"${w.created_at || ''}"`,
                    w.duration_ms != null ? w.duration_ms : '',
                    `"${w.order_id || ''}"`,
                    `"${w.customer_id || ''}"`
                ].join(','));
                const csv = [headers.join(','), ...rows].join('\n');
                downloadBlob(csv, `relay-workflows-${Date.now()}.csv`, 'text/csv');
            });
        }

        // JSON Export
        const btnExportJson = document.getElementById('btn-export-json');
        if (btnExportJson) {
            btnExportJson.addEventListener('click', () => {
                if (historyState.workflows.length === 0) return alert('No records to export');
                downloadBlob(JSON.stringify(historyState.workflows, null, 2), `relay-workflows-${Date.now()}.json`, 'application/json');
            });
        }

        // Event delegation for pagination
        const paginationEl = document.getElementById('history-pagination');
        if (paginationEl) {
            paginationEl.addEventListener('click', (e) => {
                const btn = e.target.closest('[data-page]');
                if (btn) {
                    setPage(parseInt(btn.dataset.page, 10));
                }
            });
        }
    });
})();