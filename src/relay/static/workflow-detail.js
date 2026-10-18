/**
 * Workflow Detail Page - Frontend Controller
 * Handles DAG visualization, tabbed JSON inspector, and workflow actions.
 */

(function() {
    'use strict';

    let activeWorkflowData = null;
    let jsonTabs = {
        input: '{\n  "status": "loading"\n}',
        resolved: '{\n  "status": "loading"\n}',
        telemetry: '{\n  "status": "loading\n}'
    };

    function switchTab(tabKey) {
        ['input', 'resolved', 'telemetry'].forEach(t => {
            const btn = document.getElementById('tab-' + t);
            if (!btn) return;
            if (t === tabKey) {
                btn.style.color = '#2C1D14';
                btn.style.fontWeight = '700';
                btn.style.borderBottom = '2px solid #C68B59';
            } else {
                btn.style.color = '#7A5A47';
                btn.style.fontWeight = 'normal';
                btn.style.borderBottom = '2px solid transparent';
            }
        });
        const viewer = document.getElementById('json-viewer');
        if (viewer) viewer.textContent = jsonTabs[tabKey];
    }

    function copyTraceId(id) {
        if (navigator.clipboard && navigator.clipboard.writeText) {
            navigator.clipboard.writeText(id).then(() => {
                const btn = document.getElementById('copy-uuid-btn');
                if (btn) {
                    btn.style.color = '#C68B59';
                    setTimeout(() => btn.style.color = '#7A5A47', 1000);
                }
            });
        }
    }

    function copyJsonPayload() {
        const viewer = document.getElementById('json-viewer');
        if (navigator.clipboard && navigator.clipboard.writeText && viewer) {
            navigator.clipboard.writeText(viewer.textContent).then(() => {
                const text = document.getElementById('copy-json-text');
                if (text) {
                    text.textContent = 'Copied!';
                    setTimeout(() => text.textContent = 'Copy JSON', 1200);
                }
            });
        }
    }

    function exportWorkflowJson() {
        const data = activeWorkflowData ? JSON.stringify(activeWorkflowData, null, 2) : 
            (document.getElementById('json-viewer')?.textContent || '{}');
        const blob = new Blob([data], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const executionId = document.body.dataset.executionId || 'unknown';
        a.download = `workflow-${executionId}.json`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        URL.revokeObjectURL(url);
    }

    async function triggerWorkflowRetry() {
        const btn = document.getElementById('btn-action-retry');
        const executionId = document.body.dataset.executionId;
        if (!executionId) return;
        
        if (!confirm('Re-execute this workflow with its original parameters?')) return;
        btn.disabled = true;
        btn.innerHTML = `<span class="material-symbols-outlined" style="font-size: 15px; animation: spin 1s linear infinite;">refresh</span> Retrying…`;

        try {
            const res = await fetch(`/api/v1/workflows/${executionId}/retry`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                alert(`Workflow successfully re-executed!\nNew Workflow ID: ${data.new_execution_id}`);
                window.location.href = `/workflows/${data.new_execution_id}`;
            } else {
                alert(`Retry failed: ${data.detail || 'Server error'}`);
            }
        } catch (e) {
            alert(`Retry request failed: ${e.message}`);
        } finally {
            btn.disabled = false;
            btn.innerHTML = `<span class="material-symbols-outlined" style="font-size: 15px; color: #B45309;">replay</span> Re-run Workflow`;
        }
    }

    async function triggerWorkflowCancel() {
        const btn = document.getElementById('btn-action-cancel');
        const executionId = document.body.dataset.executionId;
        if (!executionId) return;
        
        if (!confirm('Cancel this active workflow?')) return;
        btn.disabled = true;

        try {
            const res = await fetch(`/api/v1/workflows/${executionId}/cancel`, { method: 'POST' });
            const data = await res.json();
            if (res.ok) {
                alert('Workflow cancelled.');
                window.location.reload();
            } else {
                alert(`Cancel failed: ${data.detail || 'Server error'}`);
            }
        } catch (e) {
            alert(`Cancel failed: ${e.message}`);
        } finally {
            btn.disabled = false;
        }
    }

    window.selectDagStep = function(idx) {
        if (!activeWorkflowData || !activeWorkflowData.steps) return;
        const step = activeWorkflowData.steps[idx];
        if (!step) return;

        activeWorkflowData.steps.forEach((_, i) => {
            const box = document.getElementById(`dag-step-box-${i}`);
            if (box) {
                box.style.borderColor = (i === idx) ? '#C68B59' : '#E8DFD5';
                box.style.boxShadow = (i === idx) ? '0 0 0 2px #F8EDE2' : '0 1px 3px rgba(44,29,20,0.04)';
            }
        });

        jsonTabs.resolved = JSON.stringify(step, null, 2);
        switchTab('resolved');
        const heading = document.getElementById('tab-resolved');
        if (heading) {
            const textSpan = heading.querySelector('span:last-child');
            if (textSpan) textSpan.textContent = `Step: ${step.step_name}`;
        }
    };

    function initWorkflowDetail() {
        const executionId = document.body.dataset.executionId;
        if (!executionId) return;

        // Attach event listeners
        const copyUuidBtn = document.getElementById('copy-uuid-btn');
        if (copyUuidBtn) copyUuidBtn.addEventListener('click', () => copyTraceId(executionId));

        const exportBtn = document.querySelector('[onclick="exportWorkflowJson()"]');
        if (exportBtn) exportBtn.addEventListener('click', exportWorkflowJson);

        const retryBtn = document.getElementById('btn-action-retry');
        if (retryBtn) retryBtn.addEventListener('click', triggerWorkflowRetry);

        const cancelBtn = document.getElementById('btn-action-cancel');
        if (cancelBtn) cancelBtn.addEventListener('click', triggerWorkflowCancel);

        const copyJsonBtn = document.getElementById('copy-json-btn');
        if (copyJsonBtn) copyJsonBtn.addEventListener('click', copyJsonPayload);

        // Tab buttons
        document.getElementById('tab-input')?.addEventListener('click', () => switchTab('input'));
        document.getElementById('tab-resolved')?.addEventListener('click', () => switchTab('resolved'));
        document.getElementById('tab-telemetry')?.addEventListener('click', () => switchTab('telemetry'));

        // Fetch workflow data
        fetch(`/api/v1/workflows/${executionId}`)
            .then(res => res.ok ? res.json() : Promise.reject(new Error('Failed to fetch')))
            .then(wf => {
                activeWorkflowData = wf;
                populateWorkflowDetail(wf);
            })
            .catch(e => console.error('Error fetching workflow detail:', e));
    }

    function populateWorkflowDetail(wf) {
        if (wf.workflow_type) document.getElementById('workflow-headline-title').textContent = wf.workflow_type;
        if (wf.status) {
            const st = wf.status.toUpperCase();
            document.getElementById('workflow-status-text').textContent = st;
            const badge = document.getElementById('workflow-status-badge');
            if (st === 'COMPLETED') {
                badge.style.background = '#E6F4EA';
                badge.style.color = '#137333';
                badge.style.borderColor = '#CEEAD6';
            } else if (st === 'FAILED') {
                badge.style.background = '#FCE8E6';
                badge.style.color = '#C5221F';
                badge.style.borderColor = '#FAD2CF';
            } else if (st === 'RUNNING') {
                badge.style.background = '#E8F0FE';
                badge.style.color = '#1A73E8';
                badge.style.borderColor = '#D2E3FC';
            }
        }

        if (wf.source_system) document.getElementById('telemetry-trigger-source').textContent = wf.source_system;
        if (wf.started_at) document.getElementById('telemetry-started-at').textContent = new Date(wf.started_at).toLocaleString();
        if (wf.completed_at) document.getElementById('telemetry-completed-at').textContent = new Date(wf.completed_at).toLocaleString();
        if (wf.duration_ms != null) document.getElementById('telemetry-runtime-latency').textContent = `${Math.round(wf.duration_ms)}ms`;

        // Metadata cards
        if (wf.workflow_type) document.getElementById('meta-workflow-type').textContent = wf.workflow_type;
        if (wf.source_system) document.getElementById('meta-source-system').textContent = wf.source_system;
        if (wf.external_event_id) document.getElementById('meta-external-ref-id').textContent = wf.external_event_id;
        if (wf.correlation_id) document.getElementById('meta-correlation-id').textContent = wf.correlation_id;
        if (wf.idempotency_key) document.getElementById('meta-idempotency-key').textContent = wf.idempotency_key;
        if (wf.failure_category) document.getElementById('meta-failure-cat').textContent = wf.failure_category;

        const orig = wf.original_request || {};
        const result = wf.result || {};
        if (wf.order_id || orig.order_id) document.getElementById('meta-order-id').textContent = wf.order_id || orig.order_id;
        if (wf.customer_id || orig.customer_id) document.getElementById('meta-customer-id').textContent = wf.customer_id || orig.customer_id;
        if (orig.previous_delivery_date || result.previous_delivery_date) {
            document.getElementById('meta-original-delivery').textContent = orig.previous_delivery_date || result.previous_delivery_date;
        }
        if (result.new_delivery_date || orig.requested_delivery_date) {
            document.getElementById('meta-adjusted-delivery').textContent = result.new_delivery_date || orig.requested_delivery_date;
        }

        // LLM Telemetry
        const invocations = wf.llm_invocations || [];
        if (invocations.length > 0) {
            const inv = invocations[0];
            if (inv.model) document.getElementById('meta-llm-model').textContent = inv.model;
            if (inv.latency_ms != null) document.getElementById('meta-llm-latency').textContent = `${Math.round(inv.latency_ms)}ms`;
            if (inv.total_tokens != null) document.getElementById('meta-llm-tokens').textContent = `${inv.total_tokens} tokens`;
            if (inv.estimated_cost_usd != null) document.getElementById('meta-llm-cost').textContent = `$${inv.estimated_cost_usd.toFixed(5)} USD`;
        }

        // Steps table & DAG summary
        const steps = wf.steps || [];
        document.getElementById('execution-step-count-header').textContent = `(${steps.length} Operations)`;
        const compSteps = steps.filter(s => (s.status || '').toLowerCase() === 'completed').length;
        document.getElementById('dag-nodes-succeeded-pill').textContent = `${compSteps}/${steps.length || 5} Nodes Succeeded`;

        // Dynamically render actual execution DAG nodes
        if (steps.length > 0) {
            const track = document.getElementById('dag-stepper-track');
            if (track) {
                track.innerHTML = steps.map((s, idx) => {
                    const isCompleted = (s.status || '').toLowerCase() === 'completed';
                    const isRunning = (s.status || '').toLowerCase() === 'running';
                    const isFailed = (s.status || '').toLowerCase() === 'failed';
                    
                    const borderColor = isCompleted ? '#1E8E3E' : (isFailed ? '#D93025' : (isRunning ? '#1967D2' : '#E8DFD5'));
                    const icon = isCompleted ? 'check' : (isFailed ? 'close' : (isRunning ? 'sync' : 'pending'));
                    const iconColor = isCompleted ? '#137333' : (isFailed ? '#C5221F' : '#1A73E8');
                    const dur = s.duration_ms != null ? `${Math.round(s.duration_ms)}ms` : '—';
                    const isAI = s.step_name.includes('intent') || s.step_name.includes('nl') || s.step_name.includes('ai');

                    return `
                        <div data-step-index="${idx}" style="display: flex; flex-direction: column; align-items: center; width: 170px; z-index: 2; cursor: pointer;">
                            <div style="width: 36px; height: 36px; border-radius: 50%; background: #FFFFFF; border: 2px solid ${borderColor}; display: flex; align-items: center; justify-content: center; color: ${iconColor}; box-shadow: 0 1px 3px rgba(44,29,20,0.04);">
                                <span class="material-symbols-outlined" style="font-size: 18px;">${icon}</span>
                            </div>
                            <div id="dag-step-box-${idx}" style="margin-top: 10px; background: #FFFFFF; border: 1px solid #E8DFD5; border-radius: 8px; padding: 10px; width: 100%; text-align: center; box-shadow: 0 1px 3px rgba(44,29,20,0.04); transition: all 0.15s ease;">
                                <div style="display: flex; justify-content: space-between; font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #7A5A47; margin-bottom: 4px;">
                                    <span>0${idx + 1}${isAI ? ' (AI)' : ''}</span>
                                    <span style="background: ${isCompleted ? '#E6F4EA' : '#FCE8E6'}; color: ${isCompleted ? '#137333' : '#C5221F'}; padding: 1px 4px; border-radius: 2px; font-weight: 600;">${dur}</span>
                                </div>
                                <div style="font-weight: 600; font-size: 11px; color: #2C1D14; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${s.step_name}">${s.step_name}</div>
                                <div style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #7A5A47; margin-top: 2px;">Attempt ${s.attempt_number || 1}/1</div>
                            </div>
                        </div>
                        ${idx < steps.length - 1 ? '<span class="material-symbols-outlined" style="color: #C68B59; font-size: 18px;">arrow_forward</span>' : ''}
                    `;
                }).join('');
            }
        }
        
        // Event delegation for DAG step selection
        const track = document.getElementById('dag-stepper-track');
        if (track) {
            track.addEventListener('click', (e) => {
                const stepDiv = e.target.closest('[data-step-index]');
                if (stepDiv) {
                    const idx = parseInt(stepDiv.dataset.stepIndex, 10);
                    selectDagStep(idx);
                }
            });
        }

        const tbody = document.getElementById('execution-steps-table-body');
        if (steps.length > 0) {
            tbody.innerHTML = steps.map((s, idx) => {
                const st = (s.status || 'completed').toLowerCase();
                const isSuccess = st === 'completed';
                const badgeBg = isSuccess ? '#E6F4EA' : '#FCE8E6';
                const badgeBorder = isSuccess ? '#CEEAD6' : '#FAD2CF';
                const badgeText = isSuccess ? '#137333' : '#C5221F';
                const dotBg = isSuccess ? '#1E8E3E' : '#D93025';
                const dur = s.duration_ms != null ? `${s.duration_ms}ms` : '—';
                const started = s.started_at ? new Date(s.started_at).toLocaleTimeString() : '—';
                const diag = s.error_category ? `[${s.error_category}]` : (s.step_metadata ? JSON.stringify(s.step_metadata) : 'None');

                return `
                    <tr style="border-bottom: 1px solid rgba(232,223,213,0.6);">
                        <td style="padding: 12px 16px; font-weight: 600; color: #2C1D14; display: flex; align-items: center; gap: 6px;">
                            <span class="material-symbols-outlined" style="font-size: 16px; color: #C68B59;">rule</span>
                            <span>${s.step_name}</span>
                        </td>
                        <td style="padding: 12px 16px;">
                            <span style="display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 9999px; font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; background: ${badgeBg}; border: 1px solid ${badgeBorder}; color: ${badgeText};">
                                <span style="width: 6px; height: 6px; border-radius: 50%; background: ${dotBg};"></span>
                                <span>${st.toUpperCase()}</span>
                            </span>
                        </td>
                        <td style="padding: 12px 16px; text-align: right; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7A5A47;">${started}</td>
                        <td style="padding: 12px 16px; text-align: right; font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 700; color: #2C1D14;">${dur}</td>
                        <td style="padding: 12px 16px; text-align: center; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7A5A47;">${s.attempt_number || 1} / 1</td>
                        <td style="padding: 12px 16px; text-align: right; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7A5A47; overflow: hidden; text-overflow: ellipsis; max-width: 200px;">${diag}</td>
                    </tr>
                `;
            }).join('');
        } else {
            tbody.innerHTML = `
                <tr>
                    <td colspan="6" style="padding: 32px; text-align: center; color: #7A5A47; font-family: 'JetBrains Mono', monospace;">
                        No discrete step attempts recorded for this execution.
                    </td>
                </tr>
            `;
        }

        // JSON Tabs
        jsonTabs.input = JSON.stringify(wf.original_request || {}, null, 2);
        jsonTabs.resolved = JSON.stringify(wf.result || wf.error_details || {}, null, 2);
        jsonTabs.telemetry = JSON.stringify(wf, null, 2);
        switchTab('resolved');
    }

    // Auto-initialize
    document.addEventListener('DOMContentLoaded', initWorkflowDetail);
})();