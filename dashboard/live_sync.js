(function () {
    function extractLiveEvent(state) {
        return state && typeof state === 'object' ? (state._event || null) : null;
    }

    function buildLiveMessage(state) {
        if (!state || typeof state !== 'object') {
            return { message: 'live indisponible', isError: true };
        }
        const parts = [];
        if (state.data_reset && state.data_reset.running) {
            parts.push('reset data');
        }
        if (state.orders && state.orders.running) {
            parts.push('commandes live');
        }
        if (state.alerts && state.alerts.running) {
            parts.push('alertes live');
        }
        if (state.micro_batch && state.micro_batch.running) {
            parts.push('micro-batch');
        }
        if (parts.length) {
            return { message: parts.join(' + '), isError: false, active: true };
        }
        return { message: 'idle', isError: false, active: false };
    }

    function attachLiveSync(options) {
        const {
            apiUrl,
            onTick,
            onState,
            setStatus,
            refreshOnIdleEveryMs = 1000,
            activeRefreshEveryMs = 1000,
            minRefreshIntervalMs = 1000,
            reconnectDelayMs = 1000,
            fallbackEveryMs = 1000
        } = options || {};

        if (!apiUrl || typeof onTick !== 'function') {
            return { disconnect() {} };
        }

        let source = null;
        let reconnectTimer = null;
        let refreshInFlight = false;
        let refreshTimer = null;
        let pendingReason = null;
        let lastWasActive = false;
        let lastIdleRefreshAt = 0;
        let lastRefreshAt = 0;

        async function executeRefresh(reason) {
            refreshInFlight = true;
            lastRefreshAt = Date.now();
            try {
                await onTick(reason);
            } finally {
                refreshInFlight = false;
                if (pendingReason) {
                    const nextReason = pendingReason;
                    pendingReason = null;
                    queueRefresh(nextReason);
                }
            }
        }

        function queueRefresh(reason) {
            const now = Date.now();
            const elapsed = now - lastRefreshAt;
            const remaining = Math.max(minRefreshIntervalMs - elapsed, 0);

            if (refreshInFlight) {
                pendingReason = reason;
                return;
            }

            if (remaining === 0) {
                if (refreshTimer) {
                    clearTimeout(refreshTimer);
                    refreshTimer = null;
                }
                executeRefresh(reason);
                return;
            }

            pendingReason = reason;
            if (refreshTimer) return;
            refreshTimer = window.setTimeout(() => {
                refreshTimer = null;
                const nextReason = pendingReason || reason;
                pendingReason = null;
                executeRefresh(nextReason);
            }, remaining);
        }

        function updateStatus(state, isError = false) {
            if (typeof setStatus !== 'function') return;
            if (isError) {
                setStatus('live offline', true);
                return;
            }
            const payload = buildLiveMessage(state);
            const liveEvent = extractLiveEvent(state);
            const suffix = liveEvent && liveEvent.topic ? ` • ${liveEvent.topic}` : '';
            setStatus(`${payload.message}${suffix}`, !!payload.isError);
        }

        function scheduleReconnect() {
            if (reconnectTimer) return;
            reconnectTimer = window.setTimeout(() => {
                reconnectTimer = null;
                connect();
            }, reconnectDelayMs);
        }

        function connect() {
            if (typeof window.EventSource !== 'function') {
                window.setInterval(() => queueRefresh('live-fallback'), fallbackEveryMs);
                return;
            }
            if (source) {
                source.close();
            }
            source = new window.EventSource(`${apiUrl}/api/live/stream`);
            source.onmessage = async (event) => {
                try {
                    const state = JSON.parse(event.data);
                    const live = buildLiveMessage(state);
                    const liveEvent = extractLiveEvent(state);
                    if (typeof onState === 'function') {
                        onState(state);
                    }
                    updateStatus(state, false);
                    const now = Date.now();
                    if (liveEvent) {
                        queueRefresh(`live-event:${liveEvent.topic || 'update'}`);
                        lastIdleRefreshAt = now;
                    } else if (live.active && (now - lastRefreshAt >= activeRefreshEveryMs)) {
                        queueRefresh('live-active');
                        lastIdleRefreshAt = now;
                    } else if (lastWasActive) {
                        queueRefresh('live-end');
                        lastIdleRefreshAt = now;
                    } else if (now - lastIdleRefreshAt > refreshOnIdleEveryMs) {
                        queueRefresh('live-idle');
                        lastIdleRefreshAt = now;
                    }
                    lastWasActive = !!live.active;
                } catch (error) {
                    console.error('Live sync parse error:', error);
                }
            };
            source.onerror = () => {
                updateStatus(null, true);
                if (source) {
                    source.close();
                    source = null;
                }
                scheduleReconnect();
            };
        }

        connect();

        return {
            disconnect() {
                if (refreshTimer) {
                    clearTimeout(refreshTimer);
                    refreshTimer = null;
                }
                if (reconnectTimer) {
                    clearTimeout(reconnectTimer);
                    reconnectTimer = null;
                }
                if (source) {
                    source.close();
                    source = null;
                }
            }
        };
    }

    window.KiLiveSync = { attach: attachLiveSync };
})();
