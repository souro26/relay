/**
 * Relay - Business Workflow Integration
 * Frontend Controller for Truthful Observability & Telemetry
 */

(function() {
    'use strict';

    let statusChartInstance = null;

    const state = {
        theme: 'light',
        workflows: [],
        metrics: null,
        activeWorkflow: null,
        historyFilter: {
            status: 'all',
            search: '',
            page: 1,
            pageSize: 25
        }
    };

    // ==============================================================================
    // Theme Management
    // ==============================================================================
    const themeManager = {
        STORAGE_KEY: 'relay-theme-preference',

        init() {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            const preferred = stored || (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
            this.applyTheme(preferred);

            const toggleBtn = document.getElementById('theme-toggle-btn');
            if (toggleBtn) {
                toggleBtn.addEventListener('click', () => this.toggle());
            }
        },

        applyTheme(mode) {
            state.theme = mode;
            document.documentElement.setAttribute('data-theme', mode);
            localStorage.setItem(this.STORAGE_KEY, mode);
            this.updateToggleIcon(mode);
            if (statusChartInstance) {
                statusChartInstance.update();
            }
        },

        toggle() {
            const next = state.theme === 'dark' ? 'light' : 'dark';
            this.applyTheme(next);
        },

        updateToggleIcon(mode) {
            const btn = document.getElementById('theme-toggle-btn');
            if (!btn) return;
            const icon = btn.querySelector('.theme-icon');
            if (!icon) return;

            if (mode === 'dark') {
                btn.title = 'Switch to light mode';
                icon.innerHTML = `
                    <circle cx="12" cy="12" r="5"/>
                    <line x1="12" y1="1" x2="12" y2="3"/>
                    <line x1="12" y1="21" x2="12" y2="23"/>
                    <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
                    <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
                    <line x1="1" y1="12" x2="3" y2="12"/>
                    <line x1="21" y1="12" x2="23" y2="12"/>
                    <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
                    <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
                `;
            } else {
                btn.title = 'Switch to dark mode';
                icon.innerHTML = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>`;
            }
        }
    };

    // ==============================================================================
    // Utilities
    // ==============================================================================
    const utils = {
        escapeHtml(str) {
            if (str == null) return '';
            const div = document.createElement('div');
            div.textContent = String(str);
            return div.innerHTML;
        },

        formatNumber(num) {
            if (num == null || isNaN(num)) return '—';
            return new Intl.NumberFormat('en-US').format(num);
        },

        formatDate(dateStr) {
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
        },

        showToast(message, type = 'info') {
            const existing = document.getElementById('relay-toast');
            if (existing) existing.remove();

            const toast = document.createElement('div');
            toast.id = 'relay-toast';
            toast.style.cssText = `
                position: fixed;
                bottom: 24px;
                right: 24px;
                background: ${type === 'error' ? '#DC2626' : (type === 'success' ? '#059669' : '#0F172A')};
                color: #FFFFFF;
                padding: 10px 16px;
                border-radius: 6px;
                font-size: 12.5px;
                font-weight: 500;
                box-shadow: 0 10px 15px -3px rgba(0,0,0,0.2);
                z-index: 9999;
                display: flex;
                align-items: center;
                gap: 8px;
            `;
            toast.textContent = message;
            document.body.appendChild(toast);
            setTimeout(() => toast.remove(), 3200);
        },

        copyToClipboard(text, label = 'Copied to clipboard') {
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(() => {
                    utils.showToast(label, 'success');
                }).catch(() => {
                    utils.fallbackCopy(text, label);
                });
            } else {
                utils.fallbackCopy(text, label);
            }
        },

        fallbackCopy(text, label) {
            const ta = document.createElement('textarea');
            ta.value = text;
            ta.style.position = 'fixed';
            ta.style.opacity = '0';
            document.body.appendChild(ta);
            ta.select();
            document.execCommand('copy');
            ta.remove();
            utils.showToast(label, 'success');
        },

        downloadFile(content, filename, type = 'text/plain') {
            const blob = new Blob([content], { type });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            a.remove();
            URL.revokeObjectURL(url);
            utils.showToast(`Exported ${filename}`, 'success');
        }
    };

    // ==============================================================================
    // API Client
    // ==============================================================================
    const api = {
        async getMetrics() {
            const res = await fetch('/api/v1/metrics');
            if (!res.ok) throw new Error('Failed to fetch metrics');
            return res.json();
        },

        async getWorkflows(page = 1, pageSize = 25, status = null) {
            let url = `/api/v1/workflows?page=${page}&page_size=${pageSize}`;
            if (status && status !== 'all') {
                url += `&status=${encodeURIComponent(status)}`;
            }
            const res = await fetch(url);
            if (!res.ok) throw new Error('Failed to fetch workflows');
            return res.json();
        },

        async getWorkflow(id) {
            const res = await fetch(`/api/v1/workflows/${id}`);
            if (res.status === 404) {
                const err = new Error('Workflow not found');
                err.status = 404;
                throw err;
            }
            if (!res.ok) throw new Error('Failed to fetch workflow');
            return res.json();
        },

        async submitNLRequest(payload) {
            const res = await fetch('/api/v1/order-change-requests/nl', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) {
                const msg = data.detail?.error || (typeof data.detail === 'string' ? data.detail : 'Request failed');
                const err = new Error(msg);
                err.response = data;
                throw err;
            }
            return data;
        },

        async checkReadiness() {
            const t0 = performance.now();
            try {
                const res = await fetch('/ready');
                const t1 = performance.now();
                return { ok: res.ok, latencyMs: Math.round(t1 - t0) };
            } catch {
                return { ok: false, latencyMs: null };
            }
        }
    };

    // ==============================================================================
    // Dashboard (Overview)
    // ==============================================================================
    async function initDashboard() {
        const totalEl = document.getElementById('metric-total-workflows');
        const successRateEl = document.getElementById('metric-success-rate');
        const medianEl = document.getElementById('metric-median-latency');
        const p95El = document.getElementById('metric-p95-latency');
        const failedEl = document.getElementById('metric-failed-workflows');
        const runningEl = document.getElementById('metric-running-workflows');
        const tokensEl = document.getElementById('metric-total-tokens');
        const costEl = document.getElementById('metric-total-cost');
        const diagLlmLat = document.getElementById('diag-llm-latency');
        const diagLlmCalls = document.getElementById('diag-llm-calls');
        const diagFailList = document.getElementById('diag-step-failures-list');
        const runsTbody = document.getElementById('dashboard-recent-workflows');

        try {
            const metrics = await api.getMetrics();
            state.metrics = metrics;

            if (totalEl) totalEl.textContent = utils.formatNumber(metrics.total_workflows || 0);
            if (successRateEl) successRateEl.textContent = metrics.success_rate_percentage || '—';
            if (medianEl) medianEl.textContent = metrics.median_duration_ms != null ? `${metrics.median_duration_ms}ms` : '—';
            if (p95El) p95El.textContent = metrics.p95_duration_ms != null ? `${metrics.p95_duration_ms}ms` : '—';
            if (failedEl) failedEl.textContent = String(metrics.failed_workflows || 0);
            if (runningEl) runningEl.textContent = String(metrics.running_workflows || 0);
            if (tokensEl) tokensEl.textContent = metrics.total_tokens ? utils.formatNumber(metrics.total_tokens) : '—';
            if (costEl) costEl.textContent = metrics.total_estimated_cost_usd != null ? `$${metrics.total_estimated_cost_usd.toFixed(4)}` : '—';

            // Diagnostics Card
            if (diagLlmLat) diagLlmLat.textContent = metrics.avg_llm_latency_ms != null ? `${metrics.avg_llm_latency_ms}ms` : '—';
            if (diagLlmCalls) diagLlmCalls.textContent = String(metrics.total_llm_invocations || 0);
            if (diagFailList) {
                const failCounts = metrics.step_failure_counts || {};
                const keys = Object.keys(failCounts);
                if (keys.length === 0) {
                    diagFailList.textContent = '0 step failures recorded across workflow executions.';
                } else {
                    diagFailList.innerHTML = keys.map(k => `
                        <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                            <span><code>${utils.escapeHtml(k)}</code></span>
                            <span class="badge badge-failed">${failCounts[k]} failures</span>
                        </div>
                    `).join('');
                }
            }

            // Status Distribution Donut Chart
            renderStatusDonut(metrics);

            // Recent Runs Table
            renderDashboardRuns(metrics.recent_workflows || []);

            // Search filter
            const searchInput = document.getElementById('dashboard-search-input');
            const statusFilter = document.getElementById('dashboard-status-filter');
            const filterRuns = () => {
                const query = (searchInput ? searchInput.value : '').toLowerCase().trim();
                const status = statusFilter ? statusFilter.value : 'all';
                const filtered = (metrics.recent_workflows || []).filter(w => {
                    const matchQ = !query || (w.id || '').toLowerCase().includes(query) || (w.workflow_type || '').toLowerCase().includes(query);
                    const matchS = status === 'all' || (w.status || '').toLowerCase() === status;
                    return matchQ && matchS;
                });
                renderDashboardRuns(filtered);
            };

            if (searchInput) searchInput.addEventListener('input', filterRuns);
            if (statusFilter) statusFilter.addEventListener('change', filterRuns);

        } catch (error) {
            if (runsTbody) {
                runsTbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 24px; color: var(--color-error);">
                            Failed to load operational metrics: ${utils.escapeHtml(error.message)}
                        </td>
                    </tr>
                `;
            }
        }
    }

    function renderStatusDonut(metrics) {
        const canvas = document.getElementById('statusChart');
        if (!canvas) return;

        const completed = metrics.completed_workflows || 0;
        const running = metrics.running_workflows || 0;
        const uncertain = metrics.uncertain_workflows || 0;
        const failed = metrics.failed_workflows || 0;
        const total = completed + running + uncertain + failed;

        const elComp = document.getElementById('legend-completed-cnt');
        const elRun = document.getElementById('legend-running-cnt');
        const elUnc = document.getElementById('legend-uncertain-cnt');
        const elFail = document.getElementById('legend-failed-cnt');

        if (elComp) elComp.textContent = utils.formatNumber(completed);
        if (elRun) elRun.textContent = utils.formatNumber(running);
        if (elUnc) elUnc.textContent = utils.formatNumber(uncertain);
        if (elFail) elFail.textContent = utils.formatNumber(failed);

        const centerPct = document.getElementById('donut-center-pct');
        const centerLbl = document.getElementById('donut-center-lbl');
        const elCompPct = document.getElementById('legend-completed-pct');
        const elRunPct = document.getElementById('legend-running-pct');
        const elUncPct = document.getElementById('legend-uncertain-pct');
        const elFailPct = document.getElementById('legend-failed-pct');

        if (total > 0) {
            const pctComp = ((completed / total) * 100).toFixed(1);
            if (centerPct) centerPct.textContent = `${pctComp}%`;
            if (centerLbl) centerLbl.textContent = 'SUCCESS';
            if (elCompPct) elCompPct.textContent = `${pctComp}%`;
            if (elRunPct) elRunPct.textContent = `${((running / total) * 100).toFixed(1)}%`;
            if (elUncPct) elUncPct.textContent = `${((uncertain / total) * 100).toFixed(1)}%`;
            if (elFailPct) elFailPct.textContent = `${((failed / total) * 100).toFixed(1)}%`;
        } else {
            if (centerPct) centerPct.textContent = '—';
            if (centerLbl) centerLbl.textContent = 'NO DATA';
            if (elCompPct) elCompPct.textContent = '—';
            if (elRunPct) elRunPct.textContent = '—';
            if (elUncPct) elUncPct.textContent = '—';
            if (elFailPct) elFailPct.textContent = '—';
        }

        if (statusChartInstance) {
            statusChartInstance.destroy();
        }

        const ctx = canvas.getContext('2d');
        const chartData = total > 0 ? [completed, running, uncertain, failed] : [1];
        const chartColors = total > 0 ? ['#059669', '#2563EB', '#D97706', '#DC2626'] : ['#E2E8F0'];

        statusChartInstance = new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: total > 0 ? ['Completed', 'Running', 'Uncertain', 'Failed'] : ['No Data'],
                datasets: [{
                    data: chartData,
                    backgroundColor: chartColors,
                    borderWidth: 2,
                    borderColor: state.theme === 'dark' ? '#111827' : '#FFFFFF',
                    hoverOffset: total > 0 ? 3 : 0
                }]
            },
            options: {
                cutout: '76%',
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        enabled: total > 0,
                        callbacks: {
                            label(ctx) {
                                return ` ${ctx.label}: ${utils.formatNumber(ctx.raw)}`;
                            }
                        }
                    }
                }
            }
        });
    }

    function renderDashboardRuns(runs) {
        const tbody = document.getElementById('dashboard-recent-workflows');
        const countEl = document.getElementById('dashboard-runs-count');
        if (!tbody) return;

        if (countEl) countEl.textContent = `Showing ${runs.length} recent runs`;

        if (runs.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 24px; color: var(--color-text-muted);">
                        No workflow runs recorded yet. Submit a request from <a href="/request" style="color: var(--color-accent);">NL Request Studio</a>.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = runs.map(w => {
            const uuidShort = (w.id || '').substring(0, 10);
            const statusLower = (w.status || 'pending').toLowerCase();
            const badgeClass = statusLower === 'completed' ? 'badge-completed' : (statusLower === 'failed' ? 'badge-failed' : (statusLower === 'running' ? 'badge-running' : 'badge-uncertain'));
            const duration = w.duration_ms != null ? `${Math.round(w.duration_ms)}ms` : '—';
            const timeAgo = utils.formatDate(w.created_at);

            return `
                <tr>
                    <td><code class="table-uuid">${utils.escapeHtml(uuidShort)}</code></td>
                    <td>
                        <div style="font-weight: 500;">${utils.escapeHtml(w.workflow_type || 'order_change')}</div>
                    </td>
                    <td><span class="badge ${badgeClass}">${utils.escapeHtml((w.status || 'PENDING').toUpperCase())}</span></td>
                    <td><code style="font-family: var(--font-mono); font-size: 11.5px;">${duration}</code></td>
                    <td><span style="font-family: var(--font-mono); font-size: 11px; color: var(--color-text-secondary);">${w.total_tokens ? utils.formatNumber(w.total_tokens) : '—'}</span></td>
                    <td style="color: var(--color-text-secondary); font-size: 11.5px;">${timeAgo}</td>
                    <td style="text-align: right;">
                        <a href="/workflows/${w.id}" class="btn btn-secondary btn-sm" style="font-size: 11px;">
                            <span>Inspect</span>
                            <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                <polyline points="9 18 15 12 9 6"/>
                            </svg>
                        </a>
                    </td>
                </tr>
            `;
        }).join('');
    }

    // ==============================================================================
    // Workflow History Ledger
    // ==============================================================================
    async function initWorkflowHistory() {
        const searchInput = document.getElementById('workflow-search-input');
        const statusFilters = document.getElementById('workflow-status-filters');
        const pageSizeSelect = document.getElementById('history-page-size');
        const btnExportCsv = document.getElementById('btn-export-csv');
        const btnExportJson = document.getElementById('btn-export-json');

        try {
            const metrics = await api.getMetrics();
            const total = metrics.total_workflows || 0;
            const completed = metrics.completed_workflows || 0;
            const running = metrics.running_workflows || 0;
            const uncertain = metrics.uncertain_workflows || 0;
            const failed = metrics.failed_workflows || 0;

            const elTot = document.getElementById('history-total-traces');
            const elComp = document.getElementById('history-completed-cnt');
            const elRun = document.getElementById('history-running-cnt');
            const elUnc = document.getElementById('history-uncertain-cnt');
            const elFail = document.getElementById('history-failed-cnt');

            if (elTot) elTot.textContent = utils.formatNumber(total);
            if (elComp) elComp.textContent = utils.formatNumber(completed);
            if (elRun) elRun.textContent = utils.formatNumber(running);
            if (elUnc) elUnc.textContent = utils.formatNumber(uncertain);
            if (elFail) elFail.textContent = utils.formatNumber(failed);

            // Pill counts
            const pAll = document.getElementById('pill-cnt-all');
            const pComp = document.getElementById('pill-cnt-completed');
            const pRun = document.getElementById('pill-cnt-running');
            const pUnc = document.getElementById('pill-cnt-uncertain');
            const pFail = document.getElementById('pill-cnt-failed');

            if (pAll) pAll.textContent = utils.formatNumber(total);
            if (pComp) pComp.textContent = utils.formatNumber(completed);
            if (pRun) pRun.textContent = utils.formatNumber(running);
            if (pUnc) pUnc.textContent = utils.formatNumber(uncertain);
            if (pFail) pFail.textContent = utils.formatNumber(failed);

            // Load workflows
            await loadHistoryPage(1);

            // Search Filter
            if (searchInput) {
                searchInput.addEventListener('input', (e) => {
                    state.historyFilter.search = e.target.value.trim().toLowerCase();
                    renderHistoryTable();
                });
            }

            // Status Filter Pills
            if (statusFilters) {
                statusFilters.addEventListener('click', (e) => {
                    const btn = e.target.closest('.filter-pill-btn');
                    if (!btn) return;
                    statusFilters.querySelectorAll('.filter-pill-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    state.historyFilter.status = btn.dataset.status || 'all';
                    loadHistoryPage(1);
                });
            }

            // Page Size Select
            if (pageSizeSelect) {
                pageSizeSelect.addEventListener('change', (e) => {
                    state.historyFilter.pageSize = parseInt(e.target.value, 10) || 25;
                    loadHistoryPage(1);
                });
            }

            // Functional Export CSV
            if (btnExportCsv) {
                btnExportCsv.addEventListener('click', () => {
                    if (state.workflows.length === 0) {
                        utils.showToast('No records available to export', 'error');
                        return;
                    }
                    const headers = ['id', 'workflow_type', 'status', 'created_at', 'duration_ms', 'correlation_id'];
                    const rows = state.workflows.map(w => [
                        `"${w.id}"`,
                        `"${w.workflow_type || ''}"`,
                        `"${w.status || ''}"`,
                        `"${w.created_at || ''}"`,
                        w.duration_ms != null ? w.duration_ms : '',
                        `"${w.correlation_id || ''}"`
                    ].join(','));
                    const csv = [headers.join(','), ...rows].join('\n');
                    utils.downloadFile(csv, `relay-workflows-${Date.now()}.csv`, 'text/csv');
                });
            }

            // Functional Export JSON
            if (btnExportJson) {
                btnExportJson.addEventListener('click', () => {
                    if (state.workflows.length === 0) {
                        utils.showToast('No records available to export', 'error');
                        return;
                    }
                    const json = JSON.stringify(state.workflows, null, 2);
                    utils.downloadFile(json, `relay-workflows-${Date.now()}.json`, 'application/json');
                });
            }

        } catch (error) {
            const tbody = document.getElementById('workflow-list-body');
            if (tbody) {
                tbody.innerHTML = `
                    <tr>
                        <td colspan="7" style="text-align: center; padding: 24px; color: var(--color-error);">
                            Failed to load workflow history: ${utils.escapeHtml(error.message)}
                        </td>
                    </tr>
                `;
            }
        }
    }

    async function loadHistoryPage(page) {
        state.historyFilter.page = page;
        const res = await api.getWorkflows(page, state.historyFilter.pageSize, state.historyFilter.status);
        state.workflows = res.items || [];
        state.historyTotal = res.total || 0;
        state.historyPages = res.total_pages || 1;
        renderHistoryTable();
    }

    function renderHistoryTable() {
        const tbody = document.getElementById('workflow-list-body');
        const countEl = document.getElementById('history-entry-count');
        const paginationEl = document.getElementById('history-pagination');
        if (!tbody) return;

        let filtered = state.workflows;
        if (state.historyFilter.search) {
            const q = state.historyFilter.search;
            filtered = filtered.filter(w => {
                const idMatch = (w.id || '').toLowerCase().includes(q);
                const typeMatch = (w.workflow_type || '').toLowerCase().includes(q);
                const orderMatch = (w.order_id || '').toLowerCase().includes(q);
                const eventMatch = (w.external_event_id || '').toLowerCase().includes(q);
                return idMatch || typeMatch || orderMatch || eventMatch;
            });
        }

        if (countEl) {
            countEl.textContent = `Showing ${filtered.length} of ${utils.formatNumber(state.historyTotal || filtered.length)} entries`;
        }

        if (filtered.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="text-align: center; padding: 32px; color: var(--color-text-muted);">
                        No workflow records match the active criteria.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = filtered.map(w => {
            const uuidShort = (w.id || '').substring(0, 10);
            const statusLower = (w.status || 'pending').toLowerCase();
            const badgeClass = statusLower === 'completed' ? 'badge-completed' : (statusLower === 'failed' ? 'badge-failed' : (statusLower === 'running' ? 'badge-running' : 'badge-uncertain'));
            const duration = w.duration_ms != null ? `${Math.round(w.duration_ms)}ms` : '—';
            const timeFormatted = utils.formatDate(w.created_at);

            return `
                <tr>
                    <td><code class="table-uuid">${utils.escapeHtml(uuidShort)}</code></td>
                    <td>
                        <span style="font-family: var(--font-mono); font-size: 11.5px;">${utils.escapeHtml(w.order_id || '—')}</span>
                        ${w.customer_id ? `<span class="table-sub-uuid">${utils.escapeHtml(w.customer_id)}</span>` : ''}
                    </td>
                    <td><span style="font-weight: 500;">${utils.escapeHtml(w.workflow_type || 'order_change')}</span></td>
                    <td><span class="badge ${badgeClass}">${utils.escapeHtml((w.status || 'PENDING').toUpperCase())}</span></td>
                    <td><code style="font-family: var(--font-mono); font-size: 11.5px;">${duration}</code></td>
                    <td style="color: var(--color-text-secondary); font-size: 11.5px;">${timeFormatted}</td>
                    <td style="text-align: right;">
                        <a href="/workflows/${w.id}" class="btn btn-secondary btn-sm" style="font-size: 11px;">Inspect</a>
                    </td>
                </tr>
            `;
        }).join('');

        // Pagination
        if (paginationEl) {
            if (state.historyPages <= 1) {
                paginationEl.innerHTML = '';
            } else {
                let pagHtml = '';
                for (let i = 1; i <= state.historyPages; i++) {
                    pagHtml += `<button type="button" class="btn btn-sm ${i === state.historyFilter.page ? 'btn-primary' : 'btn-secondary'}" onclick="window.loadHistoryPage(${i})">${i}</button>`;
                }
                paginationEl.innerHTML = pagHtml;
            }
        }
    }

    // ==============================================================================
    // NL Request Studio
    // ==============================================================================
    function initNlStudio() {
        const textarea = document.getElementById('nl-text');
        const charCounter = document.getElementById('nl-char-counter');
        const chips = document.querySelectorAll('.suggestion-chip');
        const btnSynthesize = document.getElementById('btn-synthesize-workflow');
        const btnReset = document.getElementById('btn-reset-studio');
        const errorBanner = document.getElementById('nl-studio-error');

        const extractOrderId = document.getElementById('extract-order-id');
        const extractDate = document.getElementById('extract-target-date');

        const outcomeEmpty = document.getElementById('nl-outcome-empty');
        const outcomeContent = document.getElementById('nl-outcome-content');
        const outcomeBadge = document.getElementById('nl-outcome-badge');
        const outcomeWfId = document.getElementById('nl-outcome-wfid');
        const outcomeTokens = document.getElementById('nl-outcome-tokens');
        const outcomeCost = document.getElementById('nl-outcome-cost');
        const outcomeAction = document.getElementById('nl-outcome-action');

        function updateClientDetection(text) {
            if (charCounter) charCounter.textContent = `${text.length} / 2000 chars`;

            const ordMatch = text.match(/ORD-[A-Za-z0-9]+/i);
            if (extractOrderId) extractOrderId.textContent = ordMatch ? ordMatch[0].toUpperCase() : 'None detected';

            const dateMatch = text.match(/\b\d{4}-\d{2}-\d{2}\b/);
            if (extractDate) extractDate.textContent = dateMatch ? dateMatch[0] : 'Parsed on submission';
        }

        if (textarea) {
            textarea.addEventListener('input', () => updateClientDetection(textarea.value));
            updateClientDetection(textarea.value);
        }

        chips.forEach(chip => {
            chip.addEventListener('click', () => {
                const prompt = chip.dataset.prompt;
                if (textarea && prompt) {
                    textarea.value = prompt;
                    updateClientDetection(prompt);
                }
            });
        });

        if (btnReset) {
            btnReset.addEventListener('click', () => {
                if (textarea) {
                    textarea.value = '';
                    updateClientDetection('');
                }
                if (errorBanner) errorBanner.style.display = 'none';
                if (outcomeEmpty) outcomeEmpty.style.display = 'block';
                if (outcomeContent) outcomeContent.style.display = 'none';
            });
        }

        if (btnSynthesize) {
            btnSynthesize.addEventListener('click', async () => {
                const text = textarea ? textarea.value.trim() : '';
                if (!text) {
                    utils.showToast('Please enter an order change request', 'error');
                    return;
                }

                btnSynthesize.disabled = true;
                btnSynthesize.innerHTML = `<span class="spinner" style="width: 14px; height: 14px; border-width: 2px;"></span> Interpreting &amp; Executing…`;
                if (errorBanner) errorBanner.style.display = 'none';

                try {
                    const res = await api.submitNLRequest({
                        text,
                        source_system: 'web-console',
                        external_event_id: `evt-${Date.now()}`
                    });

                    utils.showToast('Request interpreted and executed', 'success');

                    if (outcomeEmpty) outcomeEmpty.style.display = 'none';
                    if (outcomeContent) outcomeContent.style.display = 'flex';

                    if (outcomeBadge) {
                        outcomeBadge.textContent = res.success ? 'COMPLETED' : 'FAILED';
                        outcomeBadge.className = res.success ? 'badge badge-completed' : 'badge badge-failed';
                    }

                    if (outcomeWfId) outcomeWfId.textContent = res.workflow_id || 'None';
                    if (outcomeTokens) outcomeTokens.textContent = res.total_tokens != null ? utils.formatNumber(res.total_tokens) : '—';
                    if (outcomeCost) outcomeCost.textContent = res.estimated_cost_usd != null ? `$${res.estimated_cost_usd.toFixed(4)}` : '—';

                    if (outcomeAction && res.workflow_id) {
                        outcomeAction.innerHTML = `
                            <a href="/workflows/${res.workflow_id}" class="btn btn-primary" style="width: 100%;">
                                View Execution Details &rarr;
                            </a>
                        `;
                    }
                } catch (err) {
                    if (errorBanner) {
                        errorBanner.textContent = `Error: ${err.message}`;
                        errorBanner.style.display = 'block';
                    }
                    utils.showToast(err.message, 'error');
                } finally {
                    btnSynthesize.disabled = false;
                    btnSynthesize.innerHTML = `
                        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>
                        </svg>
                        <span>Interpret &amp; Execute Workflow</span>
                    `;
                }
            });
        }
    }

    // ==============================================================================
    // Workflow Detail View
    // ==============================================================================
    async function loadWorkflowDetail(id) {
        const detailView = document.getElementById('workflow-detail-view');
        const notFoundView = document.getElementById('workflow-not-found-view');

        try {
            const wf = await api.getWorkflow(id);
            state.activeWorkflow = wf;
            if (notFoundView) notFoundView.style.display = 'none';
            if (detailView) detailView.style.display = 'block';
            renderWorkflowDetail(wf);
        } catch (err) {
            if (err.status === 404) {
                if (detailView) detailView.style.display = 'none';
                if (notFoundView) notFoundView.style.display = 'block';
            } else {
                utils.showToast(`Failed to load workflow: ${err.message}`, 'error');
            }
        }
    }

    function renderWorkflowDetail(wf) {
        // Breadcrumb & Copy UUID
        const breadcrumbId = document.getElementById('wf-breadcrumb-id');
        const btnCopyUuid = document.getElementById('btn-copy-uuid');
        const btnExportTrace = document.getElementById('btn-export-trace');

        if (breadcrumbId) breadcrumbId.textContent = wf.id;
        if (btnCopyUuid) {
            btnCopyUuid.onclick = () => utils.copyToClipboard(wf.id, 'Workflow ID copied');
        }
        if (btnExportTrace) {
            btnExportTrace.onclick = () => {
                utils.downloadFile(JSON.stringify(wf, null, 2), `workflow-${wf.id}.json`, 'application/json');
            };
        }

        // Header Title & Status
        const titleEl = document.getElementById('wf-title');
        const statusBadge = document.getElementById('wf-header-status');
        if (titleEl) titleEl.textContent = wf.workflow_type || 'order_change';
        if (statusBadge) {
            const st = (wf.status || 'PENDING').toUpperCase();
            statusBadge.textContent = st;
            statusBadge.className = `badge badge-${st.toLowerCase()}`;
        }

        // Subheader Timings
        const triggerEl = document.getElementById('wf-trigger-source');
        const startedEl = document.getElementById('wf-started-time');
        const completedEl = document.getElementById('wf-completed-time');
        const latencyEl = document.getElementById('wf-runtime-latency');

        if (triggerEl) triggerEl.textContent = wf.source_system || '—';
        if (startedEl) startedEl.textContent = utils.formatDate(wf.started_at);
        if (completedEl) completedEl.textContent = utils.formatDate(wf.completed_at);
        if (latencyEl) latencyEl.textContent = wf.duration_ms != null ? `${Math.round(wf.duration_ms)}ms` : '—';

        // Metadata Grid Cards
        const metaType = document.getElementById('meta-wf-type');
        const metaExtRef = document.getElementById('meta-ext-ref');
        const metaSource = document.getElementById('meta-source');
        const metaOrderId = document.getElementById('meta-order-id');
        const metaCustId = document.getElementById('meta-customer-id');
        const metaNewDelivery = document.getElementById('meta-new-delivery');
        const metaCorr = document.getElementById('meta-correlation-id');
        const metaIdem = document.getElementById('meta-idempotency-key');
        const metaFailCat = document.getElementById('meta-failure-cat');

        const orig = wf.original_request || {};
        const res = wf.result || {};

        if (metaType) metaType.textContent = wf.workflow_type || '—';
        if (metaExtRef) metaExtRef.textContent = wf.external_event_id || orig.external_event_id || '—';
        if (metaSource) metaSource.textContent = wf.source_system || orig.source_system || '—';

        if (metaOrderId) metaOrderId.textContent = wf.order_id || orig.order_id || '—';
        if (metaCustId) metaCustId.textContent = wf.customer_id || orig.customer_id || '—';
        if (metaNewDelivery) metaNewDelivery.textContent = res.new_delivery_date || orig.requested_delivery_date || '—';

        if (metaCorr) metaCorr.textContent = wf.correlation_id || '—';
        if (metaIdem) metaIdem.textContent = wf.idempotency_key || '—';
        if (metaFailCat) metaFailCat.textContent = wf.failure_category || 'None';

        // LLM Telemetry Card
        const metaLlmModel = document.getElementById('meta-llm-model');
        const metaLlmLatency = document.getElementById('meta-llm-latency');
        const metaLlmTokens = document.getElementById('meta-llm-tokens');
        const metaLlmCost = document.getElementById('meta-llm-cost');

        const invocations = wf.llm_invocations || [];
        if (invocations.length > 0) {
            const inv = invocations[0];
            if (metaLlmModel) metaLlmModel.textContent = inv.model || '—';
            if (metaLlmLatency) metaLlmLatency.textContent = inv.latency_ms != null ? `${inv.latency_ms}ms` : '—';
            if (metaLlmTokens) metaLlmTokens.textContent = inv.total_tokens != null ? utils.formatNumber(inv.total_tokens) : '—';
            if (metaLlmCost) metaLlmCost.textContent = inv.estimated_cost_usd != null ? `$${inv.estimated_cost_usd.toFixed(4)}` : '—';
        } else {
            if (metaLlmModel) metaLlmModel.textContent = 'None';
            if (metaLlmLatency) metaLlmLatency.textContent = '—';
            if (metaLlmTokens) metaLlmTokens.textContent = '—';
            if (metaLlmCost) metaLlmCost.textContent = '—';
        }

        // Real DAG Stepper Progression
        const stepperTrack = document.getElementById('wf-dag-stepper');
        const summaryPill = document.getElementById('dag-summary-pill');
        const steps = wf.steps || [];

        if (summaryPill) {
            const completedCount = steps.filter(s => (s.status || '').toLowerCase() === 'completed').length;
            if (steps.length > 0) {
                summaryPill.textContent = `${completedCount}/${steps.length} Steps Succeeded`;
                summaryPill.className = wf.status === 'completed' ? 'badge badge-completed' : 'badge badge-failed';
            } else {
                summaryPill.textContent = 'No discrete step records';
                summaryPill.className = 'badge badge-pending';
            }
        }

        if (stepperTrack) {
            if (steps.length === 0) {
                stepperTrack.innerHTML = `
                    <div style="padding: 16px; color: var(--color-text-muted); font-size: 12px;">
                        No discrete step telemetry records persisted for this execution.
                    </div>
                `;
            } else {
                stepperTrack.innerHTML = steps.map((s, idx) => {
                    const st = (s.status || 'pending').toLowerCase();
                    const isCompleted = st === 'completed';
                    const isFailed = st === 'failed';
                    const durationText = s.duration_ms != null ? `${s.duration_ms}ms` : '—';

                    return `
                        <div class="dag-node ${isCompleted ? 'completed' : (isFailed ? 'failed' : '')}" style="margin-bottom: 8px;">
                            <div class="dag-node-box">
                                ${isCompleted ? `
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                        <polyline points="20 6 9 17 4 12"/>
                                    </svg>
                                ` : (isFailed ? `
                                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                                        <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
                                    </svg>
                                ` : `
                                    <span style="font-size: 11px; font-weight: 700;">${idx + 1}</span>
                                `)}
                            </div>
                            <span class="dag-node-num">Step ${idx + 1} &bull; ${durationText}</span>
                            <span class="dag-node-label">${utils.escapeHtml(s.step_name)}</span>
                            <span class="dag-node-sub">Attempt #${s.attempt_number || 1}</span>
                        </div>
                    `;
                }).join('');
            }
        }

        // Steps Telemetry Table
        const stepsTbody = document.getElementById('wf-steps-tbody');
        const stepsBadge = document.getElementById('steps-log-badge');
        if (stepsBadge) stepsBadge.textContent = `${steps.length} Persisted Operations`;

        if (stepsTbody) {
            if (steps.length === 0) {
                stepsTbody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align: center; color: var(--color-text-muted); padding: 24px;">
                            No discrete step attempts recorded for this execution.
                        </td>
                    </tr>
                `;
            } else {
                stepsTbody.innerHTML = steps.map(s => {
                    const st = (s.status || 'completed').toUpperCase();
                    const badgeClass = st === 'COMPLETED' ? 'badge-completed' : (st === 'FAILED' ? 'badge-failed' : 'badge-running');
                    const errContext = s.error_category ? `[${utils.escapeHtml(s.error_category)}]` : 'None';

                    return `
                        <tr>
                            <td><strong>${utils.escapeHtml(s.step_name)}</strong></td>
                            <td><span class="badge ${badgeClass}">${st}</span></td>
                            <td>#${s.attempt_number || 1}</td>
                            <td>${utils.formatDate(s.started_at)}</td>
                            <td><code>${s.duration_ms != null ? `${s.duration_ms}ms` : '—'}</code></td>
                            <td style="text-align: right; color: var(--color-text-secondary); font-family: var(--font-mono); font-size: 11px;">
                                ${errContext}
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // Raw State Inspector
        const codeBlock = document.getElementById('wf-raw-json-code');
        const tabBtns = document.querySelectorAll('.tab-btn');
        const btnCopyRaw = document.getElementById('btn-copy-raw-json');

        const payloads = {
            'tab-input': wf.original_request || {},
            'tab-state': wf.result || wf.error_details || {},
            'tab-trace': wf
        };

        function setInspectorTab(tabKey) {
            if (codeBlock) {
                const data = payloads[tabKey] || wf;
                codeBlock.textContent = JSON.stringify(data, null, 2);
            }
        }

        tabBtns.forEach(btn => {
            btn.addEventListener('click', () => {
                tabBtns.forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                setInspectorTab(btn.dataset.tab);
            });
        });

        if (btnCopyRaw) {
            btnCopyRaw.addEventListener('click', () => {
                if (codeBlock) utils.copyToClipboard(codeBlock.textContent, 'JSON payload copied');
            });
        }

        setInspectorTab('tab-state');
    }

    // ==============================================================================
    // Health Poller
    // ==============================================================================
    async function checkSystemHealth() {
        const pill = document.getElementById('system-health-pill');
        const text = document.getElementById('health-text');
        const latency = document.getElementById('health-latency');
        if (!pill) return;

        const res = await api.checkReadiness();
        if (res.ok) {
            pill.style.background = 'var(--color-success-bg)';
            pill.style.borderColor = 'var(--color-success-border)';
            pill.style.color = 'var(--color-success-text)';
            if (text) text.textContent = 'System: Ready';
            if (latency) {
                latency.style.display = 'inline-block';
                latency.textContent = `${res.latencyMs}ms ping`;
            }
        } else {
            pill.style.background = 'var(--color-warning-bg)';
            pill.style.borderColor = 'var(--color-warning-border)';
            pill.style.color = 'var(--color-warning-text)';
            if (text) text.textContent = 'System: Degraded';
            if (latency) latency.style.display = 'none';
        }
    }

    // Exports
    window.initDashboard = initDashboard;
    window.initWorkflowHistory = initWorkflowHistory;
    window.initNlStudio = initNlStudio;
    window.loadWorkflowDetail = loadWorkflowDetail;
    window.loadHistoryPage = loadHistoryPage;

    document.addEventListener('DOMContentLoaded', () => {
        themeManager.init();
        checkSystemHealth();
        setInterval(checkSystemHealth, 30000);
    });

})();