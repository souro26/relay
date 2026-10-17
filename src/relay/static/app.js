/**
 * Relay - Business Workflow Integration
 * Modern Frontend JavaScript with Real-time Telemetry, DAG Visualizer & Interactive Charts
 */

(function() {
    'use strict';

    // Chart instances
    let statusChartInstance = null;
    let latencyChartInstance = null;

    // Theme Management
    const theme = {
        STORAGE_KEY: 'relay-theme-preference',

        getPreferredTheme() {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            if (stored === 'light' || stored === 'dark') {
                return stored;
            }
            return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
                ? 'dark'
                : 'light';
        },

        applyTheme(mode) {
            document.documentElement.setAttribute('data-theme', mode);
            localStorage.setItem(this.STORAGE_KEY, mode);
            this.updateToggleUi(mode);
            this.updateChartsTheme(mode);
        },

        toggle() {
            const current = document.documentElement.getAttribute('data-theme') || 'light';
            const next = current === 'dark' ? 'light' : 'dark';
            this.applyTheme(next);
        },

        updateToggleUi(mode) {
            const btn = document.getElementById('theme-toggle-btn');
            if (!btn) return;
            const icon = btn.querySelector('.theme-icon');
            if (mode === 'dark') {
                btn.setAttribute('aria-label', 'Switch to light mode');
                btn.title = 'Switch to light mode';
                if (icon) {
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
                }
            } else {
                btn.setAttribute('aria-label', 'Switch to dark mode');
                btn.title = 'Switch to dark mode';
                if (icon) {
                    icon.innerHTML = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>`;
                }
            }
        },

        updateChartsTheme(mode) {
            if (!statusChartInstance && !latencyChartInstance) return;
            const textColor = mode === 'dark' ? '#94a3b8' : '#64748b';
            const gridColor = mode === 'dark' ? 'rgba(51, 65, 85, 0.4)' : 'rgba(226, 232, 240, 0.8)';

            if (statusChartInstance) {
                if (statusChartInstance.options.plugins?.legend?.labels) {
                    statusChartInstance.options.plugins.legend.labels.color = textColor;
                }
                statusChartInstance.update();
            }

            if (latencyChartInstance) {
                if (latencyChartInstance.options.scales?.x) {
                    latencyChartInstance.options.scales.x.ticks.color = textColor;
                    latencyChartInstance.options.scales.x.grid.color = gridColor;
                }
                if (latencyChartInstance.options.scales?.y) {
                    latencyChartInstance.options.scales.y.ticks.color = textColor;
                    latencyChartInstance.options.scales.y.grid.color = 'transparent';
                }
                if (latencyChartInstance.options.plugins?.legend?.labels) {
                    latencyChartInstance.options.plugins.legend.labels.color = textColor;
                }
                latencyChartInstance.update();
            }
        },

        init() {
            const initial = this.getPreferredTheme();
            this.applyTheme(initial);

            const btn = document.getElementById('theme-toggle-btn');
            if (btn) {
                btn.addEventListener('click', () => this.toggle());
            }

            // Sync with system changes if user hasn't explicitly set a preference
            if (window.matchMedia) {
                window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
                    if (!localStorage.getItem(this.STORAGE_KEY)) {
                        this.applyTheme(e.matches ? 'dark' : 'light');
                    }
                });
            }
        }
    };

    // Utility Functions
    const utils = {
        escapeHtml(text) {
            if (text == null) return '';
            const div = document.createElement('div');
            div.textContent = String(text);
            return div.innerHTML;
        },

        formatDate(dateString) {
            if (!dateString) return '—';
            try {
                const date = new Date(dateString);
                return date.toLocaleString(undefined, {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                });
            } catch {
                return dateString;
            }
        },

        formatRelativeTime(dateString) {
            if (!dateString) return '—';
            try {
                const date = new Date(dateString);
                const now = new Date();
                const diffMs = now - date;
                const diffSecs = Math.floor(diffMs / 1000);
                const diffMins = Math.floor(diffSecs / 60);
                const diffHours = Math.floor(diffMins / 60);
                const diffDays = Math.floor(diffHours / 24);

                if (diffSecs < 10) return 'just now';
                if (diffSecs < 60) return `${diffSecs}s ago`;
                if (diffMins < 60) return `${diffMins}m ago`;
                if (diffHours < 24) return `${diffHours}h ago`;
                if (diffDays < 7) return `${diffDays}d ago`;
                return this.formatDate(dateString);
            } catch {
                return dateString;
            }
        },

        generateUuid() {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        },

        generateExternalEventId() {
            return `evt-${Date.now()}-${Math.random().toString(36).substring(2, 9)}`;
        },

        debounce(fn, delay) {
            let timeoutId;
            return (...args) => {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => fn.apply(this, args), delay);
            };
        },

        showToast(message, type = 'error') {
            const container = document.querySelector('.flash-messages') || this.createToastContainer();
            const toast = document.createElement('div');
            toast.className = `flash flash-${type}`;
            toast.textContent = message;
            container.appendChild(toast);
            setTimeout(() => {
                toast.style.opacity = '0';
                toast.style.transform = 'translateY(-10px)';
                setTimeout(() => toast.remove(), 300);
            }, 5000);
        },

        createToastContainer() {
            const container = document.createElement('div');
            container.className = 'flash-messages';
            container.setAttribute('role', 'alert');
            container.setAttribute('aria-live', 'polite');
            document.body.appendChild(container);
            return container;
        },

        formatNumber(num) {
            if (num == null) return '0';
            return new Intl.NumberFormat().format(num);
        }
    };

    // API Client
    const api = {
        baseUrl: '/api/v1',

        async request(endpoint, options = {}) {
            const url = `${this.baseUrl}${endpoint}`;
            const config = {
                headers: {
                    'Content-Type': 'application/json',
                    ...options.headers,
                },
                ...options,
            };

            if (config.body && typeof config.body === 'object') {
                config.body = JSON.stringify(config.body);
            }

            try {
                const response = await fetch(url, config);
                const data = await response.json().catch(() => ({}));

                if (!response.ok) {
                    throw new ApiError(response.status, data);
                }

                return data;
            } catch (error) {
                if (error instanceof ApiError) throw error;
                throw new ApiError(0, { message: error.message || 'Network error' });
            }
        },

        async getMetrics() {
            return this.request('/metrics');
        },

        async getWorkflows(page = 1, pageSize = 20) {
            return this.request(`/workflows?page=${page}&page_size=${pageSize}`);
        },

        async getWorkflow(id) {
            return this.request(`/workflows/${id}`);
        },

        async createOrderChange(request) {
            return this.request('/order-change-requests', {
                method: 'POST',
                body: request,
            });
        },

        async createNaturalLanguageRequest(request) {
            return this.request('/order-change-requests/nl', {
                method: 'POST',
                body: request,
            });
        },

        async checkHealth() {
            const response = await fetch('/ready').catch(() => null);
            return response && response.ok;
        }
    };

    class ApiError extends Error {
        constructor(status, data) {
            super(data.message || data.detail || 'API Error');
            this.name = 'ApiError';
            this.status = status;
            this.data = data;
        }
    }

    // State Management
    const state = {
        workflows: {
            items: [],
            total: 0,
            page: 1,
            pageSize: 20,
            totalPages: 0,
            loading: false,
            error: null,
            filterStatus: 'all',
            searchQuery: '',
        },
    };

    // DOM Elements Cache
    const dom = {};

    function cacheDomElements() {
        // Dashboard Stats
        dom.totalWorkflows = document.getElementById('total-workflows');
        dom.completedWorkflows = document.getElementById('completed-workflows');
        dom.failedWorkflows = document.getElementById('failed-workflows');
        dom.successRate = document.getElementById('success-rate');
        dom.medianDuration = document.getElementById('median-duration');
        dom.p95Duration = document.getElementById('p95-duration');
        dom.totalTokens = document.getElementById('total-tokens');
        dom.estimatedSpending = document.getElementById('estimated-spending');
        dom.recentWorkflows = document.getElementById('recent-workflows');
        dom.recentWorkflowsEmpty = document.getElementById('recent-workflows-empty');
        dom.statusChart = document.getElementById('statusChart');
        dom.latencyChart = document.getElementById('latencyChart');

        // Workflow History
        dom.workflowsTableBody = document.getElementById('workflows-table-body');
        dom.workflowsEmpty = document.getElementById('workflows-empty');
        dom.pagination = document.getElementById('pagination');
        dom.workflowSearchInput = document.getElementById('workflow-search-input');
        dom.statusFilters = document.getElementById('status-filters');

        // Workflow Details
        dom.workflowDetail = document.getElementById('workflow-detail');
        dom.workflowNotFound = document.getElementById('workflow-not-found');
        dom.wfBreadcrumbId = document.getElementById('wf-breadcrumb-id');
        dom.wfHeaderStatus = document.getElementById('wf-header-status');
        dom.wfSummaryStatus = document.getElementById('wf-summary-status');
        dom.wfPipelineTrack = document.getElementById('workflow-pipeline-track');
        dom.wfId = document.getElementById('wf-id');
        dom.wfType = document.getElementById('wf-type');
        dom.wfSourceSystem = document.getElementById('wf-source-system');
        dom.wfExternalEventId = document.getElementById('wf-external-event-id');
        dom.wfStarted = document.getElementById('wf-started');
        dom.wfCreated = document.getElementById('wf-created');
        dom.wfCompleted = document.getElementById('wf-completed');
        dom.wfDuration = document.getElementById('wf-duration');
        dom.wfOrderId = document.getElementById('wf-order-id');
        dom.wfCustomerId = document.getElementById('wf-customer-id');
        dom.wfPrevDelivery = document.getElementById('wf-prev-delivery');
        dom.wfNewDelivery = document.getElementById('wf-new-delivery');
        dom.wfOrderStatus = document.getElementById('wf-order-status');
        dom.wfCorrelation = document.getElementById('wf-correlation');
        dom.wfIdempotencyKey = document.getElementById('wf-idempotency-key');
        dom.wfFailureCategory = document.getElementById('wf-failure-category');
        dom.wfStepsTbody = document.getElementById('wf-steps-tbody');
        dom.wfStepsEmpty = document.getElementById('wf-steps-empty');
        dom.wfLlmTbody = document.getElementById('wf-llm-tbody');
        dom.wfLlmEmpty = document.getElementById('wf-llm-empty');
        dom.wfJsonOriginal = document.getElementById('wf-json-original');
        dom.wfJsonInterpreted = document.getElementById('wf-json-interpreted');
        dom.wfJsonResult = document.getElementById('wf-json-result');
        dom.wfJsonError = document.getElementById('wf-json-error');

        // NL Form
        dom.nlForm = document.getElementById('nl-request-form');
        dom.nlText = document.getElementById('nl-text');
        dom.nlCharCount = document.getElementById('nl-char-count');
        dom.nlSourceSystem = document.getElementById('nl-source-system');
        dom.nlExternalEventId = document.getElementById('nl-external-event-id');
        dom.nlCustomerId = document.getElementById('nl-customer-id');
        dom.nlSubmitBtn = document.getElementById('nl-submit-btn');
        dom.nlLoading = document.getElementById('nl-loading');
        dom.nlError = document.getElementById('nl-error');
        dom.nlSuccess = document.getElementById('nl-success');
        dom.nlResult = document.getElementById('nl-result');
        dom.nlErrorCode = document.getElementById('nl-error-code');
        dom.nlErrorMessage = document.getElementById('nl-error-message');
        dom.nlDraftOrderId = document.getElementById('nl-draft-order-id');
        dom.nlDraftCustomerId = document.getElementById('nl-draft-customer-id');
        dom.nlDraftDeliveryDate = document.getElementById('nl-draft-delivery-date');
        dom.nlWorkflowLink = document.getElementById('nl-workflow-link');
    }

    // System Health Check
    async function checkSystemHealth() {
        const pill = document.getElementById('system-health-pill');
        if (!pill) return;

        const isHealthy = await api.checkHealth();
        if (isHealthy) {
            pill.innerHTML = `
                <span class="status-pulse-dot" style="background: var(--color-success);"></span>
                <span>Operational</span>
            `;
            pill.style.borderColor = 'rgba(16, 185, 129, 0.3)';
        } else {
            pill.innerHTML = `
                <span class="status-pulse-dot" style="background: var(--color-error);"></span>
                <span>Degraded</span>
            `;
            pill.style.borderColor = 'rgba(239, 68, 68, 0.3)';
        }
    }

    // Dashboard Rendering
    function renderDashboard(data) {
        if (dom.totalWorkflows) dom.totalWorkflows.textContent = utils.formatNumber(data.total_workflows || 0);
        if (dom.completedWorkflows) dom.completedWorkflows.textContent = utils.formatNumber(data.completed_workflows || 0);
        if (dom.failedWorkflows) dom.failedWorkflows.textContent = utils.formatNumber(data.failed_workflows || 0);
        if (dom.successRate) dom.successRate.textContent = data.success_rate_percentage || '—';

        if (dom.medianDuration) {
            dom.medianDuration.textContent = data.median_duration_ms != null ? `${data.median_duration_ms}ms` : '—';
        }
        if (dom.p95Duration) {
            dom.p95Duration.textContent = data.p95_duration_ms != null ? `${data.p95_duration_ms}ms` : '—';
        }
        if (dom.totalTokens) {
            dom.totalTokens.textContent = utils.formatNumber(data.total_tokens || 0);
        }
        if (dom.estimatedSpending) {
            dom.estimatedSpending.textContent = data.total_estimated_cost_usd != null ? `$${data.total_estimated_cost_usd.toFixed(4)}` : '$0.0000';
        }

        // Render Recent Workflows Table
        if (dom.recentWorkflows) {
            const workflows = data.recent_workflows || [];
            if (workflows.length === 0) {
                if (dom.recentWorkflowsEmpty) dom.recentWorkflowsEmpty.hidden = false;
                dom.recentWorkflows.innerHTML = '';
            } else {
                if (dom.recentWorkflowsEmpty) dom.recentWorkflowsEmpty.hidden = true;
                dom.recentWorkflows.innerHTML = workflows.map(w => {
                    const statusClass = `badge badge-${w.status}`;
                    return `
                        <tr>
                            <td><code style="font-family: var(--font-mono); font-size: 0.85rem;">${utils.escapeHtml(w.id.slice(0, 8))}…</code></td>
                            <td><span style="font-weight: 500;">${utils.escapeHtml(w.workflow_type)}</span></td>
                            <td>
                                <span class="${statusClass}">
                                    <span class="status-pulse-dot" style="background: currentColor;"></span>
                                    ${utils.escapeHtml(w.status)}
                                </span>
                            </td>
                            <td style="color: var(--color-text-secondary); font-size: 0.875rem;">${utils.formatRelativeTime(w.created_at)}</td>
                            <td style="text-align: right;">
                                <a href="${utils.escapeHtml(`/workflows/${w.id}`)}" class="btn btn-sm btn-secondary">
                                    Audit &rarr;
                                </a>
                            </td>
                        </tr>
                    `;
                }).join('');
            }
        }

        // Render Interactive Charts
        renderDashboardCharts(data);
    }

    function renderDashboardCharts(data) {
        if (typeof window.Chart === 'undefined') return;

        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        const textColor = isDark ? '#94a3b8' : '#64748b';
        const gridColor = isDark ? 'rgba(51, 65, 85, 0.4)' : 'rgba(226, 232, 240, 0.8)';

        // 1. Status Distribution Doughnut Chart
        if (dom.statusChart) {
            if (statusChartInstance) {
                statusChartInstance.destroy();
            }

            const completed = data.completed_workflows || 0;
            const failed = data.failed_workflows || 0;
            const other = Math.max(0, (data.total_workflows || 0) - completed - failed);

            const hasData = (completed + failed + other) > 0;
            const chartData = hasData ? [completed, failed, other] : [1];
            const bgColors = hasData ? ['#10b981', '#ef4444', '#f59e0b'] : [isDark ? '#334155' : '#e2e8f0'];
            const labels = hasData ? ['Completed', 'Failed', 'Other / Running'] : ['No Executions Yet'];

            statusChartInstance = new window.Chart(dom.statusChart, {
                type: 'doughnut',
                data: {
                    labels: labels,
                    datasets: [{
                        data: chartData,
                        backgroundColor: bgColors,
                        borderWidth: 0,
                        hoverOffset: 6
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    cutout: '74%',
                    plugins: {
                        legend: {
                            position: 'bottom',
                            labels: {
                                color: textColor,
                                boxWidth: 12,
                                padding: 14,
                                font: {
                                    family: "'Inter', sans-serif",
                                    size: 12
                                }
                            }
                        },
                        tooltip: {
                            enabled: hasData
                        }
                    }
                }
            });
        }

        // 2. Latency Benchmarks Bar Chart
        if (dom.latencyChart) {
            if (latencyChartInstance) {
                latencyChartInstance.destroy();
            }

            const median = data.median_duration_ms || 0;
            const p95 = data.p95_duration_ms || 0;

            latencyChartInstance = new window.Chart(dom.latencyChart, {
                type: 'bar',
                data: {
                    labels: ['Median Duration', 'P95 Tail Latency'],
                    datasets: [{
                        label: 'Milliseconds',
                        data: [median, p95],
                        backgroundColor: ['#6366f1', '#ec4899'],
                        borderRadius: 6,
                        maxBarThickness: 40
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    indexAxis: 'y',
                    scales: {
                        x: {
                            beginAtZero: true,
                            grid: {
                                color: gridColor
                            },
                            ticks: {
                                color: textColor,
                                font: { family: "'JetBrains Mono', monospace" }
                            }
                        },
                        y: {
                            grid: { display: false },
                            ticks: {
                                color: textColor,
                                font: { family: "'Inter', sans-serif", weight: '500' }
                            }
                        }
                    },
                    plugins: {
                        legend: { display: false },
                        tooltip: {
                            callbacks: {
                                label: (ctx) => `${ctx.raw} ms`
                            }
                        }
                    }
                }
            });
        }
    }

    // Workflow History Rendering & Filtering
    function renderWorkflows(data) {
        if (!dom.workflowsTableBody) return;

        let workflows = data.items || [];

        // Apply active filter and search
        if (state.workflows.filterStatus && state.workflows.filterStatus !== 'all') {
            workflows = workflows.filter(w => (w.status || '').toLowerCase() === state.workflows.filterStatus);
        }
        if (state.workflows.searchQuery) {
            const q = state.workflows.searchQuery.toLowerCase();
            workflows = workflows.filter(w =>
                (w.id || '').toLowerCase().includes(q) ||
                (w.workflow_type || '').toLowerCase().includes(q) ||
                (w.source_system || '').toLowerCase().includes(q) ||
                (w.external_event_id || '').toLowerCase().includes(q) ||
                (w.order_id || '').toLowerCase().includes(q)
            );
        }

        if (workflows.length === 0) {
            if (dom.workflowsEmpty) {
                dom.workflowsEmpty.hidden = false;
                dom.workflowsEmpty.style.display = 'block';
            }
            dom.workflowsTableBody.innerHTML = '';
            return;
        }

        if (dom.workflowsEmpty) {
            dom.workflowsEmpty.hidden = true;
            dom.workflowsEmpty.style.display = 'none';
        }

        dom.workflowsTableBody.innerHTML = workflows.map(w => {
            const statusClass = `badge badge-${w.status}`;
            const eventSnippet = w.external_event_id ? utils.escapeHtml(w.external_event_id) : '—';
            const sourceSnippet = w.source_system ? `<span class="badge" style="background: var(--color-surface); font-size: 0.75rem;">${utils.escapeHtml(w.source_system)}</span>` : '';

            return `
                <tr>
                    <td>
                        <a href="${utils.escapeHtml(`/workflows/${w.id}`)}" style="text-decoration: none;">
                            <code style="font-family: var(--font-mono); font-weight: 600; color: var(--color-primary);">${utils.escapeHtml(w.id.slice(0, 8))}…</code>
                        </a>
                    </td>
                    <td>
                        <div style="font-weight: 600;">${utils.escapeHtml(w.workflow_type)}</div>
                    </td>
                    <td>
                        <span class="${statusClass}">
                            <span class="status-pulse-dot" style="background: currentColor;"></span>
                            ${utils.escapeHtml(w.status)}
                        </span>
                    </td>
                    <td>
                        <div style="display: flex; align-items: center; gap: var(--spacing-xs);">
                            ${sourceSnippet}
                            <span style="font-size: var(--font-size-xs); font-family: var(--font-mono); color: var(--color-text-secondary); max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${eventSnippet}">
                                ${eventSnippet}
                            </span>
                        </div>
                    </td>
                    <td style="color: var(--color-text-secondary); font-size: var(--font-size-sm);">${utils.formatRelativeTime(w.created_at)}</td>
                    <td style="text-align: right;">
                        <a href="${utils.escapeHtml(`/workflows/${w.id}`)}" class="btn btn-sm btn-secondary">
                            View Execution
                        </a>
                    </td>
                </tr>
            `;
        }).join('');

        renderPagination(data);
    }

    function renderPagination(data) {
        if (!dom.pagination) return;

        const { page, total_pages } = data;
        if (total_pages <= 1) {
            dom.pagination.innerHTML = '';
            return;
        }

        let html = '<div style="display: flex; gap: var(--spacing-xs); align-items: center;">';

        if (page > 1) {
            html += `<a href="?page=${page - 1}" class="pagination-link btn btn-sm btn-secondary" aria-label="Previous page">&laquo; Prev</a>`;
        }

        let start = Math.max(1, page - 2);
        let end = Math.min(total_pages, start + 4);
        if (end - start < 4) start = Math.max(1, end - 4);

        if (start > 1) {
            html += `<a href="?page=1" class="pagination-link btn btn-sm btn-secondary">1</a>`;
            if (start > 2) html += `<span style="padding: 0 4px; color: var(--color-text-muted);">…</span>`;
        }

        for (let i = start; i <= end; i++) {
            if (i === page) {
                html += `<span class="btn btn-sm btn-primary" aria-current="page">${i}</span>`;
            } else {
                html += `<a href="?page=${i}" class="pagination-link btn btn-sm btn-secondary">${i}</a>`;
            }
        }

        if (end < total_pages) {
            if (end < total_pages - 1) html += `<span style="padding: 0 4px; color: var(--color-text-muted);">…</span>`;
            html += `<a href="?page=${total_pages}" class="pagination-link btn btn-sm btn-secondary">${total_pages}</a>`;
        }

        if (page < total_pages) {
            html += `<a href="?page=${page + 1}" class="pagination-link btn btn-sm btn-secondary" aria-label="Next page">Next &raquo;</a>`;
        }

        html += '</div>';
        dom.pagination.innerHTML = html;
    }

    // Pipeline DAG Visualizer
    function renderPipelineTrack(workflow) {
        if (!dom.wfPipelineTrack) return;

        const canonicalSteps = [
            { name: 'validate_request', label: 'Validate Schema' },
            { name: 'check_order', label: 'Check Order' },
            { name: 'check_customer', label: 'Check Customer' },
            { name: 'update_order', label: 'Update Order' },
            { name: 'notify_customer', label: 'Notify Customer' }
        ];

        const recordedSteps = workflow.steps || [];
        const wfStatus = (workflow.status || '').toLowerCase();

        // Map step statuses
        let html = '';
        canonicalSteps.forEach((cStep, idx) => {
            const recorded = recordedSteps.find(s => s.step_name === cStep.name);
            let stepStatus = 'pending';
            let durationText = '';

            if (recorded) {
                stepStatus = recorded.status.toLowerCase();
                if (recorded.duration_ms != null) {
                    durationText = `${recorded.duration_ms}ms`;
                }
            } else if (wfStatus === 'completed') {
                stepStatus = 'completed';
            } else if (wfStatus === 'running' && idx === 0) {
                stepStatus = 'running';
            }

            let iconHtml = '';
            if (stepStatus === 'completed') {
                iconHtml = `
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <polyline points="20 6 9 17 4 12"/>
                    </svg>
                `;
            } else if (stepStatus === 'failed') {
                iconHtml = `
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
                        <line x1="18" y1="6" x2="6" y2="18"/>
                        <line x1="6" y1="6" x2="18" y2="18"/>
                    </svg>
                `;
            } else if (stepStatus === 'running') {
                iconHtml = `<span class="spinner" style="width: 16px; height: 16px; border-width: 2px;"></span>`;
            } else {
                iconHtml = `<span style="font-size: 11px; font-weight: 700;">${idx + 1}</span>`;
            }

            html += `
                <div class="pipeline-step ${stepStatus}">
                    <div class="pipeline-node">
                        ${iconHtml}
                    </div>
                    <div class="pipeline-label">${utils.escapeHtml(cStep.label)}</div>
                    <div class="pipeline-sublabel">${durationText || utils.escapeHtml(stepStatus)}</div>
                </div>
            `;
        });

        dom.wfPipelineTrack.innerHTML = html;
    }

    // Workflow Detail Rendering
    function renderWorkflowDetail(workflow) {
        if (!dom.workflowDetail) return;

        if (!workflow) {
            dom.workflowDetail.hidden = true;
            dom.workflowDetail.style.display = 'none';
            if (dom.workflowNotFound) {
                dom.workflowNotFound.hidden = false;
                dom.workflowNotFound.style.display = 'flex';
            }
            return;
        }

        dom.workflowDetail.hidden = false;
        dom.workflowDetail.style.display = '';
        if (dom.workflowNotFound) {
            dom.workflowNotFound.hidden = true;
            dom.workflowNotFound.style.display = 'none';
        }

        // Breadcrumb ID
        if (dom.wfBreadcrumbId) dom.wfBreadcrumbId.textContent = workflow.id;

        // Header and Summary Badges
        const statusBadgeHtml = `
            <span class="status-pulse-dot" style="background: currentColor;"></span>
            ${utils.escapeHtml(workflow.status)}
        `;
        if (dom.wfHeaderStatus) {
            dom.wfHeaderStatus.innerHTML = statusBadgeHtml;
            dom.wfHeaderStatus.className = `badge badge-${workflow.status}`;
        }
        if (dom.wfSummaryStatus) {
            dom.wfSummaryStatus.innerHTML = statusBadgeHtml;
            dom.wfSummaryStatus.className = `badge badge-${workflow.status}`;
        }

        // Render Interactive Pipeline Track
        renderPipelineTrack(workflow);

        // Core Metadata
        if (dom.wfId) dom.wfId.textContent = workflow.id;
        if (dom.wfType) dom.wfType.textContent = workflow.workflow_type;
        if (dom.wfSourceSystem) dom.wfSourceSystem.textContent = workflow.source_system || '—';
        if (dom.wfExternalEventId) dom.wfExternalEventId.textContent = workflow.external_event_id || '—';

        if (dom.wfStarted) dom.wfStarted.textContent = utils.formatDate(workflow.started_at);
        if (dom.wfCreated) dom.wfCreated.textContent = utils.formatDate(workflow.created_at);
        if (dom.wfCompleted) dom.wfCompleted.textContent = workflow.completed_at ? utils.formatDate(workflow.completed_at) : '—';
        if (dom.wfDuration) dom.wfDuration.textContent = workflow.duration_ms != null ? `${workflow.duration_ms}ms` : '—';

        // Business Fields
        const orig = workflow.original_request || {};
        const res = workflow.result || {};
        if (dom.wfOrderId) dom.wfOrderId.textContent = workflow.order_id || orig.order_id || '—';
        if (dom.wfCustomerId) dom.wfCustomerId.textContent = workflow.customer_id || orig.customer_id || '—';
        if (dom.wfPrevDelivery) dom.wfPrevDelivery.textContent = res.previous_delivery_date ? utils.formatDate(res.previous_delivery_date) : '—';
        if (dom.wfNewDelivery) dom.wfNewDelivery.textContent = res.new_delivery_date ? utils.formatDate(res.new_delivery_date) : (orig.requested_delivery_date ? utils.formatDate(orig.requested_delivery_date) : '—');
        if (dom.wfOrderStatus) dom.wfOrderStatus.textContent = res.order_status || '—';

        if (dom.wfCorrelation) dom.wfCorrelation.textContent = workflow.correlation_id || '—';
        if (dom.wfIdempotencyKey) dom.wfIdempotencyKey.textContent = workflow.idempotency_key || '—';
        if (dom.wfFailureCategory) dom.wfFailureCategory.textContent = workflow.failure_category || '—';

        // Steps Timeline Table
        if (dom.wfStepsTbody) {
            const steps = workflow.steps || [];
            if (steps.length === 0) {
                dom.wfStepsTbody.innerHTML = '';
                if (dom.wfStepsEmpty) {
                    dom.wfStepsEmpty.hidden = false;
                    dom.wfStepsEmpty.style.display = 'block';
                }
            } else {
                if (dom.wfStepsEmpty) {
                    dom.wfStepsEmpty.hidden = true;
                    dom.wfStepsEmpty.style.display = 'none';
                }
                dom.wfStepsTbody.innerHTML = steps.map(s => `
                    <tr>
                        <td><strong style="color: var(--color-primary);">${utils.escapeHtml(s.step_name)}</strong></td>
                        <td><code style="font-family: var(--font-mono);">#${s.attempt_number}</code></td>
                        <td>
                            <span class="badge badge-${s.status}">
                                <span class="status-pulse-dot" style="background: currentColor;"></span>
                                ${utils.escapeHtml(s.status)}
                            </span>
                        </td>
                        <td style="color: var(--color-text-secondary);">${utils.formatDate(s.started_at)}</td>
                        <td><code style="font-family: var(--font-mono);">${s.duration_ms != null ? `${s.duration_ms}ms` : '—'}</code></td>
                        <td>
                            ${s.error_category ? `<span style="color: var(--color-error); font-weight: 600;">[${utils.escapeHtml(s.error_category)}]</span> ` : ''}
                            ${s.metadata ? `<code style="font-size: 0.8rem; background: var(--color-surface); padding: 2px 6px; border-radius: 4px;">${utils.escapeHtml(JSON.stringify(s.metadata))}</code>` : (s.error_details ? `<code style="font-size: 0.8rem; background: var(--color-surface); padding: 2px 6px; border-radius: 4px;">${utils.escapeHtml(JSON.stringify(s.error_details))}</code>` : '—')}
                        </td>
                    </tr>
                `).join('');
            }
        }

        // LLM Telemetry
        if (dom.wfLlmTbody) {
            const llmCalls = workflow.llm_invocations || [];
            if (llmCalls.length === 0) {
                dom.wfLlmTbody.innerHTML = '';
                if (dom.wfLlmEmpty) {
                    dom.wfLlmEmpty.hidden = false;
                    dom.wfLlmEmpty.style.display = 'block';
                }
            } else {
                if (dom.wfLlmEmpty) {
                    dom.wfLlmEmpty.hidden = true;
                    dom.wfLlmEmpty.style.display = 'none';
                }
                dom.wfLlmTbody.innerHTML = llmCalls.map(inv => `
                    <tr>
                        <td>
                            <strong>${utils.escapeHtml(inv.provider)}</strong>
                            <code style="display: block; font-size: 0.75rem; color: var(--color-text-muted);">${utils.escapeHtml(inv.model)}</code>
                        </td>
                        <td>
                            <span class="badge badge-${inv.status}">
                                <span class="status-pulse-dot" style="background: currentColor;"></span>
                                ${utils.escapeHtml(inv.status)}
                            </span>
                        </td>
                        <td><code>${inv.latency_ms != null ? `${inv.latency_ms}ms` : '—'}</code></td>
                        <td>${inv.prompt_tokens != null ? utils.formatNumber(inv.prompt_tokens) : '—'}</td>
                        <td>${inv.completion_tokens != null ? utils.formatNumber(inv.completion_tokens) : '—'}</td>
                        <td><strong>${inv.total_tokens != null ? utils.formatNumber(inv.total_tokens) : '—'}</strong></td>
                        <td style="color: var(--color-primary); font-weight: 600;">${inv.estimated_cost_usd != null ? `$${inv.estimated_cost_usd.toFixed(4)}` : '—'}</td>
                    </tr>
                `).join('');
            }
        }

        // JSON Code Blocks
        if (dom.wfJsonOriginal) dom.wfJsonOriginal.textContent = JSON.stringify(workflow.original_request || {}, null, 2);
        if (dom.wfJsonInterpreted) dom.wfJsonInterpreted.textContent = workflow.interpreted_request ? JSON.stringify(workflow.interpreted_request, null, 2) : '—';
        if (dom.wfJsonResult) dom.wfJsonResult.textContent = workflow.result ? JSON.stringify(workflow.result, null, 2) : '—';
        if (dom.wfJsonError) dom.wfJsonError.textContent = workflow.error_details ? JSON.stringify(workflow.error_details, null, 2) : '—';
    }

    // NL Request Form Handling
    function initNlForm() {
        if (!dom.nlForm) return;

        if (dom.nlExternalEventId && !dom.nlExternalEventId.value) {
            dom.nlExternalEventId.value = utils.generateExternalEventId();
        }

        dom.nlForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            setFormLoading(true);
            hideNlMessages();

            const request = {
                text: dom.nlText.value.trim(),
                source_system: dom.nlSourceSystem.value.trim() || 'web',
                external_event_id: dom.nlExternalEventId.value.trim() || utils.generateExternalEventId(),
                customer_id: dom.nlCustomerId.value.trim() || undefined,
            };

            if (!request.text) {
                showNlError('Please enter a natural language request.');
                setFormLoading(false);
                return;
            }

            if (!request.external_event_id) {
                showNlError('Please provide an external event ID.');
                setFormLoading(false);
                return;
            }

            try {
                const response = await api.createNaturalLanguageRequest(request);

                if (response.success) {
                    showNlSuccess(response);
                    dom.nlExternalEventId.value = utils.generateExternalEventId();
                } else {
                    showNlError(response.error || 'Interpretation failed', response.error_code);
                }
            } catch (error) {
                if (error instanceof ApiError) {
                    const detail = error.data?.detail || error.data;
                    const message = detail?.error || detail?.message || error.message;
                    const code = detail?.error_code;
                    showNlError(message, code);
                } else {
                    showNlError(error.message || 'An unexpected error occurred');
                }
            } finally {
                setFormLoading(false);
            }
        });
    }

    function setFormLoading(loading) {
        if (dom.nlSubmitBtn) {
            dom.nlSubmitBtn.disabled = loading;
            dom.nlSubmitBtn.innerHTML = loading
                ? '<span class="spinner" aria-hidden="true" style="margin-right: 6px;"></span> Interpreting Request…'
                : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true" style="margin-right: var(--spacing-xs);"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> Interpret & Dispatch Request';
        }
        if (dom.nlLoading) {
            dom.nlLoading.hidden = !loading;
            dom.nlLoading.style.display = loading ? 'block' : 'none';
        }
        if (dom.nlText) dom.nlText.disabled = loading;
        if (dom.nlSourceSystem) dom.nlSourceSystem.disabled = loading;
        if (dom.nlExternalEventId) dom.nlExternalEventId.disabled = loading;
        if (dom.nlCustomerId) dom.nlCustomerId.disabled = loading;
    }

    function showNlError(message, code) {
        if (dom.nlError) {
            dom.nlError.hidden = false;
            dom.nlError.style.display = 'block';
            if (dom.nlErrorCode) dom.nlErrorCode.textContent = code || 'ERROR';
            if (dom.nlErrorMessage) dom.nlErrorMessage.textContent = message;
        }
        if (dom.nlSuccess) {
            dom.nlSuccess.hidden = true;
            dom.nlSuccess.style.display = 'none';
        }
        if (dom.nlResult) {
            dom.nlResult.hidden = true;
            dom.nlResult.style.display = 'none';
        }
    }

    function showNlSuccess(response) {
        if (dom.nlSuccess) {
            dom.nlSuccess.hidden = false;
            dom.nlSuccess.style.display = 'block';
        }
        if (dom.nlResult) {
            dom.nlResult.hidden = false;
            dom.nlResult.style.display = 'block';
        }
        if (dom.nlError) {
            dom.nlError.hidden = true;
            dom.nlError.style.display = 'none';
        }

        if (dom.nlDraftOrderId) dom.nlDraftOrderId.textContent = response.draft?.order_id || '—';
        if (dom.nlDraftCustomerId) dom.nlDraftCustomerId.textContent = response.draft?.customer_id || '—';
        if (dom.nlDraftDeliveryDate) {
            dom.nlDraftDeliveryDate.textContent = response.draft?.requested_delivery_date
                ? utils.formatDate(response.draft.requested_delivery_date)
                : '—';
        }

        if (dom.nlWorkflowLink) {
            dom.nlWorkflowLink.href = '/workflows';
        }
    }

    function hideNlMessages() {
        if (dom.nlError) {
            dom.nlError.hidden = true;
            dom.nlError.style.display = 'none';
        }
        if (dom.nlSuccess) {
            dom.nlSuccess.hidden = true;
            dom.nlSuccess.style.display = 'none';
        }
        if (dom.nlResult) {
            dom.nlResult.hidden = true;
            dom.nlResult.style.display = 'none';
        }
    }

    // Load Data Functions
    async function loadDashboard() {
        try {
            const data = await api.getMetrics();
            renderDashboard(data);
        } catch (error) {
            console.error('Failed to load dashboard:', error);
            utils.showToast('Failed to load dashboard telemetry');
        }
    }

    async function loadWorkflows(page = 1) {
        if (!dom.workflowsTableBody) return;

        state.workflows.loading = true;
        state.workflows.page = page;

        dom.workflowsTableBody.innerHTML = `
            <tr>
                <td colspan="6" class="loading" style="padding: var(--spacing-xl); text-align: center;">
                    <span class="spinner" aria-hidden="true"></span> Loading executions…
                </td>
            </tr>
        `;

        try {
            const data = await api.getWorkflows(page, state.workflows.pageSize);
            state.workflows.items = data.items || [];
            state.workflows.total = data.total || 0;
            state.workflows.totalPages = data.total_pages || 0;
            state.workflows.page = data.page || 1;

            renderWorkflows(data);
        } catch (error) {
            console.error('Failed to load workflows:', error);
            if (dom.workflowsTableBody) {
                dom.workflowsTableBody.innerHTML = `
                    <tr>
                        <td colspan="6" style="text-align: center; color: var(--color-error); padding: var(--spacing-xl);">
                            Failed to load workflows. <button class="btn btn-secondary btn-sm" onclick="loadWorkflows(${page})">Retry</button>
                        </td>
                    </tr>
                `;
            }
            utils.showToast('Failed to load workflow history');
        } finally {
            state.workflows.loading = false;
        }
    }

    async function loadWorkflowDetail(id) {
        if (!dom.workflowDetail) return;

        dom.workflowDetail.hidden = true;
        dom.workflowDetail.style.display = 'none';
        if (dom.workflowNotFound) {
            dom.workflowNotFound.hidden = true;
            dom.workflowNotFound.style.display = 'none';
        }

        const loadingEl = document.createElement('div');
        loadingEl.className = 'loading';
        loadingEl.style.padding = 'var(--spacing-2xl)';
        loadingEl.style.textAlign = 'center';
        loadingEl.innerHTML = '<span class="spinner" aria-hidden="true"></span> Loading execution audit trail…';
        dom.workflowDetail.parentNode.insertBefore(loadingEl, dom.workflowDetail.nextSibling);

        try {
            const workflow = await api.getWorkflow(id);
            if (loadingEl.parentNode) loadingEl.remove();
            renderWorkflowDetail(workflow);
        } catch (error) {
            if (loadingEl.parentNode) loadingEl.remove();
            if (error instanceof ApiError && error.status === 404) {
                if (dom.workflowDetail) {
                    dom.workflowDetail.hidden = true;
                    dom.workflowDetail.style.display = 'none';
                }
                if (dom.workflowNotFound) {
                    dom.workflowNotFound.hidden = false;
                    dom.workflowNotFound.style.display = 'flex';
                }
            } else {
                utils.showToast('Failed to load workflow details');
            }
        }
    }

    // Filter and Search Handlers
    function setupHistoryFilters() {
        if (dom.statusFilters) {
            dom.statusFilters.addEventListener('click', (e) => {
                const btn = e.target.closest('.filter-pill');
                if (!btn) return;

                dom.statusFilters.querySelectorAll('.filter-pill').forEach(b => {
                    b.className = 'btn btn-sm btn-secondary filter-pill';
                });
                btn.className = 'btn btn-sm btn-primary filter-pill active';

                state.workflows.filterStatus = btn.dataset.status || 'all';
                renderWorkflows({
                    items: state.workflows.items,
                    total: state.workflows.total,
                    page: state.workflows.page,
                    total_pages: state.workflows.totalPages,
                });
            });
        }

        if (dom.workflowSearchInput) {
            dom.workflowSearchInput.addEventListener('input', utils.debounce((e) => {
                state.workflows.searchQuery = e.target.value.trim();
                renderWorkflows({
                    items: state.workflows.items,
                    total: state.workflows.total,
                    page: state.workflows.page,
                    total_pages: state.workflows.totalPages,
                });
            }, 200));
        }
    }

    // Page Initialization
    function init() {
        theme.init();
        cacheDomElements();
        checkSystemHealth();
        setupHistoryFilters();

        const path = window.location.pathname;

        if (path === '/' || path === '/dashboard') {
            loadDashboard();
        } else if (path === '/workflows' || path.startsWith('/workflows?')) {
            const urlParams = new URLSearchParams(window.location.search);
            const page = parseInt(urlParams.get('page') || '1', 10);
            loadWorkflows(page);
        } else if (path.startsWith('/workflows/') && path !== '/workflows' && path !== '/request') {
            const id = path.split('/workflows/')[1];
            if (id && !id.includes('?')) {
                loadWorkflowDetail(id);
            }
        } else if (path === '/request') {
            initNlForm();
        }

        // Event delegation for pagination links
        document.addEventListener('click', (e) => {
            const link = e.target.closest('.pagination-link');
            if (link && link.href) {
                e.preventDefault();
                const url = new URL(link.href);
                const page = parseInt(url.searchParams.get('page') || '1', 10);
                loadWorkflows(page);
                history.pushState({}, '', `?page=${page}`);
            }
        });

        // Regenerate external event ID button
        const regenBtn = document.getElementById('regen-event-id');
        if (regenBtn) {
            regenBtn.addEventListener('click', () => {
                if (dom.nlExternalEventId) {
                    dom.nlExternalEventId.value = utils.generateExternalEventId();
                }
            });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Global exports
    window.loadWorkflows = loadWorkflows;
    window.loadWorkflowDetail = loadWorkflowDetail;
    window.loadDashboard = loadDashboard;
    window.utils = utils;
    window.api = api;
    window.theme = theme;
})();