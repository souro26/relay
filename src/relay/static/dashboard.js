/**
 * Dashboard Page - Frontend Controller
 * Handles metrics hydration, KPI cards, donut chart, and recent runs table.
 */

(function() {
    'use strict';

    let rawMetrics = null;

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

    async function hydrateDashboard() {
        try {
            const res = await fetch('/api/v1/metrics');
            if (!res.ok) return;
            const data = await res.json();
            rawMetrics = data;
            const numFmt = new Intl.NumberFormat('en-US');

            // 1. KPI Cards
            const total = data.total_workflows || 0;
            document.getElementById('kpi-total-executions').textContent = numFmt.format(total);
            if (data.success_rate_percentage) document.getElementById('kpi-success-rate').textContent = data.success_rate_percentage;
            if (data.median_duration_ms != null) document.getElementById('kpi-median-latency').textContent = `${data.median_duration_ms}ms`;
            if (data.p95_duration_ms != null) {
                document.getElementById('kpi-p95-latency').textContent = `${data.p95_duration_ms}ms`;
                const headerP95 = document.getElementById('header-latency-text');
                if (headerP95) headerP95.textContent = `~${data.p95_duration_ms}ms`;
            }
            document.getElementById('kpi-failed-count').textContent = data.failed_workflows || 0;
            document.getElementById('kpi-failed-badge').textContent = `${data.failed_workflows || 0} Total`;
            document.getElementById('kpi-running-count').textContent = data.running_workflows || 0;
            if (data.total_tokens) document.getElementById('kpi-total-tokens').textContent = numFmt.format(data.total_tokens);
            if (data.total_estimated_cost_usd != null) document.getElementById('kpi-estimated-cost').textContent = `$${data.total_estimated_cost_usd.toFixed(4)}`;

            // 2. Donut & Legend
            const comp = data.completed_workflows || 0;
            const run = data.running_workflows || 0;
            const unc = data.uncertain_workflows || 0;
            const fail = data.failed_workflows || 0;
            const sum = comp + run + unc + fail;

            document.getElementById('legend-completed-cnt').textContent = numFmt.format(comp);
            document.getElementById('legend-running-cnt').textContent = numFmt.format(run);
            document.getElementById('legend-uncertain-cnt').textContent = numFmt.format(unc);
            document.getElementById('legend-failed-cnt').textContent = numFmt.format(fail);

            if (sum > 0) {
                const compPct = ((comp / sum) * 100).toFixed(1);
                document.getElementById('donut-center-pct').textContent = `${compPct}%`;
                document.getElementById('legend-completed-pct').textContent = `${compPct}%`;
                document.getElementById('legend-running-pct').textContent = `${((run / sum) * 100).toFixed(1)}%`;
                document.getElementById('legend-uncertain-pct').textContent = `${((unc / sum) * 100).toFixed(1)}%`;
                document.getElementById('legend-failed-pct').textContent = `${((fail / sum) * 100).toFixed(1)}%`;

                // SVG Donut calculation
                const circum = 238.7;
                const compOffset = circum - (comp / sum) * circum;
                const compCircle = document.getElementById('donut-svg-completed');
                if (compCircle) compCircle.style.strokeDashoffset = compOffset;
            } else {
                document.getElementById('donut-center-pct').textContent = '—';
                document.getElementById('donut-center-lbl').textContent = 'NO DATA';
            }

            // 3. Diagnostics
            if (data.avg_llm_latency_ms != null) {
                document.getElementById('diag-avg-llm-latency').textContent = `${data.avg_llm_latency_ms}ms`;
            }
            document.getElementById('diag-total-llm-calls').textContent = data.total_llm_invocations || 0;

            const failList = document.getElementById('diag-step-failures-list');
            if (data.step_failure_counts && Object.keys(data.step_failure_counts).length > 0) {
                failList.innerHTML = Object.entries(data.step_failure_counts).map(([step, count]) => `
                    <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 12px; background: #F5EFEB; border: 1px solid #E8DFD5; border-radius: 8px;">
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: #2C1D14;">${escapeHtml(step)}</span>
                        <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 700; background: #FCE8E6; color: #C5221F; border: 1px solid #FAD2CF; padding: 2px 6px; border-radius: 4px;">${count} failures</span>
                    </div>
                `).join('');
            }

            // 4. Recent Runs Table
            renderRunsTable(data.recent_workflows || []);

        } catch (e) {
            console.error('Failed to load metrics:', e);
        }
    }

    function renderRunsTable(runs) {
        const tbody = document.getElementById('dashboard-runs-tbody');
        const countSpan = document.getElementById('dashboard-showing-count');
        if (!tbody) return;

        if (countSpan) countSpan.textContent = `Showing ${runs.length} recent runs`;

        if (runs.length === 0) {
            tbody.innerHTML = `
                <tr>
                    <td colspan="7" style="padding: 32px; text-align: center; color: #7A5A47; font-family: 'JetBrains Mono', monospace;">
                        No workflow runs recorded yet. Start one from the <a href="/request" style="color: #B45309; font-weight: 600; text-decoration: underline;">NL Request Studio</a>.
                    </td>
                </tr>
            `;
            return;
        }

        tbody.innerHTML = runs.map(w => {
            const shortId = (w.id || '').substring(0, 11);
            const st = (w.status || 'pending').toLowerCase();
            const badgeBg = st === 'completed' ? '#E6F4EA' : (st === 'failed' ? '#FCE8E6' : '#E8F0FE');
            const badgeBorder = st === 'completed' ? '#CEEAD6' : (st === 'failed' ? '#FAD2CF' : '#D2E3FC');
            const badgeText = st === 'completed' ? '#137333' : (st === 'failed' ? '#C5221F' : '#1A73E8');
            const dotBg = st === 'completed' ? '#1E8E3E' : (st === 'failed' ? '#D93025' : '#1967D2');
            const dur = w.duration_ms != null ? `${Math.round(w.duration_ms)}ms` : '—';
            const tokens = w.total_tokens ? new Intl.NumberFormat('en-US').format(w.total_tokens) : '—';
            const dateStr = w.created_at ? new Date(w.created_at).toLocaleTimeString() : '—';

            return `
                <tr style="border-bottom: 1px solid rgba(232,223,213,0.6);">
                    <td style="padding: 12px 16px; font-family: 'JetBrains Mono', monospace; font-size: 12px; font-weight: 600; color: #3D271D;">
                        ${shortId}
                    </td>
                    <td style="padding: 12px 16px; font-weight: 600; color: #2C1D14;">
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span class="material-symbols-outlined" style="font-size: 16px; color: #C68B59;">alt_route</span>
                            <span>${escapeHtml(w.workflow_type || 'order_change')}</span>
                        </div>
                    </td>
                    <td style="padding: 12px 16px;">
                        <span style="display: inline-flex; align-items: center; gap: 6px; padding: 2px 10px; border-radius: 9999px; font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; background: ${badgeBg}; border: 1px solid ${badgeBorder}; color: ${badgeText};">
                            <span style="width: 6px; height: 6px; border-radius: 50%; background: ${dotBg};"></span>
                            <span>${(w.status || 'PENDING').toUpperCase()}</span>
                        </span>
                    </td>
                    <td style="padding: 12px 16px; text-align: right; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #573D2F;">${dur}</td>
                    <td style="padding: 12px 16px; text-align: right; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7A5A47;">${tokens}</td>
                    <td style="padding: 12px 16px; text-align: right; font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #7A5A47;">${dateStr}</td>
                    <td style="padding: 12px 16px; text-align: center;">
                        <a href="/workflows/${w.id}" style="display: inline-flex; align-items: center; gap: 4px; font-family: 'JetBrains Mono', monospace; font-size: 11px; font-weight: 600; color: #3D271D; background: #F5EFEB; border: 1px solid #E8DFD5; padding: 4px 10px; border-radius: 6px; text-decoration: none;">
                            <span class="material-symbols-outlined" style="font-size: 14px; color: #C68B59;">schema</span>
                            <span>Inspect</span>
                        </a>
                    </td>
                </tr>
            `;
        }).join('');
    }

    function filterRuns() {
        if (!rawMetrics || !rawMetrics.recent_workflows) return;
        const searchInput = document.getElementById('dashboard-search-input');
        const statusSelect = document.getElementById('dashboard-status-select');
        const query = (searchInput?.value || '').toLowerCase().trim();
        const status = statusSelect?.value || 'all';

        const filtered = rawMetrics.recent_workflows.filter(w => {
            const matchQ = !query || (w.id || '').toLowerCase().includes(query) || (w.workflow_type || '').toLowerCase().includes(query);
            const matchS = status === 'all' || (w.status || '').toLowerCase() === status;
            return matchQ && matchS;
        });
        renderRunsTable(filtered);
    }

    // Auto-initialize
    document.addEventListener('DOMContentLoaded', () => {
        hydrateDashboard();

        const searchInput = document.getElementById('dashboard-search-input');
        const statusSelect = document.getElementById('dashboard-status-select');
        if (searchInput) searchInput.addEventListener('input', filterRuns);
        if (statusSelect) statusSelect.addEventListener('change', filterRuns);

        // Refresh button
        const refreshBtn = document.getElementById('btn-refresh-dashboard');
        if (refreshBtn) {
            refreshBtn.removeAttribute('onclick');
            refreshBtn.addEventListener('click', hydrateDashboard);
        }
    });
})();