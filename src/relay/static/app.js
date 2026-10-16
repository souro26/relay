/**
 * Relay - Business Workflow Integration
 * Frontend JavaScript for the demo application
 */

(function() {
    'use strict';

    // Utility Functions
    const utils = {
        /**
         * Escape HTML to prevent XSS
         */
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        },

        /**
         * Format date for display
         */
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
                });
            } catch {
                return dateString;
            }
        },

        /**
         * Format relative time
         */
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

                if (diffSecs < 60) return 'just now';
                if (diffMins < 60) return `${diffMins}m ago`;
                if (diffHours < 24) return `${diffHours}h ago`;
                if (diffDays < 7) return `${diffDays}d ago`;
                return this.formatDate(dateString);
            } catch {
                return dateString;
            }
        },

        /**
         * Generate a UUID v4
         */
        generateUuid() {
            return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
                const r = Math.random() * 16 | 0;
                const v = c === 'x' ? r : (r & 0x3 | 0x8);
                return v.toString(16);
            });
        },

        /**
         * Generate external event ID
         */
        generateExternalEventId() {
            return `evt-${Date.now()}-${Math.random().toString(36).substring(2, 10)}`;
        },

        /**
         * Debounce function
         */
        debounce(fn, delay) {
            let timeoutId;
            return (...args) => {
                clearTimeout(timeoutId);
                timeoutId = setTimeout(() => fn.apply(this, args), delay);
            };
        },

        /**
         * Show toast notification
         */
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

        /**
         * Format number with commas
         */
        formatNumber(num) {
            return new Intl.NumberFormat().format(num);
        },

        /**
         * Calculate success rate
         */
        calculateSuccessRate(completed, failed) {
            const total = completed + failed;
            if (total === 0) return '—';
            return `${((completed / total) * 100).toFixed(1)}%`;
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

        // Metrics
        async getMetrics() {
            return this.request('/metrics');
        },

        // Workflows
        async getWorkflows(page = 1, pageSize = 20) {
            return this.request(`/workflows?page=${page}&page_size=${pageSize}`);
        },

        async getWorkflow(id) {
            return this.request(`/workflows/${id}`);
        },

        // Order Changes
        async createOrderChange(request) {
            return this.request('/order-change-requests', {
                method: 'POST',
                body: request,
            });
        },

        // Natural Language
        async createNaturalLanguageRequest(request) {
            return this.request('/order-change-requests/nl', {
                method: 'POST',
                body: request,
            });
        },
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
        },
        nlRequest: {
            loading: false,
            error: null,
            success: false,
        },
    };

    // DOM Elements Cache
    const dom = {};

    // Initialize DOM cache
    function cacheDomElements() {
        // Dashboard Summary
        dom.totalWorkflows = document.getElementById('total-workflows');
        dom.completedWorkflows = document.getElementById('completed-workflows');
        dom.failedWorkflows = document.getElementById('failed-workflows');
        dom.successRate = document.getElementById('success-rate');
        dom.recentWorkflows = document.getElementById('recent-workflows');
        dom.recentWorkflowsEmpty = document.getElementById('recent-workflows-empty');

        // Dashboard Operational Telemetry
        dom.medianDuration = document.getElementById('median-duration');
        dom.p95Duration = document.getElementById('p95-duration');
        dom.totalTokens = document.getElementById('total-tokens');
        dom.estimatedSpending = document.getElementById('estimated-spending');

        // Workflow History
        dom.workflowsTableBody = document.getElementById('workflows-table-body');
        dom.workflowsEmpty = document.getElementById('workflows-empty');
        dom.pagination = document.getElementById('pagination');

        // Workflow Details
        dom.workflowDetail = document.getElementById('workflow-detail');
        dom.workflowNotFound = document.getElementById('workflow-not-found');
        dom.wfHeaderStatus = document.getElementById('wf-header-status');
        dom.wfSummaryStatus = document.getElementById('wf-summary-status');
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
        dom.wfOriginalRequest = document.getElementById('wf-original-request');
        dom.wfInterpretedRequest = document.getElementById('wf-interpreted-request');
        dom.wfResult = document.getElementById('wf-result');
        dom.wfError = document.getElementById('wf-error');

        // NL Request Form
        dom.nlForm = document.getElementById('nl-request-form');
        dom.nlText = document.getElementById('nl-text');
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

        // Recent workflows
        if (dom.recentWorkflows) {
            const workflows = data.recent_workflows || [];
            if (workflows.length === 0) {
                if (dom.recentWorkflowsEmpty) dom.recentWorkflowsEmpty.hidden = false;
                dom.recentWorkflows.innerHTML = '';
            } else {
                if (dom.recentWorkflowsEmpty) dom.recentWorkflowsEmpty.hidden = true;
                dom.recentWorkflows.innerHTML = workflows.map(w => `
                    <tr>
                        <td><code>${utils.escapeHtml(w.id.slice(0, 8))}…</code></td>
                        <td>${utils.escapeHtml(w.workflow_type)}</td>
                        <td><span class="badge badge-${w.status}">${utils.escapeHtml(w.status)}</span></td>
                        <td>${utils.formatRelativeTime(w.created_at)}</td>
                        <td>
                            <a href="${utils.escapeHtml(`/workflows/${w.id}`)}" class="btn btn-sm btn-secondary">View</a>
                        </td>
                    </tr>
                `).join('');
            }
        }
    }

    // Workflow History Rendering
    function renderWorkflows(data) {
        if (!dom.workflowsTableBody) return;

        const workflows = data.items || [];
        if (workflows.length === 0) {
            if (dom.workflowsEmpty) dom.workflowsEmpty.hidden = false;
            dom.workflowsTableBody.innerHTML = '';
            return;
        }

        if (dom.workflowsEmpty) dom.workflowsEmpty.hidden = true;
        dom.workflowsTableBody.innerHTML = workflows.map(w => `
            <tr>
                <td><code>${utils.escapeHtml(w.id.slice(0, 8))}…</code></td>
                <td>${utils.escapeHtml(w.workflow_type)}</td>
                <td><span class="badge badge-${w.status}">${utils.escapeHtml(w.status)}</span></td>
                <td>${utils.formatRelativeTime(w.created_at)}</td>
                <td>
                    <a href="${utils.escapeHtml(`/workflows/${w.id}`)}" class="btn btn-sm btn-secondary">View</a>
                </td>
            </tr>
        `).join('');

        // Render pagination
        renderPagination(data);
    }

    function renderPagination(data) {
        if (!dom.pagination) return;

        const { page, total_pages } = data;
        if (total_pages <= 1) {
            dom.pagination.innerHTML = '';
            return;
        }

        let html = '';

        // Previous
        if (page > 1) {
            html += `<a href="?page=${page - 1}" class="pagination-link" aria-label="Previous page">&laquo;</a>`;
        }

        // Page numbers
        let start = Math.max(1, page - 2);
        let end = Math.min(total_pages, start + 4);
        if (end - start < 4) start = Math.max(1, end - 4);

        if (start > 1) {
            html += `<a href="?page=1" class="pagination-link">1</a>`;
            if (start > 2) html += `<span class="pagination-ellipsis" aria-hidden="true">…</span>`;
        }

        for (let i = start; i <= end; i++) {
            if (i === page) {
                html += `<span class="pagination-current" aria-current="page">${i}</span>`;
            } else {
                html += `<a href="?page=${i}" class="pagination-link">${i}</a>`;
            }
        }

        if (end < total_pages) {
            if (end < total_pages - 1) html += `<span class="pagination-ellipsis" aria-hidden="true">…</span>`;
            html += `<a href="?page=${total_pages}" class="pagination-link">${total_pages}</a>`;
        }

        // Next
        if (page < total_pages) {
            html += `<a href="?page=${page + 1}" class="pagination-link" aria-label="Next page">&raquo;</a>`;
        }

        dom.pagination.innerHTML = html;
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

        // Header and Summary Badges
        if (dom.wfHeaderStatus) {
            dom.wfHeaderStatus.textContent = workflow.status;
            dom.wfHeaderStatus.className = `badge badge-${workflow.status}`;
        }
        if (dom.wfSummaryStatus) {
            dom.wfSummaryStatus.textContent = workflow.status;
            dom.wfSummaryStatus.className = `badge badge-${workflow.status}`;
        }

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

        // Steps Timeline
        if (dom.wfStepsTbody) {
            const steps = workflow.steps || [];
            if (steps.length === 0) {
                dom.wfStepsTbody.innerHTML = '';
                if (dom.wfStepsEmpty) dom.wfStepsEmpty.hidden = false;
            } else {
                if (dom.wfStepsEmpty) dom.wfStepsEmpty.hidden = true;
                dom.wfStepsTbody.innerHTML = steps.map(s => `
                    <tr>
                        <td><strong>${utils.escapeHtml(s.step_name)}</strong></td>
                        <td>#${s.attempt_number}</td>
                        <td><span class="badge badge-${s.status}">${utils.escapeHtml(s.status)}</span></td>
                        <td>${utils.formatDate(s.started_at)}</td>
                        <td>${s.duration_ms != null ? `${s.duration_ms}ms` : '—'}</td>
                        <td>
                            ${s.error_category ? `<span style="color: var(--color-error); font-weight: 600;">[${utils.escapeHtml(s.error_category)}]</span> ` : ''}
                            ${s.metadata ? `<code>${utils.escapeHtml(JSON.stringify(s.metadata))}</code>` : (s.error_details ? `<code>${utils.escapeHtml(JSON.stringify(s.error_details))}</code>` : '—')}
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
                if (dom.wfLlmEmpty) dom.wfLlmEmpty.hidden = false;
            } else {
                if (dom.wfLlmEmpty) dom.wfLlmEmpty.hidden = true;
                dom.wfLlmTbody.innerHTML = llmCalls.map(inv => `
                    <tr>
                        <td><strong>${utils.escapeHtml(inv.provider)}</strong> / <code>${utils.escapeHtml(inv.model)}</code></td>
                        <td><span class="badge badge-${inv.status}">${utils.escapeHtml(inv.status)}</span></td>
                        <td>${inv.latency_ms != null ? `${inv.latency_ms}ms` : '—'}</td>
                        <td>${inv.prompt_tokens != null ? utils.formatNumber(inv.prompt_tokens) : '—'}</td>
                        <td>${inv.completion_tokens != null ? utils.formatNumber(inv.completion_tokens) : '—'}</td>
                        <td>${inv.total_tokens != null ? utils.formatNumber(inv.total_tokens) : '—'}</td>
                        <td>${inv.estimated_cost_usd != null ? `$${inv.estimated_cost_usd.toFixed(4)}` : '—'}</td>
                    </tr>
                `).join('');
            }
        }

        // Original Request
        if (dom.wfOriginalRequest) dom.wfOriginalRequest.textContent = JSON.stringify(workflow.original_request, null, 2);

        // Interpreted Request
        if (dom.wfInterpretedRequest) {
            dom.wfInterpretedRequest.textContent = workflow.interpreted_request ? JSON.stringify(workflow.interpreted_request, null, 2) : '—';
        }

        // Result
        if (dom.wfResult) {
            if (workflow.result) {
                dom.wfResult.innerHTML = '';
                Object.entries(workflow.result).forEach(([key, value]) => {
                    const row = document.createElement('div');
                    row.className = 'detail-row';
                    row.innerHTML = `
                        <span class="detail-label">${utils.escapeHtml(key)}</span>
                        <span class="detail-value">${utils.escapeHtml(String(value))}</span>
                    `;
                    dom.wfResult.appendChild(row);
                });
            } else {
                dom.wfResult.textContent = '—';
            }
        }

        // Error Diagnostics
        if (dom.wfError) {
            dom.wfError.textContent = workflow.error_details ? JSON.stringify(workflow.error_details, null, 2) : '—';
        }
    }

    // NL Request Form Handling
    function initNlForm() {
        if (!dom.nlForm) return;

        // Set default external_event_id
        if (dom.nlExternalEventId) {
            dom.nlExternalEventId.value = utils.generateExternalEventId();
        }

        dom.nlForm.addEventListener('submit', async (e) => {
            e.preventDefault();

            // Clear previous states
            setFormLoading(true);
            hideNlMessages();

            const request = {
                text: dom.nlText.value.trim(),
                source_system: dom.nlSourceSystem.value.trim() || 'web',
                external_event_id: dom.nlExternalEventId.value.trim() || utils.generateExternalEventId(),
                customer_id: dom.nlCustomerId.value.trim() || undefined,
            };

            // Validate required fields
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
                    // Generate new external_event_id for next submission
                    dom.nlExternalEventId.value = utils.generateExternalEventId();
                } else {
                    showNlError(response.error || 'Interpretation failed', response.error_code);
                }
            } catch (error) {
                if (error instanceof ApiError) {
                    const detail = error.data?.detail || error.data;
                    const message = detail?.error || detail?.message || error.message;
                    const code = detail?.error_code || detail?.error_code;
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
                ? '<span class="spinner" aria-hidden="true"></span> Processing…'
                : 'Submit Request';
        }
        if (dom.nlLoading) dom.nlLoading.hidden = !loading;
        if (dom.nlText) dom.nlText.disabled = loading;
        if (dom.nlSourceSystem) dom.nlSourceSystem.disabled = loading;
        if (dom.nlExternalEventId) dom.nlExternalEventId.disabled = loading;
        if (dom.nlCustomerId) dom.nlCustomerId.disabled = loading;
    }

    function showNlError(message, code) {
        if (dom.nlError) {
            dom.nlError.hidden = false;
            if (dom.nlErrorCode) dom.nlErrorCode.textContent = code || 'ERROR';
            if (dom.nlErrorMessage) dom.nlErrorMessage.textContent = message;
        }
        if (dom.nlSuccess) dom.nlSuccess.hidden = true;
        if (dom.nlResult) dom.nlResult.hidden = true;
    }

    function showNlSuccess(response) {
        if (dom.nlSuccess) dom.nlSuccess.hidden = false;
        if (dom.nlResult) dom.nlResult.hidden = false;
        if (dom.nlError) dom.nlError.hidden = true;

        if (dom.nlDraftOrderId) dom.nlDraftOrderId.textContent = response.draft?.order_id || '—';
        if (dom.nlDraftCustomerId) dom.nlDraftCustomerId.textContent = response.draft?.customer_id || '—';
        if (dom.nlDraftDeliveryDate) dom.nlDraftDeliveryDate.textContent = response.draft?.requested_delivery_date
            ? new Date(response.draft.requested_delivery_date).toLocaleString()
            : '—';

        if (dom.nlWorkflowLink && response.draft) {
            // We don't have workflow_id in the response, but we can link to workflows list
            dom.nlWorkflowLink.href = '/workflows';
        }
    }

    function hideNlMessages() {
        if (dom.nlError) dom.nlError.hidden = true;
        if (dom.nlSuccess) dom.nlSuccess.hidden = true;
        if (dom.nlResult) dom.nlResult.hidden = true;
    }

    // Load Data Functions
    async function loadDashboard() {
        try {
            const data = await api.getMetrics();
            renderDashboard(data);
        } catch (error) {
            console.error('Failed to load dashboard:', error);
            utils.showToast('Failed to load dashboard data');
        }
    }

    async function loadWorkflows(page = 1) {
        if (!dom.workflowsTableBody) return;

        state.workflows.loading = true;
        state.workflows.page = page;

        // Show loading
        dom.workflowsTableBody.innerHTML = '<tr><td colspan="5" class="loading"><span class="spinner" aria-hidden="true"></span> Loading workflows…</td></tr>';

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
                        <td colspan="5" style="text-align: center; color: var(--color-error); padding: var(--spacing-xl);">
                            Failed to load workflows. <button class="btn btn-secondary btn-sm" onclick="loadWorkflows(${page})">Retry</button>
                        </td>
                    </tr>
                `;
            }
            utils.showToast('Failed to load workflows');
        } finally {
            state.workflows.loading = false;
        }
    }

    async function loadWorkflowDetail(id) {
        if (!dom.workflowDetail) return;

        // Show loading
        dom.workflowDetail.hidden = true;
        dom.workflowDetail.style.display = 'none';
        if (dom.workflowNotFound) {
            dom.workflowNotFound.hidden = true;
            dom.workflowNotFound.style.display = 'none';
        }

        const loadingEl = document.createElement('div');
        loadingEl.className = 'loading';
        loadingEl.innerHTML = '<span class="spinner" aria-hidden="true"></span> Loading workflow…';
        if (dom.workflowDetail) {
            dom.workflowDetail.parentNode.insertBefore(loadingEl, dom.workflowDetail.nextSibling);
        }

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

    // Page Initialization
    function init() {
        cacheDomElements();

        // Detect current page and initialize accordingly
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

        // Generate new external_event_id on page load for NL form
        if (dom.nlExternalEventId && !dom.nlExternalEventId.value) {
            dom.nlExternalEventId.value = utils.generateExternalEventId();
        }

        // Add click handler for pagination links (delegated)
        document.addEventListener('click', (e) => {
            const link = e.target.closest('.pagination-link');
            if (link && link.href) {
                e.preventDefault();
                const url = new URL(link.href);
                const page = parseInt(url.searchParams.get('page') || '1', 10);
                loadWorkflows(page);
                // Update URL without reload
                history.pushState({}, '', `?page=${page}`);
            }
        });

        // Regenerate external_event_id button
        const regenBtn = document.getElementById('regen-event-id');
        if (regenBtn) {
            regenBtn.addEventListener('click', () => {
                if (dom.nlExternalEventId) {
                    dom.nlExternalEventId.value = utils.generateExternalEventId();
                }
            });
        }
    }

    // Initialize on DOM ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

    // Expose for global access (pagination, etc.)
    window.loadWorkflows = loadWorkflows;
    window.loadWorkflowDetail = loadWorkflowDetail;
    window.loadDashboard = loadDashboard;
    window.utils = utils;
    window.api = api;
})();