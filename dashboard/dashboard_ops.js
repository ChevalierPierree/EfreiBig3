(function () {
    function formatTime(value) {
        if (!value) return '-';
        const date = value instanceof Date ? value : new Date(value);
        if (Number.isNaN(date.getTime())) return '-';
        return new Intl.DateTimeFormat('fr-FR', {
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }).format(date);
    }

    function formatDateTime(value) {
        if (!value) return '-';
        const date = new Date(value);
        if (Number.isNaN(date.getTime())) return '-';
        return new Intl.DateTimeFormat('fr-FR', {
            day: '2-digit',
            month: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        }).format(date);
    }

    function setPill(el, label, tone) {
        if (!el) return;
        el.textContent = label;
        el.className = 'status-pill';
        if (tone) el.classList.add(tone);
    }

    function buildResetDetail(state) {
        if (!state) return 'Jeu de donnees initial disponible.';
        const summary = state.summary || {};
        if (state.running) {
            return `${state.message || 'Reset en cours'}${state.step ? ` • etape ${state.step}` : ''}`;
        }
        if (state.status === 'success') {
            const orders = summary.postgres_orders ?? 0;
            const alerts = summary.postgres_fraud_alerts ?? 0;
            const attempts = summary.postgres_checkout_attempts ?? 0;
            return `Etat initial recharge le ${formatDateTime(state.finished_at)} • ${orders} commandes • ${alerts} alertes live • ${attempts} tentatives checkout.`;
        }
        if (state.status === 'error') {
            return state.message || 'Erreur pendant le reset.';
        }
        return state.message || 'Jeu de donnees initial disponible.';
    }

    function attachDashboardOps(options) {
        const { apiUrl, onAfterReset } = options || {};
        const runtimeLine = document.querySelector('.command-strip .runtime-line');
        if (!apiUrl || !runtimeLine) {
            return {
                markRefresh() {},
                updateLiveState() {},
                disconnect() {}
            };
        }

        const wrapper = document.createElement('div');
        wrapper.className = 'ops-inline';
        wrapper.innerHTML = [
            '<span class="command-chip" data-role="cadence">Live 1s</span>',
            '<span class="command-chip" data-role="refresh">MAJ -</span>',
            '<span class="status-pill success" data-role="live-state">Flux stables</span>',
            '<span class="status-pill" data-role="reset-status">Reset stable</span>',
            '<button class="btn-danger" type="button" data-role="reset-button">Reset data</button>',
            '<span class="ops-copy" data-role="reset-detail">Jeu de donnees initial disponible.</span>'
        ].join('');
        runtimeLine.appendChild(wrapper);

        const refs = {
            cadence: wrapper.querySelector('[data-role="cadence"]'),
            refresh: wrapper.querySelector('[data-role="refresh"]'),
            liveState: wrapper.querySelector('[data-role="live-state"]'),
            resetStatus: wrapper.querySelector('[data-role="reset-status"]'),
            resetButton: wrapper.querySelector('[data-role="reset-button"]'),
            resetDetail: wrapper.querySelector('[data-role="reset-detail"]')
        };

        let pollTimer = null;
        let lastResetRunning = false;

        function ensurePolling() {
            if (pollTimer) return;
            pollTimer = window.setInterval(loadResetState, 1000);
        }

        function stopPolling() {
            if (!pollTimer) return;
            window.clearInterval(pollTimer);
            pollTimer = null;
        }

        function renderResetState(state) {
            if (!state) return;
            const wasRunning = lastResetRunning;
            lastResetRunning = !!state.running;

            if (state.running) {
                setPill(refs.resetStatus, 'Reset en cours', 'warning');
                refs.resetButton.disabled = true;
                refs.resetButton.textContent = 'Reset en cours';
                ensurePolling();
            } else if (state.status === 'success') {
                setPill(refs.resetStatus, 'Reset termine', 'success');
                refs.resetButton.disabled = false;
                refs.resetButton.textContent = 'Reset data';
                stopPolling();
            } else if (state.status === 'error') {
                setPill(refs.resetStatus, 'Reset en erreur', 'danger');
                refs.resetButton.disabled = false;
                refs.resetButton.textContent = 'Relancer reset';
                stopPolling();
            } else {
                setPill(refs.resetStatus, 'Reset stable', 'cool');
                refs.resetButton.disabled = false;
                refs.resetButton.textContent = 'Reset data';
                stopPolling();
            }

            refs.resetDetail.textContent = buildResetDetail(state);
            if (wasRunning && !state.running && state.status === 'success' && typeof onAfterReset === 'function') {
                onAfterReset(state);
            }
        }

        async function loadResetState() {
            try {
                const response = await fetch(`${apiUrl}/api/system/reset-status`, { cache: 'no-store' });
                if (!response.ok) return;
                const payload = await response.json();
                renderResetState(payload);
            } catch (error) {
                console.warn('Reset status unavailable:', error);
            }
        }

        async function triggerReset() {
            const confirmed = window.confirm(
                'Revenir a l etat initial de la base ? Les flux actifs seront arretes et les donnees generees seront purgees.'
            );
            if (!confirmed) return;

            refs.resetButton.disabled = true;
            refs.resetButton.textContent = 'Reset en cours';
            refs.resetDetail.textContent = 'Reinitialisation du jeu de donnees...';
            ensurePolling();

            try {
                const response = await fetch(`${apiUrl}/api/system/reset-data`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        confirm: true,
                        clear_runtime_artifacts: true,
                        stop_live_jobs: true
                    })
                });
                const payload = await response.json().catch(() => ({}));
                if (!response.ok) {
                    const detail = payload.detail || `HTTP ${response.status}`;
                    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
                }
                renderResetState(payload);
            } catch (error) {
                console.error(error);
                renderResetState({
                    running: false,
                    status: 'error',
                    message: String(error.message || error)
                });
            }
        }

        function markRefresh(reason) {
            const suffix = reason ? ` • ${reason}` : '';
            refs.refresh.textContent = `MAJ ${formatTime(new Date())}${suffix}`;
        }

        function updateLiveState(state) {
            const heartbeat = Math.max(1, Math.round(Number(state && state.heartbeat_seconds ? state.heartbeat_seconds : 1)));
            refs.cadence.textContent = `Live ${heartbeat}s`;

            if (state && state.data_reset) {
                renderResetState(state.data_reset);
            }

            if (state && state.data_reset && state.data_reset.running) {
                setPill(refs.liveState, 'Reset en cours', 'warning');
                return;
            }

            if (state && state.jobs_active) {
                setPill(refs.liveState, 'Flux actifs', 'cool');
                return;
            }

            setPill(refs.liveState, 'Flux stables', 'success');
        }

        refs.resetButton.addEventListener('click', triggerReset);
        loadResetState();

        return {
            markRefresh,
            updateLiveState,
            disconnect() {
                stopPolling();
            }
        };
    }

    window.KiDashboardOps = { attach: attachDashboardOps };
})();
