// Pi Status Dashboard Frontend Logic

// 1. Digital Clock & Date Update
function updateClock() {
    const timeEl = document.getElementById('clock-time');
    const dateEl = document.getElementById('clock-date');
    if (!timeEl || !dateEl) return;

    const now = new Date();
    
    // Format Time: HH:MM:SS
    const hours = String(now.getHours()).padStart(2, '0');
    const minutes = String(now.getMinutes()).padStart(2, '0');
    const seconds = String(now.getSeconds()).padStart(2, '0');
    timeEl.textContent = `${hours}:${minutes}:${seconds}`;

    // Format Date: Day, Month Date, Year
    const options = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    dateEl.textContent = now.toLocaleDateString('en-US', options).toUpperCase();
}
setInterval(updateClock, 500);
updateClock();

// 2. Circular Progress Rings
function setRingPercentage(ringId, percent) {
    const ring = document.getElementById(ringId);
    if (!ring) return;
    
    const radius = ring.r.baseVal.value;
    const circumference = 2 * Math.PI * radius; // 314.159
    
    // Clamp percent between 0 and 100
    const clampedPercent = Math.max(0, Math.min(100, percent));
    const offset = circumference - (clampedPercent / 100) * circumference;
    
    ring.style.strokeDashoffset = offset;
}

// Format seconds into readable uptime (e.g. 2d 5h 12m)
function formatUptime(seconds) {
    if (seconds <= 0) return '0m';
    const days = Math.floor(seconds / (24 * 3600));
    seconds %= (24 * 3600);
    const hours = Math.floor(seconds / 3600);
    seconds %= 3600;
    const minutes = Math.floor(seconds / 60);
    
    let parts = [];
    if (days > 0) parts.push(`${days}d`);
    if (hours > 0) parts.push(`${hours}h`);
    if (minutes > 0 || parts.length === 0) parts.push(`${minutes}m`);
    
    return parts.join(' ');
}

// 3. API Polling Loop
let isPolling = false;

async function fetchStatus() {
    if (isPolling) return;
    isPolling = true;

    try {
        const response = await fetch('/api/status');
        if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
        const data = await response.json();
        
        updateSystemHealth(data.system);
        updateNetworkStatus(data.network);
        updateProjectsStatus(data.projects);
        updateGlobalStatusBanner(data);
        
    } catch (error) {
        console.error("Failed to poll status:", error);
        setOfflineState();
    } finally {
        isPolling = false;
    }
}

// Update system performance displays
function updateSystemHealth(system) {
    if (!system) return;

    // CPU Temp
    const tempVal = document.getElementById('temp-val');
    const tempRing = document.getElementById('temp-ring');
    if (system.cpu_temp !== null) {
        tempVal.textContent = system.cpu_temp;
        // Map temp 30°C - 85°C to 0% - 100%
        const tempMin = 30;
        const tempMax = 85;
        const tempPercent = ((system.cpu_temp - tempMin) / (tempMax - tempMin)) * 100;
        setRingPercentage('temp-ring', tempPercent);
        
        // Dynamically adjust temp gauge color based on severity
        if (system.cpu_temp >= 75) {
            tempRing.style.stroke = 'var(--accent-red)';
            tempRing.style.filter = 'drop-shadow(0 0 6px var(--accent-red))';
        } else if (system.cpu_temp >= 60) {
            tempRing.style.stroke = 'var(--accent-orange)';
            tempRing.style.filter = 'drop-shadow(0 0 6px var(--accent-orange))';
        } else {
            tempRing.style.stroke = 'var(--accent-blue)';
            tempRing.style.filter = 'drop-shadow(0 0 6px var(--accent-blue))';
        }
    } else {
        tempVal.textContent = '--';
        setRingPercentage('temp-ring', 0);
    }

    // CPU Load
    const cpuVal = document.getElementById('cpu-val');
    if (system.cpu_percent !== null) {
        cpuVal.textContent = Math.round(system.cpu_percent);
        setRingPercentage('cpu-ring', system.cpu_percent);
    } else {
        cpuVal.textContent = '--';
        setRingPercentage('cpu-ring', 0);
    }

    // RAM
    const ramText = document.getElementById('ram-text');
    const ramFill = document.getElementById('ram-fill');
    if (system.memory && system.memory.total_gb > 0) {
        ramText.textContent = `${system.memory.used_gb} GB / ${system.memory.total_gb} GB (${Math.round(system.memory.percent)}%)`;
        ramFill.style.width = `${system.memory.percent}%`;
    }

    // Swap
    const swapText = document.getElementById('swap-text');
    const swapFill = document.getElementById('swap-fill');
    if (system.swap && system.swap.total_gb > 0) {
        swapText.textContent = `${system.swap.used_gb} GB / ${system.swap.total_gb} GB (${Math.round(system.swap.percent)}%)`;
        swapFill.style.width = `${system.swap.percent}%`;
    } else if (system.swap) {
        // Swap total is 0
        swapText.textContent = "0.0 GB / 0.0 GB (0%)";
        swapFill.style.width = "0%";
    }

    // Disk
    const diskText = document.getElementById('disk-text');
    const diskFill = document.getElementById('disk-fill');
    if (system.disk && system.disk.total_gb > 0) {
        diskText.textContent = `${system.disk.used_gb} GB / ${system.disk.total_gb} GB (${Math.round(system.disk.percent)}%)`;
        diskFill.style.width = `${system.disk.percent}%`;
    }

    // Quick Stats Info
    document.getElementById('cpu-freq-val').textContent = `${system.cpu_freq_ghz} GHz`;
    
    if (system.load_average) {
        document.getElementById('load-avg-val').textContent = system.load_average.join(' / ');
    }
    
    document.getElementById('uptime-val').textContent = formatUptime(system.uptime_seconds);

    // Diagnostics/Power alerts
    const voltBadge = document.getElementById('voltage-badge');
    const throttleBadge = document.getElementById('throttling-badge');
    const powerDiag = system.power_diagnostics;

    if (voltBadge && throttleBadge && powerDiag) {
        // Voltage State
        if (powerDiag.under_voltage_now) {
            voltBadge.textContent = "UNDERVOLTAGE";
            voltBadge.className = "diag-badge badge-danger";
        } else if (powerDiag.under_voltage_past) {
            voltBadge.textContent = "UNDERVOLTAGE (PAST)";
            voltBadge.className = "diag-badge badge-warning";
        } else {
            voltBadge.textContent = "STABLE";
            voltBadge.className = "diag-badge badge-ok";
        }

        // Throttling State
        if (powerDiag.throttled_now || powerDiag.arm_freq_capped_now) {
            throttleBadge.textContent = "THROTTLED";
            throttleBadge.className = "diag-badge badge-danger";
        } else if (powerDiag.throttled_past || powerDiag.arm_freq_capped_past) {
            throttleBadge.textContent = "THROTTLED (PAST)";
            throttleBadge.className = "diag-badge badge-warning";
        } else {
            throttleBadge.textContent = "STABLE";
            throttleBadge.className = "diag-badge badge-ok";
        }
    }
}

// Update network panel
function updateNetworkStatus(network) {
    if (!network) return;

    // Gateway IP
    document.getElementById('ip-gateway').textContent = network.gateway_ip || '--';

    // Ping latencies
    const pingInt = document.getElementById('ping-internet');
    const pingGw = document.getElementById('ping-gateway');

    if (network.pings.internet_ms !== null) {
        pingInt.textContent = `${network.pings.internet_ms} ms`;
        pingInt.className = "ping-val";
    } else {
        pingInt.textContent = "OFFLINE";
        pingInt.className = "ping-val ping-offline";
    }

    if (network.pings.gateway_ms !== null) {
        pingGw.textContent = `${network.pings.gateway_ms} ms`;
        pingGw.className = "ping-val";
    } else {
        pingGw.textContent = "OFFLINE";
        pingGw.className = "ping-val ping-offline";
    }

    // WiFi
    const wifiBox = document.getElementById('wifi-box');
    if (network.wifi) {
        wifiBox.style.display = 'block';
        document.getElementById('wifi-iface').textContent = network.wifi.interface;
        document.getElementById('wifi-strength').textContent = `${network.wifi.percent}%`;
        document.getElementById('wifi-fill').style.width = `${network.wifi.percent}%`;
    } else {
        wifiBox.style.display = 'none';
    }

    // Tailscale
    const tsBox = document.getElementById('tailscale-box');
    if (network.tailscale && network.tailscale.enabled) {
        tsBox.style.display = 'block';
        const tsStatus = document.getElementById('tailscale-status-val');
        const tsIp = document.getElementById('tailscale-ip');
        const tsDns = document.getElementById('tailscale-dns');
        
        tsStatus.textContent = network.tailscale.backend_state.toUpperCase();
        tsIp.textContent = network.tailscale.ip || '--';
        tsDns.textContent = network.tailscale.dns_name || '--';
        
        if (network.tailscale.status === 'online') {
            tsStatus.style.color = 'var(--accent-green)';
        } else {
            tsStatus.style.color = 'var(--accent-red)';
        }
    } else {
        tsBox.style.display = 'none';
    }

    // Local IP addresses
    const ipsContainer = document.getElementById('ips-container');
    if (ipsContainer && network.local_ips) {
        ipsContainer.innerHTML = '';
        Object.entries(network.local_ips).forEach(([iface, ip]) => {
            const row = document.createElement('div');
            row.className = 'ip-row';
            row.innerHTML = `
                <span class="ip-label">${iface.toUpperCase()} IP</span>
                <span class="ip-val">${ip}</span>
            `;
            ipsContainer.appendChild(row);
        });
    }
}

// Update projects grid
function updateProjectsStatus(projects) {
    const container = document.getElementById('projects-list-container');
    if (!container || !projects) return;

    container.innerHTML = '';

    projects.forEach(project => {
        const card = document.createElement('div');
        card.className = 'project-card';
        card.id = `project-card-${project.id}`;

        // Compute status class and tag text
        let statusClass = 'status-offline';
        let statusLabel = project.status || 'offline';
        
        if (project.status === 'online') {
            statusClass = 'status-online';
        } else if (project.status === 'Pending Setup' || project.is_dummy) {
            statusClass = 'status-pending';
            statusLabel = project.status;
        }

        // Response latency tag if available
        let latencyTag = '';
        if (project.latency_ms !== undefined && project.status === 'online') {
            latencyTag = `<span class="proj-badge">${project.latency_ms}ms</span>`;
        } else if (project.type === 'systemd' && project.status === 'online') {
            latencyTag = `<span class="proj-badge">systemd</span>`;
        }

        // Restart button for systemd services
        let restartButton = '';
        if (project.type === 'systemd') {
            restartButton = `
                <button class="btn-restart" title="Restart Service" onclick="restartService('${project.id}')">
                    <i data-lucide="rotate-cw" style="width: 14px; height: 14px;"></i>
                </button>
            `;
        }

        card.innerHTML = `
            <div class="proj-info">
                <div class="proj-name-row">
                    <span class="proj-name">${project.name}</span>
                    ${latencyTag}
                </div>
                <span class="proj-desc">${project.description}</span>
            </div>
            <div class="proj-controls">
                <div class="status-indicator ${statusClass}">
                    <span class="status-indicator-dot"></span>
                    <span>${statusLabel}</span>
                </div>
                ${restartButton}
            </div>
        `;
        container.appendChild(card);
    });

    // Re-trigger Lucide icon instantiation on the newly added buttons
    lucide.createIcons();
}

// Update global operational status banner
function updateGlobalStatusBanner(data) {
    const banner = document.getElementById('global-status-banner');
    const bannerText = banner.querySelector('.status-text');
    if (!banner || !bannerText) return;

    // Check for critical service failures or power supply alerts
    const powerAlerts = data.system && data.system.power_diagnostics;
    const projects = data.projects || [];
    
    const hasPowerWarnings = powerAlerts && powerAlerts.has_warnings && (powerAlerts.under_voltage_now || powerAlerts.throttled_now);
    const offlineServices = projects.filter(p => p.type === 'systemd' && p.status === 'offline');
    
    if (offlineServices.length > 0) {
        banner.className = "status-banner status-critical";
        bannerText.textContent = `${offlineServices.length} CRITICAL SERVICE(S) OFFLINE`;
    } else if (hasPowerWarnings) {
        banner.className = "status-banner status-warning";
        bannerText.textContent = "PI POWER ALERT: UNDER-VOLTAGE/THROTTLING ACTIVE";
    } else {
        banner.className = "status-banner status-all-ok";
        bannerText.textContent = "ALL SYSTEMS OPERATIONAL";
    }
}

// Fallback visual state when the server is unresponsive
function setOfflineState() {
    const banner = document.getElementById('global-status-banner');
    const bannerText = banner.querySelector('.status-text');
    if (banner && bannerText) {
        banner.className = "status-banner status-critical";
        bannerText.textContent = "DISCONNECTED FROM PI BACKEND";
    }
    
    document.getElementById('temp-val').textContent = '--';
    setRingPercentage('temp-ring', 0);
    document.getElementById('cpu-val').textContent = '--';
    setRingPercentage('cpu-ring', 0);
    
    document.getElementById('ping-internet').textContent = '--';
    document.getElementById('ping-gateway').textContent = '--';
}

// 4. REST Service Actions
async function restartService(serviceId) {
    const card = document.getElementById(`project-card-${serviceId}`);
    const btn = card ? card.querySelector('.btn-restart') : null;
    
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<div class="spinner" style="width: 12px; height: 12px; border-width: 1px;"></div>`;
    }

    try {
        const response = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: 'restart_service', target: serviceId })
        });
        const result = await response.json();
        
        if (response.ok) {
            console.log(result.message);
            // Instantly re-poll to show new online state
            await fetchStatus();
        } else {
            alert(`Failed to restart: ${result.message}`);
        }
    } catch (error) {
        console.error("Error restarting service:", error);
        alert("Network error occurred while requesting service restart.");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<i data-lucide="rotate-cw" style="width: 14px; height: 14px;"></i>`;
            lucide.createIcons();
        }
    }
}

// 5. System Modal controls
let activeSystemAction = null;

function openSystemModal(action) {
    activeSystemAction = action;
    const modal = document.getElementById('confirmation-modal');
    const title = document.getElementById('modal-title');
    const desc = document.getElementById('modal-desc');
    const icon = document.getElementById('modal-icon');
    
    if (action === 'reboot') {
        title.textContent = "Reboot System";
        desc.textContent = "Are you sure you want to reboot the Raspberry Pi? The dashboard and all background services will be temporarily unavailable.";
        icon.setAttribute('data-lucide', 'refresh-cw');
    } else if (action === 'shutdown') {
        title.textContent = "Power Off System";
        desc.textContent = "Are you sure you want to shut down the Raspberry Pi? It will shut down completely and will need a manual power cycle to turn back on.";
        icon.setAttribute('data-lucide', 'power');
    }
    
    lucide.createIcons();
    modal.classList.add('modal-active');
}

function closeSystemModal() {
    const modal = document.getElementById('confirmation-modal');
    modal.classList.remove('modal-active');
    activeSystemAction = null;
}

// Modal execute click handler
document.getElementById('modal-btn-confirm').addEventListener('click', async () => {
    if (!activeSystemAction) return;
    
    const confirmBtn = document.getElementById('modal-btn-confirm');
    confirmBtn.disabled = true;
    confirmBtn.textContent = "Executing...";

    try {
        const response = await fetch('/api/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action: activeSystemAction })
        });
        const result = await response.json();
        
        if (response.ok) {
            alert(result.message);
            closeSystemModal();
        } else {
            alert(`Execution failed: ${result.message}`);
        }
    } catch (error) {
        console.error("Error executing system action:", error);
        alert("Network error occurred.");
    } finally {
        confirmBtn.disabled = false;
        confirmBtn.textContent = "Execute";
    }
});

// Start polling
fetchStatus();
setInterval(fetchStatus, 3000);
