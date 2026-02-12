/**
 * Solana Community Mood Tracker — Dashboard JS
 * Handles API calls, data rendering, and status polling.
 */

const EMOJIS = {
    technical: '📊', onchain: '🔗', whales: '🐋',
    news: '📰', social: '📱', fear_greed: '😱', youtube: '🎥',
};

const LABELS = {
    technical: 'Technical', onchain: 'On-Chain', whales: 'Whales',
    news: 'News', social: 'Social', fear_greed: 'Fear & Greed', youtube: 'YouTube',
};

let pollTimer = null;

// ── Trigger Analysis ──────────────────────────────────

async function triggerAnalysis() {
    const btn = document.getElementById('triggerBtn');
    btn.disabled = true;

    try {
        const res = await fetch('/api/trigger', { method: 'POST' });
        const data = await res.json();

        if (data.status === 'already_running') {
            return;
        }

        showRunningOverlay(true);
        startPolling();
    } catch (err) {
        console.error('Trigger failed:', err);
        btn.disabled = false;
    }
}

function startPolling() {
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(checkStatus, 2000);
}

async function checkStatus() {
    try {
        const res = await fetch('/api/status');
        const data = await res.json();

        updateStatusBadge(data.status);

        if (data.status === 'done') {
            clearInterval(pollTimer);
            pollTimer = null;
            showRunningOverlay(false);
            document.getElementById('triggerBtn').disabled = false;

            // Refresh all data
            await Promise.all([loadLatest(), loadHistory(), loadAccuracy()]);

            if (data.last_run) {
                document.getElementById('lastRun').textContent = formatTime(data.last_run);
            }
        } else if (data.status === 'error') {
            clearInterval(pollTimer);
            pollTimer = null;
            showRunningOverlay(false);
            document.getElementById('triggerBtn').disabled = false;
            document.getElementById('runningStatus').textContent = 'Error: ' + (data.error || 'Unknown');
        }
    } catch (err) {
        console.error('Status check failed:', err);
    }
}

function updateStatusBadge(status) {
    const badge = document.getElementById('statusBadge');
    badge.className = 'badge badge-live';

    if (status === 'running') {
        badge.textContent = 'RUNNING';
        badge.classList.add('running');
    } else if (status === 'done') {
        badge.textContent = 'READY';
        badge.classList.add('done');
    } else if (status === 'error') {
        badge.textContent = 'ERROR';
        badge.classList.add('error');
    } else {
        badge.textContent = 'IDLE';
    }
}

function showRunningOverlay(show) {
    const overlay = document.getElementById('runningOverlay');
    if (show) {
        overlay.classList.add('active');
    } else {
        overlay.classList.remove('active');
    }
}

// ── Load Data ──────────────────────────────────────────

async function loadQuickData() {
    try {
        const res = await fetch('/api/quick-data');
        const data = await res.json();

        const price = data.price?.coingecko;
        if (price) {
            document.getElementById('solPrice').textContent = '$' + (price.price_usd || 0).toFixed(2);
            const change = price.price_change_24h_pct || 0;
            const changeEl = document.getElementById('solChange');
            changeEl.textContent = (change >= 0 ? '+' : '') + change.toFixed(2) + '%';
            changeEl.className = 'stat-change ' + (change >= 0 ? 'positive' : 'negative');
        }

        const fg = data.fear_greed;
        if (fg) {
            document.getElementById('fgValue').textContent = fg.current_value || '—';
            document.getElementById('fgClass').textContent = fg.classification || '—';
            const val = fg.current_value || 50;
            const fgEl = document.getElementById('fgValue');
            if (val <= 25) fgEl.style.color = '#ef4444';
            else if (val <= 45) fgEl.style.color = '#f97316';
            else if (val <= 55) fgEl.style.color = '#eab308';
            else if (val <= 75) fgEl.style.color = '#22c55e';
            else fgEl.style.color = '#14F195';
        }
    } catch (err) {
        console.error('Quick data error:', err);
    }
}

async function loadLatest() {
    try {
        const res = await fetch('/api/latest');
        const data = await res.json();
        const pred = data.prediction;

        if (!pred) return;

        // Signal card
        const dirEl = document.getElementById('signalDir');
        dirEl.textContent = pred.direction || '—';
        if (pred.direction === 'LONG') dirEl.style.color = 'var(--long-green)';
        else if (pred.direction === 'SHORT') dirEl.style.color = 'var(--short-red)';
        else dirEl.style.color = 'var(--neutral-yellow)';

        document.getElementById('signalConf').textContent =
            (pred.confidence || 0).toFixed(1) + '% confidence';

        // Strength badge
        document.getElementById('signalStrength').textContent = pred.strength || '—';

        // Signal meter needle
        const score = pred.weighted_score || 0;
        const needlePos = ((score + 1) / 2) * 100;  // Map [-1,1] to [0%,100%]
        const needle = document.getElementById('meterNeedle');
        needle.style.left = Math.max(2, Math.min(98, needlePos)) + '%';
        document.querySelector('.meter-track').classList.add('active');

        // Price from prediction
        if (pred.current_price_usd || pred.price_at_prediction) {
            const p = pred.current_price_usd || pred.price_at_prediction;
            document.getElementById('solPrice').textContent = '$' + parseFloat(p).toFixed(2);
        }

        // Signal bars
        renderSignalBars(pred.signal_scores || {});

        // Key factors
        renderFactors(pred.top_factors || pred.factors || []);

    } catch (err) {
        console.error('Load latest error:', err);
    }
}

function renderSignalBars(scores) {
    const container = document.getElementById('signalBars');

    // Sort by absolute value
    const sorted = Object.entries(scores)
        .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));

    if (sorted.length === 0) return;

    container.innerHTML = sorted.map(([key, score]) => {
        const emoji = EMOJIS[key] || '•';
        const label = LABELS[key] || key;
        const abs = Math.abs(score);
        const widthPct = abs * 50;  // Map [0,1] to [0%,50%]
        const cls = score > 0.02 ? 'bullish' : score < -0.02 ? 'bearish' : 'neutral';
        const color = score > 0.02 ? 'var(--long-green)' : score < -0.02 ? 'var(--short-red)' : 'var(--neutral-yellow)';

        return `
        <div class="signal-row">
            <span class="signal-emoji">${emoji}</span>
            <span class="signal-name">${label}</span>
            <div class="signal-bar-container">
                <div class="signal-bar-fill ${cls}" style="width: ${widthPct}%"></div>
            </div>
            <span class="signal-score" style="color: ${color}">${score >= 0 ? '+' : ''}${score.toFixed(2)}</span>
        </div>`;
    }).join('');
}

function renderFactors(factors) {
    const container = document.getElementById('factorsList');

    if (!factors.length) return;

    container.innerHTML = factors.slice(0, 5).map((f, i) => {
        const dirClass = f.direction || (f.score > 0 ? 'bullish' : f.score < 0 ? 'bearish' : 'neutral');
        const source = f.source ? (LABELS[f.source] || f.source) : '';

        return `
        <div class="factor-item">
            <span class="factor-rank">${i + 1}</span>
            <div class="factor-content">
                <div class="factor-source ${dirClass}">${source} • ${dirClass}</div>
                <div class="factor-desc">${f.description || 'N/A'}</div>
            </div>
        </div>`;
    }).join('');
}

async function loadHistory() {
    try {
        const res = await fetch('/api/history');
        const data = await res.json();
        const preds = data.predictions || [];

        document.getElementById('historyCount').textContent = preds.length;

        const tbody = document.getElementById('historyBody');

        if (!preds.length) {
            tbody.innerHTML = '<tr><td colspan="7" class="empty-row">No predictions yet</td></tr>';
            return;
        }

        tbody.innerHTML = preds.map(p => {
            const dir = (p.direction || 'N/A').toUpperCase();
            const dirClass = dir === 'LONG' ? 'long' : dir === 'SHORT' ? 'short' : 'neutral';
            const price = p.price_at_prediction ? '$' + parseFloat(p.price_at_prediction).toFixed(2) : '—';
            const conf = p.confidence != null ? p.confidence.toFixed(1) + '%' : '—';
            const score = p.weighted_score != null ? (p.weighted_score >= 0 ? '+' : '') + p.weighted_score.toFixed(3) : '—';

            let result = '⏳';
            if (p.was_correct === true) result = '✅';
            else if (p.was_correct === false) result = '❌';

            const time = p.timestamp ? formatTime(p.timestamp) : '—';

            return `<tr>
                <td>${p.id || '—'}</td>
                <td>${time}</td>
                <td><span class="dir-badge ${dirClass}">${dir}</span></td>
                <td>${price}</td>
                <td>${conf}</td>
                <td>${score}</td>
                <td class="result-badge">${result}</td>
            </tr>`;
        }).join('');

    } catch (err) {
        console.error('Load history error:', err);
    }
}

async function loadAccuracy() {
    try {
        const res = await fetch('/api/accuracy');
        const data = await res.json();

        if (data.overall_accuracy != null) {
            document.getElementById('accuracyVal').textContent = data.overall_accuracy + '%';
        }
        if (data.checked != null) {
            document.getElementById('accuracyCount').textContent =
                `${data.correct || 0}/${data.checked} checked`;
        } else {
            document.getElementById('accuracyCount').textContent =
                `${data.total_predictions || 0} total predictions`;
        }
    } catch (err) {
        console.error('Load accuracy error:', err);
    }
}

// ── Helpers ────────────────────────────────────────────

function formatTime(isoStr) {
    try {
        const d = new Date(isoStr);
        const now = new Date();
        const diffMs = now - d;
        const diffMins = Math.floor(diffMs / 60000);
        const diffHrs = Math.floor(diffMins / 60);

        if (diffMins < 1) return 'just now';
        if (diffMins < 60) return diffMins + 'm ago';
        if (diffHrs < 24) return diffHrs + 'h ago';

        return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
        return isoStr;
    }
}

// ── Init ───────────────────────────────────────────────

async function init() {
    await Promise.all([
        loadQuickData(),
        loadLatest(),
        loadHistory(),
        loadAccuracy(),
    ]);

    // Check if a run is currently in progress
    const statusRes = await fetch('/api/status');
    const statusData = await statusRes.json();
    updateStatusBadge(statusData.status);

    if (statusData.last_run) {
        document.getElementById('lastRun').textContent = formatTime(statusData.last_run);
    }

    if (statusData.status === 'running') {
        showRunningOverlay(true);
        document.getElementById('triggerBtn').disabled = true;
        startPolling();
    }
}

init();
