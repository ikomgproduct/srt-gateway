const API_URL = window.location.origin + "/api";
let servicesMap = {};
let systemNodeRole = "primary";
let interfaceInventory = [
    { id: "primary-video-main", label: "Primary Video Main", ip: "10.70.15.3", node_roles: ["primary"], directions: ["input", "output"], network: "video" },
    { id: "backup-video-backup", label: "Backup Video Backup", ip: "10.71.15.3", node_roles: ["backup"], directions: ["input", "output"], network: "video" }
];

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

async function fetchInterfaces() {
    try {
        const data = await apiRequest(`${API_URL}/interfaces`, {}, "Load interfaces");
        if (Array.isArray(data.interfaces) && data.interfaces.length) {
            interfaceInventory = data.interfaces;
        }
    } catch (e) {
        console.error("Failed to fetch interface inventory", e);
    } finally {
        populateAllInterfaceSelects();
    }
}
fetchInterfaces();

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

function getHlsOutputs(config = {}) {
    const outputs = config.hls_outputs || {};
    return {
        low_res: {
            enabled: !!(config.enable_hls_preview || outputs.low_res?.enabled),
            buffer_seconds: outputs.low_res?.buffer_seconds || 10
        },
        full_res: {
            enabled: !!outputs.full_res?.enabled,
            buffer_seconds: outputs.full_res?.buffer_seconds || 3600
        }
    };
}

function hasAnyHlsOutput(config = {}) {
    const outputs = getHlsOutputs(config);
    return outputs.low_res.enabled || outputs.full_res.enabled;
}

function buildFullSourceUrl(config, useBackup = false) {
    const protocol = (config.source_protocol || "srt").toLowerCase();
    if (protocol === "hls") return config.source_url || "";

    const inputBind = getEffectiveInputBind(config);
    let host = useBackup && config.backup_input_ip ? config.backup_input_ip : (config.source_ip || "0.0.0.0");
    const port = config.source_port || "";
    if (inputBind && protocol === "srt" && (config.source_mode || "listener") === "listener") host = inputBind;
    const base = `${protocol}://${host}${port ? `:${port}` : ""}`;

    if (protocol === "rtmp") return `${base}${normalizePath(config.source_path || "")}`;
    if (protocol === "srt") {
        return appendQuery(base, {
            mode: config.source_mode || "listener",
            latency: config.latency_ms,
            passphrase: config.passphrase,
            pbkeylen: config.pbkeylen,
            streamid: config.streamid,
            localaddr: (config.source_mode || "listener") === "caller" ? inputBind : ""
        });
    }
    if (protocol === "udp") {
        return appendQuery(base, { localaddr: inputBind });
    }
    return base;
}

function getNodeBinding(config, role) {
    return (config.node_bindings && config.node_bindings[role]) || {};
}

function getExplicitInputBind(config, role = config.target_node) {
    const binding = getNodeBinding(config, role);
    return binding.input_bind_ip || binding.local_bind_ip || "";
}

function getExplicitOutputBind(config, role = config.target_node) {
    const binding = getNodeBinding(config, role);
    return binding.output_bind_ip || binding.local_bind_ip || "";
}

function getEffectiveInputBind(config, role = config.target_node) {
    return getExplicitInputBind(config, role) || config.local_bind_ip || "";
}

function getEffectiveOutputBind(config, role = config.target_node) {
    return getExplicitOutputBind(config, role) || config.local_bind_ip || "";
}

function buildNodeBindingsFromForm(existing = {}) {
    const bindings = { ...existing };
    [
        ["primary", "primaryInputBindIp", "primaryOutputBindIp"],
        ["backup", "backupNodeInputBindIp", "backupNodeOutputBindIp"]
    ].forEach(([role, inputId, outputId]) => {
        const inputBind = document.getElementById(inputId).value.trim();
        const outputBind = document.getElementById(outputId).value.trim();
        const previous = bindings[role] || {};
        if (inputBind || outputBind || previous.local_bind_ip) {
            bindings[role] = {
                ...previous,
                input_bind_ip: inputBind || null,
                output_bind_ip: outputBind || null
            };
        } else {
            delete bindings[role];
        }
    });
    return bindings;
}

function interfaceLabel(item) {
    return `${item.label || item.id || item.ip} (${item.ip})`;
}

function matchingInterfaces(role, direction) {
    return interfaceInventory.filter(item => {
        const roles = item.node_roles || [];
        const directions = item.directions || [];
        return roles.includes(role) && directions.includes(direction);
    });
}

function populateInterfaceSelect(selectId, role, direction, selectedIp = "") {
    const select = document.getElementById(selectId);
    const options = matchingInterfaces(role, direction);
    select.innerHTML = "";

    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "Default / not bound";
    select.appendChild(emptyOption);

    options.forEach(item => {
        const option = document.createElement("option");
        option.value = item.ip;
        option.textContent = interfaceLabel(item);
        select.appendChild(option);
    });

    if (selectedIp && !options.some(item => item.ip === selectedIp)) {
        const preserved = document.createElement("option");
        preserved.value = selectedIp;
        preserved.textContent = `Existing interface (${selectedIp})`;
        select.appendChild(preserved);
    }

    select.value = selectedIp || "";
}

function populateAllInterfaceSelects(config = {}) {
    populateInterfaceSelect("primaryInputBindIp", "primary", "input", getExplicitInputBind(config, "primary"));
    populateInterfaceSelect("primaryOutputBindIp", "primary", "output", getExplicitOutputBind(config, "primary"));
    populateInterfaceSelect("backupNodeInputBindIp", "backup", "input", getExplicitInputBind(config, "backup"));
    populateInterfaceSelect("backupNodeOutputBindIp", "backup", "output", getExplicitOutputBind(config, "backup"));
}

function populateBindingFields(config) {
    populateAllInterfaceSelects(config);
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

    if (builder === "udp") {
        return appendQuery(`udp://${host}:${port}`, {
            ttl: document.getElementById("destinationTtl").value,
            pkt_size: document.getElementById("destinationPktSize").value
        });
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
    document.querySelectorAll(".destination-udp-field").forEach(el => {
        el.style.display = protocol === "udp" ? "grid" : "none";
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
    document.getElementById("destinationTtl").value = "";
    document.getElementById("destinationPktSize").value = "";

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
        } else if (url.protocol === "udp:") {
            document.getElementById("destinationBuilderProtocol").value = "udp";
            document.getElementById("destinationHost").value = url.hostname;
            document.getElementById("destinationPort").value = url.port;
            document.getElementById("destinationTtl").value = url.searchParams.get("ttl") || "";
            document.getElementById("destinationPktSize").value = url.searchParams.get("pkt_size") || "";
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

function setSourceProtocolVisibility() {
    const protocol = document.getElementById("sourceProtocol").value;
    const isHls = protocol === "hls";

    document.querySelectorAll(".source-network-field").forEach(el => {
        el.style.display = isHls ? "none" : "";
    });
    document.querySelectorAll(".source-hls-field").forEach(el => {
        el.style.display = isHls ? "flex" : "none";
    });
    document.querySelectorAll(".source-rtmp-field").forEach(el => {
        el.style.display = protocol === "rtmp" ? "flex" : "none";
    });

    document.getElementById("sourceIp").required = !isHls;
    document.getElementById("sourcePort").required = !isHls;
    document.getElementById("sourceUrl").required = isHls;
}

function setHlsControlVisibility() {
    const fullEnabled = document.getElementById("enableFullHls").checked;
    document.getElementById("fullHlsBufferRow").style.display = fullEnabled ? "grid" : "none";
}

function syncDestinationRequired() {
    const hlsEnabled = document.getElementById("enableHlsPreview").checked || document.getElementById("enableFullHls").checked;
    document.getElementById("destinationUrl").required = !hlsEnabled;
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

function hlsOutputLinksHtml(config, previewIdPath) {
    const outputs = getHlsOutputs(config);
    const links = [];
    if (outputs.low_res.enabled) {
        links.push(["Low HLS", `/previews/${previewIdPath}/low_res/stream.m3u8`]);
    }
    if (outputs.full_res.enabled) {
        links.push(["Full HLS", `/previews/${previewIdPath}/full_res/stream.m3u8`]);
    }
    return links.map(([label, path]) => `
        <button class="copy-hls-btn" type="button" data-action="copy" data-copy="${escapeHtml(window.location.origin + path)}" title="Copy ${escapeHtml(label)} HLS link">
            <i class="fa-solid fa-link"></i> ${escapeHtml(label)}
        </button>
    `).join("");
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
        const hlsLinksHtml = hlsOutputLinksHtml(c, previewIdPath);
        const targetNode = escapeHtml(c.target_node || "");
        const inputBind = escapeHtml(getEffectiveInputBind(c));
        const outputBind = escapeHtml(getEffectiveOutputBind(c));
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
                ${destinationUrl ? urlDisplayHtml("Destination", destinationUrl) : `<span style="color:var(--text-muted);font-size:0.78rem;">HLS local output only</span>`}
            </td>
            <td>
                <div class="status-badge" style="background: ${s.active_input === "main" ? "rgba(94,106,210,0.2)" : "rgba(32,201,151,0.2)"}; color: ${s.active_input === "main" ? "var(--primary)" : "var(--accent)"}; margin-bottom:6px;">${activeInput.toUpperCase()} FEED</div>
                <div ${hideNodeInfo} style="font-size: 0.7rem; font-weight:600; color: ${nodeColor}; margin-bottom:4px;"><i class="fa-solid fa-server"></i> ${targetNode.toUpperCase()} NODE</div>
                ${(inputBind || outputBind) ? `<div class="binding-summary" title="Target node binding. Active owner may differ during failover. Input: ${inputBind || "default"} | Output: ${outputBind || "default"}"><i class="fa-solid fa-network-wired"></i> TARGET IN ${inputBind || "default"} / OUT ${outputBind || "default"}</div>` : ""}
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
                ${hlsLinksHtml ? `<div class="hls-link-list">${hlsLinksHtml}</div>` : ""}
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
    populateBindingFields({});
    setSourceProtocolVisibility();
    setHlsControlVisibility();
    syncDestinationRequired();
}

document.getElementById("sourceProtocol").addEventListener("change", setSourceProtocolVisibility);
document.getElementById("enableFullHls").addEventListener("change", setHlsControlVisibility);
document.getElementById("enableHlsPreview").addEventListener("change", syncDestinationRequired);
document.getElementById("enableFullHls").addEventListener("change", syncDestinationRequired);

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
    "destinationPbkeylen",
    "destinationTtl",
    "destinationPktSize"
].forEach(id => document.getElementById(id).addEventListener("input", syncDestinationUrlPreview));

document.getElementById("serviceForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("serviceId").value;
    const isEdit = !!id;

    let keylenParsed = parseInt(document.getElementById("pbkeylen").value, 10);

    const existingBindings = isEdit ? (servicesMap[id].config.node_bindings || {}) : {};
    const sourceProtocol = document.getElementById("sourceProtocol").value;
    const sourcePortValue = document.getElementById("sourcePort").value;
    const lowResHlsEnabled = document.getElementById("enableHlsPreview").checked;
    const fullHlsEnabled = document.getElementById("enableFullHls").checked;
    const destinationUrl = buildDestinationUrlFromFields();
    if (!destinationUrl && !lowResHlsEnabled && !fullHlsEnabled) {
        alert("Destination URL is required unless Low-Res or Full HLS output is enabled.");
        return;
    }

    const payload = {
        id: id || "",
        name: document.getElementById("serviceName").value,
        source_protocol: sourceProtocol,
        source_mode: document.getElementById("sourceMode").value,
        source_ip: document.getElementById("sourceIp").value || "0.0.0.0",
        source_port: sourceProtocol === "hls" ? null : parseInt(sourcePortValue, 10),
        source_path: document.getElementById("sourcePath").value,
        source_url: document.getElementById("sourceUrl").value || null,
        destination_url: destinationUrl,

        target_node: document.getElementById("targetNode").value,

        local_bind_ip: document.getElementById("localBindIp").value || null,
        node_bindings: buildNodeBindingsFromForm(existingBindings),
        latency_ms: document.getElementById("latencyMs").value ? parseInt(document.getElementById("latencyMs").value, 10) : null,
        passphrase: document.getElementById("passphrase").value || null,
        pbkeylen: keylenParsed !== 0 ? keylenParsed : null,
        streamid: document.getElementById("streamid").value || null,

        backup_input_ip: document.getElementById("backupInputIp").value || null,
        auto_failover: document.getElementById("autoFailover").checked,
        strict_probing: document.getElementById("strictProbing").checked,
        enable_hls_preview: lowResHlsEnabled,
        hls_outputs: {
            low_res: {
                enabled: lowResHlsEnabled,
                buffer_seconds: 10
            },
            full_res: {
                enabled: fullHlsEnabled,
                buffer_seconds: Math.min(24, Math.max(1, parseInt(document.getElementById("fullHlsBufferHours").value, 10) || 1)) * 3600
            }
        },

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
    document.getElementById("sourcePort").value = s.config.source_port || "";
    document.getElementById("sourcePath").value = s.config.source_path || "";
    document.getElementById("sourceUrl").value = s.config.source_url || "";
    document.getElementById("destinationUrl").value = s.config.destination_url || "";

    document.getElementById("targetNode").value = ["primary", "backup", "all"].includes(s.config.target_node) ? s.config.target_node : "primary";

    document.getElementById("localBindIp").value = s.config.local_bind_ip || "";
    populateBindingFields(s.config);
    document.getElementById("latencyMs").value = s.config.latency_ms || "";
    document.getElementById("passphrase").value = s.config.passphrase || "";
    document.getElementById("pbkeylen").value = s.config.pbkeylen || "0";
    document.getElementById("streamid").value = s.config.streamid || "";

    document.getElementById("backupInputIp").value = s.config.backup_input_ip || "";
    document.getElementById("autoFailover").checked = s.config.auto_failover || false;
    document.getElementById("strictProbing").checked = s.config.strict_probing || false;
    const hlsOutputs = getHlsOutputs(s.config);
    document.getElementById("enableHlsPreview").checked = hlsOutputs.low_res.enabled;
    document.getElementById("enableFullHls").checked = hlsOutputs.full_res.enabled;
    document.getElementById("fullHlsBufferHours").value = Math.max(1, Math.ceil((hlsOutputs.full_res.buffer_seconds || 3600) / 3600));
    populateDestinationBuilder(s.config.destination_url || "");
    setSourceProtocolVisibility();
    setHlsControlVisibility();
    syncDestinationRequired();

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

setSourceProtocolVisibility();
setHlsControlVisibility();
syncDestinationRequired();
