const API_URL = window.location.origin + "/api";
let servicesMap = {};
let systemNodeRole = "primary";

function escapeHtml(value) {
    return String(value ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function getApiErrorPayload(data) {
    if (!data) return "";
    if (typeof data.detail === "string") return data.detail;
    if (data.detail) return JSON.stringify(data.detail);
    if (data.error) return String(data.error);
    return JSON.stringify(data);
}

async function apiRequest(url, options = {}, action = "Request") {
    const res = await fetch(url, options);
    if (!res.ok) {
        let detail = "";
        try {
            detail = getApiErrorPayload(await res.json());
        } catch {
            detail = await res.text();
        }
        throw new Error(`${action} failed (${res.status})${detail ? `: ${detail}` : ""}`);
    }
    if (res.status === 204) return null;
    const text = await res.text();
    return text ? JSON.parse(text) : null;
}

async function fetchNodeRole() {
    try {
        const data = await apiRequest(`${API_URL}/node_role`, {}, "Load node role");
        systemNodeRole = data.role;
        document.getElementById("nodeIdentity").innerText = `${systemNodeRole} Node`;

        if (systemNodeRole === "standalone") {
            document.getElementById("hardwareNodeGroup").style.display = "none";
        } else {
            document.getElementById("hardwareNodeRow").style.gridTemplateColumns = "1fr 1fr";
            document.getElementById("hardwareNodeGroup").parentElement.firstElementChild.style.gridColumn = "auto";
        }
    } catch (e) {
        console.error("Failed to fetch node role", e);
    }
}
fetchNodeRole();

async function fetchServices() {
    try {
        const data = await apiRequest(`${API_URL}/services`, {}, "Load services");
        renderServices(data);
    } catch (err) {
        console.error("Failed to fetch services", err);
    }
}

function appendQuery(url, params) {
    const entries = Object.entries(params).filter(([, value]) => value !== null && value !== undefined && value !== "");
    if (!entries.length) return url;
    const separator = url.includes("?") ? "&" : "?";
    return `${url}${separator}${entries.map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join("&")}`;
}

function normalizePath(path) {
    if (!path) return "";
    return path.startsWith("/") ? path : `/${path}`;
}

function buildFullSourceUrl(config, useBackup = false) {
    const protocol = (config.source_protocol || "srt").toLowerCase();
    const host = useBackup && config.backup_input_ip ? config.backup_input_ip : (config.source_ip || "0.0.0.0");
    const port = config.source_port || "";
    const base = `${protocol}://${host}${port ? `:${port}` : ""}`;

    if (protocol === "rtmp") return `${base}${normalizePath(config.source_path || "")}`;
    if (protocol === "srt") {
        return appendQuery(base, {
            mode: config.source_mode || "listener",
            latency: config.latency_ms,
            passphrase: config.passphrase,
            pbkeylen: config.pbkeylen,
            streamid: config.streamid,
            localaddr: config.local_bind_ip
        });
    }
    if (protocol === "udp") {
        return appendQuery(base, { localaddr: config.local_bind_ip });
    }
    return base;
}

function buildDestinationUrlFromFields() {
    const builder = document.getElementById("destinationBuilderProtocol").value;
    if (builder === "raw") return document.getElementById("destinationUrl").value;

    const host = document.getElementById("destinationHost").value.trim();
    const port = document.getElementById("destinationPort").value.trim();
    if (!host || !port) return document.getElementById("destinationUrl").value;

    if (builder === "rtmp") {
        const path = normalizePath(document.getElementById("destinationPath").value.trim());
        const key = document.getElementById("destinationKey").value.trim();
        return `rtmp://${host}:${port}${path}${key ? normalizePath(key) : ""}`;
    }

    return appendQuery(`srt://${host}:${port}`, {
        mode: document.getElementById("destinationMode").value || "caller",
        streamid: document.getElementById("destinationStreamid").value.trim(),
        passphrase: document.getElementById("destinationPassphrase").value.trim(),
        pbkeylen: document.getElementById("destinationPbkeylen").value
    });
}

function setDestinationBuilderVisibility() {
    const protocol = document.getElementById("destinationBuilderProtocol").value;
    const fields = document.getElementById("destinationBuilderFields");
    fields.style.display = protocol === "raw" ? "none" : "flex";

    document.querySelectorAll(".destination-rtmp-field").forEach(el => {
        el.style.display = protocol === "rtmp" ? "grid" : "none";
    });
    document.querySelectorAll(".destination-srt-field").forEach(el => {
        el.style.display = protocol === "srt" ? "grid" : "none";
    });
}

function populateDestinationBuilder(destinationUrl) {
    document.getElementById("destinationBuilderProtocol").value = "raw";
    document.getElementById("destinationHost").value = "";
    document.getElementById("destinationPort").value = "";
    document.getElementById("destinationPath").value = "";
    document.getElementById("destinationKey").value = "";
    document.getElementById("destinationMode").value = "caller";
    document.getElementById("destinationStreamid").value = "";
    document.getElementById("destinationPassphrase").value = "";
    document.getElementById("destinationPbkeylen").value = "";

    try {
        const url = new URL(destinationUrl);
        if (url.protocol === "rtmp:") {
            const parts = url.pathname.split("/").filter(Boolean);
            document.getElementById("destinationBuilderProtocol").value = "rtmp";
            document.getElementById("destinationHost").value = url.hostname;
            document.getElementById("destinationPort").value = url.port || "1935";
            document.getElementById("destinationPath").value = parts.length > 1 ? `/${parts.slice(0, -1).join("/")}` : url.pathname || "/live";
            document.getElementById("destinationKey").value = parts.length > 1 ? parts[parts.length - 1] : "";
        } else if (url.protocol === "srt:") {
            document.getElementById("destinationBuilderProtocol").value = "srt";
            document.getElementById("destinationHost").value = url.hostname;
            document.getElementById("destinationPort").value = url.port;
            document.getElementById("destinationMode").value = url.searchParams.get("mode") || "caller";
            document.getElementById("destinationStreamid").value = url.searchParams.get("streamid") || "";
            document.getElementById("destinationPassphrase").value = url.searchParams.get("passphrase") || "";
            document.getElementById("destinationPbkeylen").value = url.searchParams.get("pbkeylen") || "";
        }
    } catch {
        document.getElementById("destinationBuilderProtocol").value = "raw";
    }
    setDestinationBuilderVisibility();
}

function syncDestinationUrlPreview() {
    const builder = document.getElementById("destinationBuilderProtocol").value;
    if (builder !== "raw") document.getElementById("destinationUrl").value = buildDestinationUrlFromFields();
}

function serviceStatusLabel(status) {
    if (status === "pending_worker") return "pending worker";
    return status || "stopped";
}

function errorTagHtml(message, status) {
    if (!message) return "";
    const label = status === "pending_worker" ? "No eligible worker" : "Error";
    return `<button class="error-tag" type="button" title="${escapeHtml(message)}"><i class="fa-solid fa-triangle-exclamation"></i> ${escapeHtml(label)}</button>`;
}

function urlDisplayHtml(label, url) {
    const safeUrl = escapeHtml(url);
    return `
        <div class="url-line" title="${safeUrl}">
            <span class="url-label">${escapeHtml(label)}</span>
            <code>${safeUrl}</code>
            <button class="copy-mini" type="button" data-action="copy" data-copy="${safeUrl}" title="Copy ${escapeHtml(label)} URL">
                <i class="fa-solid fa-copy"></i>
            </button>
        </div>
    `;
}

function renderServices(services) {
    const tbody = document.getElementById("servicesList");

    if (services.length === 0) {
        tbody.innerHTML = `<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 40px;">No services configured. Click "New Service" to get started.</td></tr>`;
        return;
    }

    tbody.innerHTML = "";
    servicesMap = {};

    services.forEach(s => {
        servicesMap[s.config.id] = s;
        const c = s.config;
        const serviceId = escapeHtml(c.id);
        const previewIdPath = encodeURIComponent(c.id);
        const serviceName = escapeHtml(c.name);
        const statusClass = `status-${escapeHtml(s.status)}`;
        const statusLabel = escapeHtml(serviceStatusLabel(s.status));
        const activeInput = escapeHtml(s.active_input || "main");
        const sourceProtocol = escapeHtml((c.source_protocol || "").toUpperCase());
        const sourceMode = escapeHtml(c.source_mode || "");
        const fullSourceUrl = buildFullSourceUrl(c);
        const fullBackupSourceUrl = c.backup_input_ip ? buildFullSourceUrl(c, true) : "";
        const destinationUrl = c.destination_url || "";
        const targetNode = escapeHtml(c.target_node || "");
        const errorMsg = s.error_msg || "";

        let actionsHtml = "";
        if (s.status === "running") {
            actionsHtml = `<button class="btn-danger table-action" type="button" data-action="stop" data-id="${serviceId}" title="Stop"><i class="fa-solid fa-stop"></i></button>`;
            actionsHtml += `<button class="btn-secondary table-action" type="button" data-action="start" data-id="${serviceId}" data-use-backup="${s.active_input === "main"}" title="Manual Hot-Swap Input"><i class="fa-solid fa-rotate"></i> Feed</button>`;
        } else if (s.status === "stopped" || s.status === "error" || s.status === "pending_worker") {
            actionsHtml = `<button class="btn-primary table-action" type="button" data-action="start" data-id="${serviceId}"><i class="fa-solid fa-play"></i> Start</button>`;
        } else {
            actionsHtml = `<button class="btn-secondary table-action" type="button" disabled><i class="fa-solid fa-spinner fa-spin"></i> ${statusLabel}</button>`;
        }

        const encryptionText = c.pbkeylen && c.pbkeylen > 0 ? `<i class="fa-solid fa-lock" style="color:var(--accent);"></i> ${c.pbkeylen * 8}-bit` : `<i class="fa-solid fa-lock-open" style="color:var(--text-muted);"></i> None`;

        let nodeColor = c.target_node === "primary" ? "#5e6ad2" : (c.target_node === "backup" ? "#20c997" : "#e2e8f0");
        let hideNodeInfo = systemNodeRole === "standalone" ? `style="display:none;"` : "";

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>
                <div style="font-weight: 600; margin-bottom: 6px; font-size: 1rem;">${serviceName}</div>
                <span class="status-badge ${statusClass}" title="${escapeHtml(errorMsg)}">${statusLabel}</span>
                ${errorTagHtml(errorMsg, s.status)}
            </td>
            <td>
                <div style="font-weight: 600; color: var(--text-main); margin-bottom: 2px;">${sourceProtocol}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">${sourceMode}</div>
            </td>
            <td class="url-cell">
                ${urlDisplayHtml("Main", fullSourceUrl)}
                ${fullBackupSourceUrl ? urlDisplayHtml("Backup", fullBackupSourceUrl) : ""}
            </td>
            <td class="url-cell">
                ${urlDisplayHtml("Destination", destinationUrl)}
            </td>
            <td>
                <div class="status-badge" style="background: ${s.active_input === "main" ? "rgba(94,106,210,0.2)" : "rgba(32,201,151,0.2)"}; color: ${s.active_input === "main" ? "var(--primary)" : "var(--accent)"}; margin-bottom:6px;">${activeInput.toUpperCase()} FEED</div>
                <div ${hideNodeInfo} style="font-size: 0.7rem; font-weight:600; color: ${nodeColor}; margin-bottom:4px;"><i class="fa-solid fa-server"></i> ${targetNode.toUpperCase()} NODE</div>
                <div style="font-size: 0.75rem; color: var(--text-muted); font-weight:600;">${c.auto_failover ? '<i class="fa-solid fa-shield" style="color:var(--accent);"></i> Auto-Switch ON' : 'Manual Switch'} ${c.strict_probing ? '&bull; <span style="color:var(--danger);"><i class="fa-solid fa-magnifying-glass-chart"></i> Strict Watch</span>' : ''}</div>
            </td>
            <td>
                <div style="font-size: 0.85rem;">${encryptionText}</div>
            </td>
            <td class="td-video">
                <div class="td-video-inner">
                    ${s.status === "running" ? `
                        <img src="/previews/${previewIdPath}/preview.jpg?t=${Date.now()}" style="width:100%; height:100%; object-fit:cover;" onerror="this.onerror=null; this.src=''; this.parentElement.innerHTML='<div style=\\'color:var(--text-muted);font-size:0.75rem;\\'><i class=\\'fa-solid fa-spinner fa-spin\\'></i> Buffering...</div>';">
                    ` : `
                        <div style="color: rgba(255,255,255,0.1);"><i class="fa-solid fa-video-slash" style="font-size:1.5rem;"></i></div>
                    `}
                </div>
                ${c.enable_hls_preview ? `<div style="text-align:center; margin-top:8px;"><button class="copy-hls-btn" type="button" data-action="copy" data-copy="${escapeHtml(window.location.origin + `/previews/${previewIdPath}/stream.m3u8`)}" title="Copy HLS link"><i class="fa-solid fa-link"></i> Copy HLS Link</button></div>` : ""}
            </td>
            <td>
                <div class="td-actions">
                    ${actionsHtml}
                    ${systemNodeRole !== "standalone" ? `<button class="icon-btn table-action" type="button" style="margin-left: 12px; color: ${nodeColor};" data-action="swap" data-id="${serviceId}" title="Move Stream to Twin Hardware Node"><i class="fa-solid fa-server"></i> Move</button>` : ""}
                    <button class="icon-btn table-action" type="button" style="margin-left: 4px;" data-action="edit" data-id="${serviceId}" title="Edit Properties"><i class="fa-solid fa-gear"></i></button>
                    <button class="icon-btn delete table-action" type="button" data-action="delete" data-id="${serviceId}" title="Delete Pipeline"><i class="fa-solid fa-trash"></i></button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

async function copyText(text, button) {
    await navigator.clipboard.writeText(text);
    const previous = button.innerHTML;
    button.innerHTML = `<i class="fa-solid fa-check"></i>`;
    setTimeout(() => { button.innerHTML = previous; }, 1500);
}

async function handleTableAction(event) {
    const button = event.target.closest("button[data-action]");
    if (!button) return;
    const action = button.dataset.action;
    const id = button.dataset.id;

    if (action === "copy") {
        await copyText(button.dataset.copy || "", button);
        return;
    }

    if (!id) return;
    const original = button.innerHTML;
    try {
        if (action !== "edit" && action !== "delete") {
            button.disabled = true;
            button.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i>`;
        }

        if (action === "edit") {
            editService(id);
        } else if (action === "delete") {
            await deleteService(id, button);
        } else if (action === "start") {
            await startService(id, button.dataset.useBackup === "true");
        } else if (action === "stop") {
            await stopService(id);
        } else if (action === "swap") {
            await swapNode(id);
        }
    } catch (err) {
        console.error(err);
        alert(err.message);
    } finally {
        if (button.isConnected) {
            button.disabled = false;
            button.innerHTML = original;
        }
    }
}

document.getElementById("servicesList").addEventListener("click", handleTableAction);
setInterval(fetchServices, 4000);
fetchServices();

async function swapNode(id) {
    const service = servicesMap[id];
    if (!service) throw new Error("Service data is not loaded yet.");
    const payload = { ...service.config };
    if (payload.target_node === "primary") payload.target_node = "backup";
    else if (payload.target_node === "backup") payload.target_node = "all";
    else payload.target_node = "primary";

    await apiRequest(`${API_URL}/services/${id}`, {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
    }, "Move service");
    await fetchServices();
}

function openModal(id) {
    document.getElementById(id).classList.add("active");
}

function closeModal(id) {
    document.getElementById(id).classList.remove("active");
    document.getElementById("serviceForm").reset();
    document.getElementById("serviceId").value = "";
    document.getElementById("modalTitle").innerText = "Create New Service";
    document.getElementById("advancedOptions").style.display = "none";
    populateDestinationBuilder("");
}

document.getElementById("destinationBuilderProtocol").addEventListener("change", () => {
    setDestinationBuilderVisibility();
    syncDestinationUrlPreview();
});

[
    "destinationHost",
    "destinationPort",
    "destinationPath",
    "destinationKey",
    "destinationMode",
    "destinationStreamid",
    "destinationPassphrase",
    "destinationPbkeylen"
].forEach(id => document.getElementById(id).addEventListener("input", syncDestinationUrlPreview));

document.getElementById("serviceForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("serviceId").value;
    const isEdit = !!id;

    let keylenParsed = parseInt(document.getElementById("pbkeylen").value, 10);

    const payload = {
        id: id || "",
        name: document.getElementById("serviceName").value,
        source_protocol: document.getElementById("sourceProtocol").value,
        source_mode: document.getElementById("sourceMode").value,
        source_ip: document.getElementById("sourceIp").value || "0.0.0.0",
        source_port: parseInt(document.getElementById("sourcePort").value, 10),
        source_path: document.getElementById("sourcePath").value,
        destination_url: buildDestinationUrlFromFields(),

        target_node: document.getElementById("targetNode").value,

        local_bind_ip: document.getElementById("localBindIp").value || null,
        node_bindings: isEdit ? (servicesMap[id].config.node_bindings || {}) : {},
        latency_ms: document.getElementById("latencyMs").value ? parseInt(document.getElementById("latencyMs").value, 10) : null,
        passphrase: document.getElementById("passphrase").value || null,
        pbkeylen: keylenParsed !== 0 ? keylenParsed : null,
        streamid: document.getElementById("streamid").value || null,

        backup_input_ip: document.getElementById("backupInputIp").value || null,
        auto_failover: document.getElementById("autoFailover").checked,
        strict_probing: document.getElementById("strictProbing").checked,
        enable_hls_preview: document.getElementById("enableHlsPreview").checked,

        enabled: true
    };

    try {
        const method = isEdit ? "PUT" : "POST";
        const url = isEdit ? `${API_URL}/services/${id}` : `${API_URL}/services`;

        await apiRequest(url, {
            method,
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        }, "Save service");

        closeModal("createModal");
        await fetchServices();
    } catch (err) {
        console.error(err);
        alert(err.message);
    }
});

function editService(id) {
    const s = servicesMap[id];
    if (!s) {
        alert("Service data is not loaded yet. Refreshing the list now.");
        fetchServices();
        return;
    }
    document.getElementById("modalTitle").innerText = "Edit Service Properties";
    document.getElementById("serviceId").value = s.config.id;
    document.getElementById("serviceName").value = s.config.name;
    document.getElementById("sourceProtocol").value = s.config.source_protocol || "srt";
    document.getElementById("sourceMode").value = s.config.source_mode || "listener";
    document.getElementById("sourceIp").value = s.config.source_ip || "0.0.0.0";
    document.getElementById("sourcePort").value = s.config.source_port;
    document.getElementById("sourcePath").value = s.config.source_path || "";
    document.getElementById("destinationUrl").value = s.config.destination_url;

    document.getElementById("targetNode").value = s.config.target_node || "worker_1";

    document.getElementById("localBindIp").value = s.config.local_bind_ip || "";
    document.getElementById("latencyMs").value = s.config.latency_ms || "";
    document.getElementById("passphrase").value = s.config.passphrase || "";
    document.getElementById("pbkeylen").value = s.config.pbkeylen || "0";
    document.getElementById("streamid").value = s.config.streamid || "";

    document.getElementById("backupInputIp").value = s.config.backup_input_ip || "";
    document.getElementById("autoFailover").checked = s.config.auto_failover || false;
    document.getElementById("strictProbing").checked = s.config.strict_probing || false;
    document.getElementById("enableHlsPreview").checked = s.config.enable_hls_preview || false;
    populateDestinationBuilder(s.config.destination_url || "");

    openModal("createModal");
}

async function deleteService(id) {
    const service = servicesMap[id];
    const name = service?.config?.name || "this routing pipeline";
    if (!confirm(`Delete ${name}?`)) return;
    await apiRequest(`${API_URL}/services/${id}`, { method: "DELETE" }, "Delete service");
    await fetchServices();
}

async function startService(id, useBackup = false) {
    await apiRequest(`${API_URL}/services/${id}/start?use_backup=${useBackup}`, { method: "POST" }, "Start service");
    await fetchServices();
}

async function stopService(id) {
    await apiRequest(`${API_URL}/services/${id}/stop`, { method: "POST" }, "Stop service");
    await fetchServices();
}
