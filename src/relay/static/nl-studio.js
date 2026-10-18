/**
 * Natural Language Request Studio - Frontend Controller
 * Handles real-time character counting, parameter extraction preview, and workflow submission.
 */

(function() {
    'use strict';

    // ==============================================================================
    // NL Request Studio Initialization
    // ==============================================================================
    window.initNlStudio = function initNlStudio() {
        // Elements
        var promptEl = document.getElementById('nl-prompt-text');
        var charCounterEl = document.getElementById('nl-char-counter');
        var previewOrderEl = document.getElementById('preview-order-id');
        var previewDateEl = document.getElementById('preview-target-date');
        var previewCustEl = document.getElementById('preview-customer-id');

        var btnSubmit = document.getElementById('btn-submit-nl');
        var btnIcon = document.getElementById('btn-icon');
        var btnTextEl = document.getElementById('btn-submit-text');
        var errorBox = document.getElementById('nl-error-box');

        var outcomeEmpty = document.getElementById('outcome-empty-state');
        var outcomeDetails = document.getElementById('outcome-details');
        var outcomeBadgeContainer = document.getElementById('outcome-badge-container');
        var outcomeWfId = document.getElementById('outcome-workflow-id');
        var outcomeTokens = document.getElementById('outcome-tokens');
        var outcomeCost = document.getElementById('outcome-cost');
        var outcomeAction = document.getElementById('outcome-action-container');

        // 1. Core Dynamic Keystroke & Parameter Function
        function updateCounter() {
            if (!promptEl) promptEl = document.getElementById('nl-prompt-text');
            var val = promptEl ? promptEl.value : '';
            var len = val.length;

            // Counter: 0 -> 1 -> 2 -> ... in real time
            if (!charCounterEl) charCounterEl = document.getElementById('nl-char-counter');
            if (charCounterEl) {
                charCounterEl.textContent = len + ' / 2000 chars';
                if (len > 2000) {
                    charCounterEl.style.color = '#C5221F';
                    charCounterEl.style.fontWeight = '700';
                } else if (len > 1800) {
                    charCounterEl.style.color = '#B06000';
                    charCounterEl.style.fontWeight = '600';
                } else {
                    charCounterEl.style.color = '#7A5A47';
                    charCounterEl.style.fontWeight = '600';
                }
            }

            // Live Parameter Extraction
            if (!previewOrderEl) previewOrderEl = document.getElementById('preview-order-id');
            if (previewOrderEl) {
                var ordMatch = val.match(/ORD-[A-Za-z0-9]+/i);
                previewOrderEl.textContent = ordMatch ? ordMatch[0].toUpperCase() : 'None detected';
                previewOrderEl.style.color = ordMatch ? '#2C1D14' : '#7A5A47';
            }

            if (!previewDateEl) previewDateEl = document.getElementById('preview-target-date');
            if (previewDateEl) {
                var dateMatch = val.match(/\b\d{4}-\d{2}-\d{2}\b/);
                if (dateMatch) {
                    previewDateEl.textContent = dateMatch[0];
                    previewDateEl.style.color = '#137333';
                } else {
                    var monthMatch = val.match(/\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}\b/i);
                    if (monthMatch) {
                        previewDateEl.textContent = monthMatch[0];
                        previewDateEl.style.color = '#137333';
                    } else {
                        previewDateEl.textContent = val.trim() ? 'Parsed on submit' : 'None detected';
                        previewDateEl.style.color = '#7A5A47';
                    }
                }
            }

            if (!previewCustEl) previewCustEl = document.getElementById('preview-customer-id');
            if (previewCustEl) {
                var custMatch = val.match(/customer-\w+|CUST-\w+/i);
                if (custMatch) {
                    previewCustEl.textContent = custMatch[0];
                    previewCustEl.style.color = '#2C1D14';
                } else {
                    previewCustEl.textContent = val.trim() ? 'Optional in prompt' : 'None detected';
                    previewCustEl.style.color = '#7A5A47';
                }
            }
        }

        // 2. High-Frequency Heartbeat Ticker (Runs every 40ms = 25 times per second)
        setInterval(updateCounter, 40);

        // Initial check
        updateCounter();

        // Clear function
        window.clearPrompt = function clearPrompt() {
            if (promptEl) {
                promptEl.value = '';
                updateCounter();
            }
            if (errorBox) errorBox.style.display = 'none';
            if (outcomeEmpty) {
                outcomeEmpty.style.display = 'block';
                outcomeEmpty.innerHTML = 'Submit a prompt to trigger model interpretation and live workflow execution.';
            }
            if (outcomeDetails) outcomeDetails.style.display = 'none';
            if (outcomeBadgeContainer) {
                outcomeBadgeContainer.innerHTML = '<span id="outcome-status-badge" style="padding: 2px 8px; border-radius: 4px; font-family: \'JetBrains Mono\', monospace; font-size: 11px; background: #F5EFEB; color: #7A5A47; font-weight: 600; border: 1px solid #E8DFD5;">IDLE</span>';
            }
        };

        // Suggestion chips
        document.querySelectorAll('.prompt-chip').forEach(function(chip) {
            chip.addEventListener('click', function() {
                if (promptEl) {
                    promptEl.value = chip.dataset.prompt;
                    updateCounter();
                }
            });
        });

        // 3. Submit Handler with Green Spinner & Live Visual Feedback
        if (btnSubmit) {
            btnSubmit.addEventListener('click', async function() {
                var text = promptEl ? promptEl.value.trim() : '';
                if (!text) {
                    alert('Please enter a request in the prompt input console.');
                    if (promptEl) promptEl.focus();
                    return;
                }

                // Hide old error
                if (errorBox) errorBox.style.display = 'none';

                // Set Loading State on Button: Emerald Green Spinner
                btnSubmit.disabled = true;
                btnSubmit.style.opacity = '0.9';
                btnSubmit.style.cursor = 'wait';
                btnSubmit.innerHTML =
                    '<span class="btn-spinner"></span>' +
                    '<span style="color: #FFFFFF; font-weight: 600;">Processing & Orchestrating...</span>';

                // Set Loading State on Outcome Card (Right Side)
                if (outcomeDetails) outcomeDetails.style.display = 'none';
                if (outcomeBadgeContainer) {
                    outcomeBadgeContainer.innerHTML =
                        '<span style="display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 4px; font-family: \'JetBrains Mono\', monospace; font-size: 11px; background: #E8F0FE; color: #1967D2; border: 1px solid #D2E3FC; font-weight: 700;">' +
                            '<span class="btn-spinner" style="width: 10px; height: 10px; border: 2px solid rgba(25,103,210,0.3); border-top-color: #1967D2;"></span>' +
                            '<span>PROCESSING</span>' +
                        '</span>';
                }
                if (outcomeEmpty) {
                    outcomeEmpty.style.display = 'block';
                    outcomeEmpty.innerHTML =
                        '<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 20px 0;">' +
                            '<span class="card-spinner"></span>' +
                            '<span style="font-weight: 600; color: #2C1D14; font-size: 13px;">Reasoning Intent & Calling Order Service...</span>' +
                            '<span style="color: #7A5A47; font-size: 11px;">Validating parameters against PostgreSQL audit ledger</span>' +
                        '</div>';
                }

                try {
                    var res = await fetch('/api/v1/order-change-requests/nl', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            text: text,
                            source_system: 'studio-web',
                            external_event_id: 'evt-studio-' + Date.now()
                        })
                    });

                    var data = await res.json();
                    if (!res.ok) {
                        var msg = 'Execution failed';
                        if (data.detail) {
                            if (typeof data.detail === 'string') msg = data.detail;
                            else if (data.detail.error) msg = data.detail.error;
                            else if (data.detail.message) msg = data.detail.message;
                            else if (Array.isArray(data.detail) && data.detail.length > 0) msg = data.detail[0].msg || JSON.stringify(data.detail);
                        }
                        throw new Error(msg);
                    }

                    // Outcome Succeeded
                    if (outcomeEmpty) outcomeEmpty.style.display = 'none';
                    if (outcomeDetails) outcomeDetails.style.display = 'flex';

                    if (data.success) {
                        if (outcomeBadgeContainer) {
                            outcomeBadgeContainer.innerHTML =
                                '<span style="display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 4px; font-family: \'JetBrains Mono\', monospace; font-size: 11px; background: #E6F4EA; color: #137333; border: 1px solid #CEEAD6; font-weight: 700;">' +
                                    '<span style="width: 6px; height: 6px; border-radius: 50%; background: #1E8E3E;" class="pulse-dot"></span>' +
                                    '<span>COMPLETED</span>' +
                                '</span>';
                        }
                    } else {
                        if (outcomeBadgeContainer) {
                            outcomeBadgeContainer.innerHTML =
                                '<span style="display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 4px; font-family: \'JetBrains Mono\', monospace; font-size: 11px; background: #FCE8E6; color: #C5221F; border: 1px solid #FAD2CF; font-weight: 700;">' +
                                    '<span style="width: 6px; height: 6px; border-radius: 50%; background: #D93025;"></span>' +
                                    '<span>FAILED</span>' +
                                '</span>';
                        }
                    }

                    if (outcomeWfId) outcomeWfId.textContent = data.workflow_id || 'None';
                    if (outcomeTokens) outcomeTokens.textContent = data.total_tokens != null ? new Intl.NumberFormat('en-US').format(data.total_tokens) : '-';
                    if (outcomeCost) outcomeCost.textContent = data.estimated_cost_usd != null ? '$' + data.estimated_cost_usd.toFixed(4) : '-';

                    if (data.workflow_id && outcomeAction) {
                        outcomeAction.innerHTML =
                            '<a href="/workflows/' + data.workflow_id + '" style="width: 100%; padding: 12px 16px; border-radius: 8px; background: #121D33; color: #FFFFFF; font-weight: 700; font-size: 13px; display: flex; align-items: center; justify-content: center; gap: 8px; text-decoration: none; box-shadow: 0 2px 8px rgba(18,29,51,0.2);">' +
                                '<span>Inspect Execution Detail & DAG</span>' +
                                '<span class="material-symbols-outlined" style="font-size: 16px; color: #C68B59;">arrow_forward</span>' +
                            '</a>';
                    }
                } catch (err) {
                    if (errorBox) {
                        errorBox.textContent = 'Error: ' + err.message;
                        errorBox.style.display = 'block';
                    }
                    if (outcomeBadgeContainer) {
                        outcomeBadgeContainer.innerHTML = '<span style="padding: 2px 8px; border-radius: 4px; font-family: \'JetBrains Mono\', monospace; font-size: 11px; background: #FCE8E6; color: #C5221F; border: 1px solid #FAD2CF; font-weight: 700;">ERROR</span>';
                    }
                    if (outcomeEmpty) {
                        outcomeEmpty.style.display = 'block';
                        outcomeEmpty.textContent = 'Execution failed: ' + err.message;
                    }
                } finally {
                    btnSubmit.disabled = false;
                    btnSubmit.style.opacity = '1';
                    btnSubmit.style.cursor = 'pointer';
                    btnSubmit.innerHTML =
                        '<span id="btn-icon" class="material-symbols-outlined" style="font-size: 18px; color: #C68B59;">play_arrow</span>' +
                        '<span id="btn-submit-text">Interpret & Execute Workflow</span>';
                }
            });
        }
    };

    // Auto-initialize on DOMContentLoaded if the page has NL studio elements
    document.addEventListener('DOMContentLoaded', function() {
        if (document.getElementById('nl-prompt-text')) {
            initNlStudio();
        }
    });
})();