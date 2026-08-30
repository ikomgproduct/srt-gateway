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
    if (!select) return;
    const options = matchingInterfaces(role, direction);
    select.innerHTML = "";

    const emptyOption = document.createElement("option");
    emptyOption.value = "";
    emptyOption.textContent = "Default / not bound";
    select.appendChild(emptyOption);

    options.forEach(item => {
        const option = document.createElement("option");
        option.value = item.ip;
        option.dataset.interfaceId = item.id || "";
        option.textContent = interfaceLabel(item);
        select.appendChild(option);
    });

    if (selectedIp && !options.some(item => item.ip === selectedIp)) {
        const preserved = document.createElement("option");
        preserved.value = selectedIp;
        preserved.dataset.interfaceId = "";
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
    populateRouteEndpointSelects(config);
}

function populateBindingFields(config) {
    populateAllInterfaceSelects(config);
}

function getSelectedInterface(selectId) {
    const select = document.getElementById(selectId);
    if (!select) return { bind_ip: null, interface_id: null };
    const selected = select.options[select.selectedIndex];
    return {
        bind_ip: select.value || null,
        interface_id: selected?.dataset?.interfaceId || null
    };
}

function parseOptionalInt(id) {
    const value = document.getElementById(id)?.value;
    if (value === undefined || value === null || value === "") return null;
    const parsed = parseInt(value, 10);
    return Number.isNaN(parsed) ? null : parsed;
}

function compactObject(value) {
    const output = {};
    Object.entries(value).forEach(([key, item]) => {
        if (item !== null && item !== undefined && item !== "") output[key] = item;
    });
    return output;
}

function buildRouteEndpointFromForm(prefix) {
    const fieldMap = {
        source: {
            interfaceId: "sourceInterface",
            addressId: "sourceIp",
            portId: "sourcePort"
        },
        destination: {
            interfaceId: "destinationInterface",
            addressId: "destinationHost",
            portId: "destinationPort"
        },
        destinationSecondary: {
            interfaceId: "destinationSecondaryInterface",
            addressId: "destinationSecondaryHost",
            portId: "destinationSecondaryPort"
        }
    };
    const fields = fieldMap[prefix];
    const selectedInterface = getSelectedInterface(fields.interfaceId);
    return compactObject({
        interface_id: selectedInterface.interface_id,
        bind_ip: selectedInterface.bind_ip,
        address: document.getElementById(fields.addressId).value.trim() || "0.0.0.0",
        port: parseOptionalInt(fields.portId)
    });
}

function hydrateRouteEndpoint(prefix, endpoint = {}, fallback = {}) {
    const fieldMap = {
        source: {
            interfaceId: "sourceInterface",
            role: "primary",
            direction: "input",
            addressId: "sourceIp",
            portId: "sourcePort"
        },
        destination: {
            interfaceId: "destinationInterface",
            role: "primary",
            direction: "output",
            addressId: "destinationHost",
            portId: "destinationPort"
        },
        destinationSecondary: {
            interfaceId: "destinationSecondaryInterface",
            role: "backup",
            direction: "output",
            addressId: "destinationSecondaryHost",
            portId: "destinationSecondaryPort"
        }
    };
    const fields = fieldMap[prefix];
    const bindIp = endpoint.bind_ip || fallback.bind_ip || "";
    populateInterfaceSelect(fields.interfaceId, fields.role, fields.direction, bindIp);
    document.getElementById(fields.addressId).value = endpoint.address || fallback.address || "";
    document.getElementById(fields.portId).value = endpoint.port || fallback.port || "";
}

function populateRouteEndpointSelects(config = {}) {
    const sourceEndpoint = config.source?.primary_endpoint || {};
    const destination = firstEnabledDestination(config.destinations || []) || {};
    const destinationEndpoint = destination.primary_endpoint || {};
    const secondaryEndpoint = destination.path_redundancy?.secondary_endpoint || {};
    populateInterfaceSelect("sourceInterface", "primary", "input", sourceEndpoint.bind_ip || getExplicitInputBind(config, "primary"));
    populateInterfaceSelect("destinationInterface", "primary", "output", destinationEndpoint.bind_ip || getExplicitOutputBind(config, "primary"));
    populateInterfaceSelect("destinationSecondaryInterface", "backup", "output", secondaryEndpoint.bind_ip || getExplicitOutputBind(config, "backup"));
}

function buildStreamIdConfig(scope) {
    const mode = document.getElementById(`${scope}StreamIdMode`).value;
    if (mode === "custom") {
        return compactObject({
            mode,
            custom_value: document.getElementById(`${scope}StreamIdCustomValue`).value.trim()
        });
    }
    return compactObject({
        mode: "default",
        host_mode: document.getElementById(`${scope}StreamIdHostMode`).value || "publish",
        resource_name: document.getElementById(`${scope}StreamIdResourceName`).value.trim(),
        username: document.getElementById(`${scope}StreamIdUsername`).value.trim()
    });
}

function hydrateStreamIdConfig(scope, srtParams = {}, legacyStreamid = "") {
    const streamId = srtParams.stream_id || (legacyStreamid ? { mode: "custom", custom_value: legacyStreamid } : { mode: "default" });
    document.getElementById(`${scope}StreamIdMode`).value = streamId.mode || "default";
    document.getElementById(`${scope}StreamIdHostMode`).value = streamId.host_mode || "publish";
    document.getElementById(`${scope}StreamIdResourceName`).value = streamId.resource_name || "";
    document.getElementById(`${scope}StreamIdUsername`).value = streamId.username || "";
    document.getElementById(`${scope}StreamIdCustomValue`).value = streamId.custom_value || "";
}

function buildSrtParametersFromForm(scope) {
    const streamId = buildStreamIdConfig(scope);
    const params = compactObject({
        latency_ms: parseOptionalInt(`${scope}LatencyMs`),
        receive_buffer_bytes: scope === "source" ? parseOptionalInt("sourceReceiveBufferBytes") : null,
        retransmission_bandwidth_kbps: scope === "destination" ? parseOptionalInt("destinationRetransmissionBandwidthKbps") : null,
        passphrase: document.getElementById(`${scope}Passphrase`).value.trim(),
        stream_id: streamId
    });
    return Object.keys(params).length ? params : null;
}

function buildLinkParametersFromForm(scope) {
    if (scope === "source") {
        return compactObject({
            ttl: parseOptionalInt("sourceTtl"),
            mtu: parseOptionalInt("sourceMtu")
        });
    }
    return compactObject({
        ttl: parseOptionalInt("destinationTtl"),
        mtu: parseOptionalInt("destinationMtu"),
        tos: document.getElementById("destinationTos").value.trim(),
        max_bitrate_kbps: parseOptionalInt("destinationMaxBitrateKbps")
    });
}

function buildSourceConfigFromForm() {
    const protocol = document.getElementById("sourceProtocol").value;
    if (protocol === "hls") {
        return compactObject({
            protocol,
            url: document.getElementById("sourceUrl").value.trim(),
            path: ""
        });
    }

    const source = compactObject({
        protocol,
        mode: protocol === "srt" || protocol === "rtmp" || protocol === "rist" ? document.getElementById("sourceMode").value : null,
        type: protocol === "udp" ? document.getElementById("sourceUdpType").value : null,
        primary_endpoint: buildRouteEndpointFromForm("source"),
        path: protocol === "rtmp" ? document.getElementById("sourcePath").value.trim() : "",
        link_parameters: protocol === "udp" ? buildLinkParametersFromForm("source") : null,
        srt: protocol === "srt" ? buildSrtParametersFromForm("source") : null
    });
    return source;
}

function firstEnabledDestination(destinations = []) {
    return destinations.find(item => item && item.enabled !== false) || null;
}

function resetTargetNodeOptions() {
    document.querySelectorAll("#targetNode option[data-legacy-target='true']").forEach(option => option.remove());
}

function setTargetNodeForCreate() {
    resetTargetNodeOptions();
    document.getElementById("targetNode").value = "primary";
}

function setTargetNodeForEdit(targetNode) {
    resetTargetNodeOptions();
    const select = document.getElementById("targetNode");
    const supportedTargets = ["primary", "backup", "all"];
    if (!targetNode || supportedTargets.includes(targetNode)) {
        select.value = targetNode || "primary";
        return;
    }

    const legacyOption = document.createElement("option");
    legacyOption.value = targetNode;
    legacyOption.dataset.legacyTarget = "true";
    legacyOption.textContent = `Existing legacy ${targetNode}`;
    select.appendChild(legacyOption);
    select.value = targetNode;
}

function buildPathRedundancyFromForm() {
    const enabled = document.getElementById("pathRedundancyEnabled").checked;
    if (!enabled) return { enabled: false, mode: "none", secondary_endpoint: null };
    return {
        enabled: true,
        mode: "manual",
        secondary_endpoint: buildRouteEndpointFromForm("destinationSecondary")
    };
}

function buildRtmpDestinationUrl(protocol) {
    const host = document.getElementById("destinationHost").value.trim();
    const port = document.getElementById("destinationPort").value.trim();
    if (!host || !port) return "";
    const path = normalizePath(document.getElementById("destinationPath").value.trim() || "/live");
    const key = document.getElementById("destinationKey").value.trim();
    return `${protocol}://${host}:${port}${path}${key ? normalizePath(key) : ""}`;
}

function buildDestinationUrlFromFields() {
    const builder = document.getElementById("destinationBuilderProtocol").value;
    if (!document.getElementById("normalDestinationEnabled").checked) return "";
    if (builder === "raw") return document.getElementById("destinationUrl").value.trim();

    const host = document.getElementById("destinationHost").value.trim();
    const port = document.getElementById("destinationPort").value.trim();
    if (!host || !port) return document.getElementById("destinationUrl").value;

    if (builder === "rtmp" || builder === "rtmps") {
        return buildRtmpDestinationUrl(builder);
    }

    if (builder === "udp") {
        return appendQuery(`udp://${host}:${port}`, {
            ttl: document.getElementById("destinationTtl").value
        });
    }

    if (builder === "rist") return `rist://${host}:${port}`;

    return appendQuery(`srt://${host}:${port}`, {
        mode: document.getElementById("destinationMode").value || "caller",
        streamid: document.getElementById("destinationStreamIdMode").value === "custom" ? document.getElementById("destinationStreamIdCustomValue").value.trim() : "",
        passphrase: document.getElementById("destinationPassphrase").value.trim(),
        pbkeylen: document.getElementById("pbkeylen").value !== "0" ? document.getElementById("pbkeylen").value : ""
    });
}

function buildDestinationConfigFromForm() {
    if (!document.getElementById("normalDestinationEnabled").checked) return [];
    const protocol = document.getElementById("destinationBuilderProtocol").value;
    if (protocol === "raw") {
        return [compactObject({
            protocol: "raw",
            url: document.getElementById("destinationUrl").value.trim(),
            enabled: true
        })];
    }
    const destination = compactObject({
        protocol,
        mode: protocol === "srt" ? document.getElementById("destinationMode").value : null,
        type: protocol === "udp" ? document.getElementById("destinationUdpType").value : null,
        primary_endpoint: buildRouteEndpointFromForm("destination"),
        path_redundancy: protocol === "srt" ? buildPathRedundancyFromForm() : null,
        link_parameters: protocol === "udp" ? buildLinkParametersFromForm("destination") : null,
        srt: protocol === "srt" ? buildSrtParametersFromForm("destination") : null,
        url: protocol === "rtmp" || protocol === "rtmps" ? buildRtmpDestinationUrl(protocol) : null,
        enabled: true
    });
    return [destination];
}

function buildLegacyFieldsFromStructured(source, destinations) {
    const sourceEndpoint = source.primary_endpoint || {};
    const sourceSrt = source.srt || {};
    const sourceStreamId = sourceSrt.stream_id || {};
    const legacyStreamId = source.protocol === "srt" && sourceStreamId.mode === "custom"
        ? sourceStreamId.custom_value
        : null;
    return {
        source_protocol: source.protocol,
        source_mode: source.mode || "listener",
        source_ip: source.protocol === "hls" ? "0.0.0.0" : (sourceEndpoint.address || "0.0.0.0"),
        source_port: source.protocol === "hls" ? null : sourceEndpoint.port,
        source_path: source.path || "",
        source_url: source.protocol === "hls" ? (source.url || null) : null,
        destination_url: buildDestinationUrlFromFields(),
        latency_ms: sourceSrt.latency_ms || null,
        passphrase: sourceSrt.passphrase || null,
        streamid: legacyStreamId || null
    };
}

function setRouteEditorVisibility() {
    const sourceProtocol = document.getElementById("sourceProtocol").value;
    const destinationProtocol = document.getElementById("destinationBuilderProtocol").value;
    const normalDestinationEnabled = document.getElementById("normalDestinationEnabled").checked;
    const sourceIsHls = sourceProtocol === "hls";

    document.querySelectorAll(".source-network-field").forEach(el => {
        el.style.display = sourceIsHls ? "none" : "";
    });
    document.querySelectorAll(".source-hls-field").forEach(el => {
        el.style.display = sourceIsHls ? "flex" : "none";
    });
    document.querySelectorAll(".source-srt-field").forEach(el => {
        el.style.display = sourceProtocol === "srt" ? "block" : "none";
    });
    document.querySelectorAll(".source-udp-field").forEach(el => {
        el.style.display = sourceProtocol === "udp" ? "" : "none";
    });
    document.querySelectorAll(".source-rtmp-field").forEach(el => {
        el.style.display = sourceProtocol === "rtmp" ? "flex" : "none";
    });
    document.querySelectorAll(".source-mode-field").forEach(el => {
        el.style.display = ["srt", "rtmp", "rist"].includes(sourceProtocol) ? "flex" : "none";
    });

    document.getElementById("sourceIp").required = !sourceIsHls;
    document.getElementById("sourcePort").required = !sourceIsHls;
    document.getElementById("sourceUrl").required = sourceIsHls;

    document.getElementById("normalDestinationFields").style.display = normalDestinationEnabled ? "block" : "none";
    document.querySelectorAll(".destination-raw-field").forEach(el => {
        el.style.display = normalDestinationEnabled && destinationProtocol === "raw" ? "flex" : "none";
    });
    document.querySelectorAll(".destination-endpoint-field").forEach(el => {
        el.style.display = normalDestinationEnabled && destinationProtocol !== "raw" ? "grid" : "none";
    });
    document.querySelectorAll(".destination-rtmp-field").forEach(el => {
        el.style.display = normalDestinationEnabled && ["rtmp", "rtmps"].includes(destinationProtocol) ? "" : "none";
    });
    document.querySelectorAll(".destination-srt-field").forEach(el => {
        el.style.display = normalDestinationEnabled && destinationProtocol === "srt" ? "" : "none";
    });
    document.querySelectorAll(".destination-udp-field").forEach(el => {
        el.style.display = normalDestinationEnabled && destinationProtocol === "udp" ? "" : "none";
    });
    document.querySelectorAll(".path-redundancy-field").forEach(el => {
        el.style.display = normalDestinationEnabled && destinationProtocol === "srt" && document.getElementById("pathRedundancyEnabled").checked ? "" : "none";
    });
    document.querySelectorAll(".source-stream-default-field").forEach(el => {
        el.style.display = document.getElementById("sourceStreamIdMode").value === "default" ? "block" : "none";
    });
    document.querySelectorAll(".source-stream-custom-field").forEach(el => {
        el.style.display = document.getElementById("sourceStreamIdMode").value === "custom" ? "flex" : "none";
    });
    document.querySelectorAll(".destination-stream-default-field").forEach(el => {
        el.style.display = document.getElementById("destinationStreamIdMode").value === "default" ? "block" : "none";
    });
    document.querySelectorAll(".destination-stream-custom-field").forEach(el => {
        el.style.display = document.getElementById("destinationStreamIdMode").value === "custom" ? "flex" : "none";
    });
    syncDestinationRequired();
}

function populateDestinationBuilder(destinationUrl = "") {
    document.getElementById("destinationHost").value = "";
    document.getElementById("destinationPort").value = "";
    document.getElementById("destinationPath").value = "";
    document.getElementById("destinationKey").value = "";
    document.getElementById("destinationMode").value = "caller";
    document.getElementById("destinationUdpType").value = "unicast";
    document.getElementById("destinationPassphrase").value = "";
    document.getElementById("destinationLatencyMs").value = "";
    document.getElementById("destinationRetransmissionBandwidthKbps").value = "";
    document.getElementById("destinationTtl").value = "";
    document.getElementById("destinationMtu").value = "";
    document.getElementById("destinationTos").value = "";
    document.getElementById("destinationMaxBitrateKbps").value = "";
    document.getElementById("pathRedundancyEnabled").checked = false;
    hydrateStreamIdConfig("destination", {});
    document.getElementById("destinationUrl").value = destinationUrl || "";

    if (!destinationUrl) {
        setRouteEditorVisibility();
        return;
    }

    try {
        const url = new URL(destinationUrl);
        if (url.protocol === "rtmp:" || url.protocol === "rtmps:") {
            const parts = url.pathname.split("/").filter(Boolean);
            document.getElementById("destinationBuilderProtocol").value = url.protocol.replace(":", "");
            document.getElementById("destinationHost").value = url.hostname;
            document.getElementById("destinationPort").value = url.port || "1935";
            document.getElementById("destinationPath").value = parts.length > 1 ? `/${parts.slice(0, -1).join("/")}` : url.pathname || "/live";
            document.getElementById("destinationKey").value = parts.length > 1 ? parts[parts.length - 1] : "";
        } else if (url.protocol === "srt:") {
            document.getElementById("destinationBuilderProtocol").value = "srt";
            document.getElementById("destinationHost").value = url.hostname;
            document.getElementById("destinationPort").value = url.port;
            document.getElementById("destinationMode").value = url.searchParams.get("mode") || "caller";
            document.getElementById("destinationPassphrase").value = url.searchParams.get("passphrase") || "";
            if (url.searchParams.get("pbkeylen")) document.getElementById("pbkeylen").value = url.searchParams.get("pbkeylen");
            hydrateStreamIdConfig("destination", {}, url.searchParams.get("streamid") || "");
        } else if (url.protocol === "udp:") {
            document.getElementById("destinationBuilderProtocol").value = "udp";
            document.getElementById("destinationHost").value = url.hostname;
            document.getElementById("destinationPort").value = url.port;
            document.getElementById("destinationTtl").value = url.searchParams.get("ttl") || "";
        } else if (url.protocol === "rist:") {
            document.getElementById("destinationBuilderProtocol").value = "rist";
            document.getElementById("destinationHost").value = url.hostname;
            document.getElementById("destinationPort").value = url.port;
        } else {
            document.getElementById("destinationBuilderProtocol").value = "raw";
        }
    } catch {
        document.getElementById("destinationBuilderProtocol").value = "raw";
    }
    setRouteEditorVisibility();
}

function syncDestinationUrlPreview() {
    const builder = document.getElementById("destinationBuilderProtocol").value;
    if (builder !== "raw") document.getElementById("destinationUrl").value = buildDestinationUrlFromFields();
}

function setHlsControlVisibility() {
    const fullEnabled = document.getElementById("enableFullHls").checked;
    document.getElementById("fullHlsBufferRow").style.display = fullEnabled ? "grid" : "none";
}

function syncDestinationRequired() {
    const hlsEnabled = document.getElementById("enableHlsPreview").checked || document.getElementById("enableFullHls").checked;
    const normalDestinationEnabled = document.getElementById("normalDestinationEnabled").checked;
    document.getElementById("destinationUrl").required = normalDestinationEnabled && !hlsEnabled && document.getElementById("destinationBuilderProtocol").value === "raw";
    document.getElementById("destinationHost").required = normalDestinationEnabled && document.getElementById("destinationBuilderProtocol").value !== "raw";
    document.getElementById("destinationPort").required = normalDestinationEnabled && document.getElementById("destinationBuilderProtocol").value !== "raw";
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

function hydrateSourceConfig(config = {}) {
    const source = config.source || {};
    const protocol = source.protocol || config.source_protocol || "srt";
    document.getElementById("sourceProtocol").value = protocol;
    document.getElementById("sourceMode").value = source.mode || config.source_mode || "listener";
    document.getElementById("sourceUdpType").value = source.type || "unicast";
    document.getElementById("sourcePath").value = source.path || config.source_path || "";
    document.getElementById("sourceUrl").value = source.url || config.source_url || "";
    hydrateRouteEndpoint("source", source.primary_endpoint || {}, {
        bind_ip: source.primary_endpoint?.bind_ip || getExplicitInputBind(config, "primary"),
        address: config.source_ip || "0.0.0.0",
        port: config.source_port || ""
    });
    const linkParameters = source.link_parameters || {};
    document.getElementById("sourceTtl").value = linkParameters.ttl ?? "";
    document.getElementById("sourceMtu").value = linkParameters.mtu ?? "";
    const srtParams = source.srt || {};
    document.getElementById("sourceLatencyMs").value = srtParams.latency_ms || config.latency_ms || "";
    document.getElementById("sourceReceiveBufferBytes").value = srtParams.receive_buffer_bytes || "";
    document.getElementById("sourcePassphrase").value = srtParams.passphrase || config.passphrase || "";
    hydrateStreamIdConfig("source", srtParams, config.streamid || "");
}

function hydrateDestinationConfig(config = {}) {
    const destination = firstEnabledDestination(config.destinations || []);
    const destinationUrl = config.destination_url || destination?.url || "";
    const hasNormalDestination = !!(destination || destinationUrl);
    document.getElementById("normalDestinationEnabled").checked = hasNormalDestination || !hasAnyHlsOutput(config);

    const protocol = destination?.protocol || "";
    if (protocol) {
        document.getElementById("destinationBuilderProtocol").value = protocol;
    } else {
        populateDestinationBuilder(destinationUrl);
    }

    const selectedProtocol = document.getElementById("destinationBuilderProtocol").value;
    if (destination && selectedProtocol !== "raw") {
        hydrateRouteEndpoint("destination", destination.primary_endpoint || {}, {
            bind_ip: destination.primary_endpoint?.bind_ip || getExplicitOutputBind(config, "primary"),
            address: "",
            port: ""
        });
    }
    if (destination?.url && (selectedProtocol === "rtmp" || selectedProtocol === "rtmps")) {
        populateDestinationBuilder(destination.url);
    } else if (selectedProtocol === "raw") {
        document.getElementById("destinationUrl").value = destination?.url || destinationUrl || "";
    }

    document.getElementById("destinationMode").value = destination?.mode || "caller";
    document.getElementById("destinationUdpType").value = destination?.type || "unicast";
    const linkParameters = destination?.link_parameters || {};
    document.getElementById("destinationTtl").value = linkParameters.ttl ?? "";
    document.getElementById("destinationMtu").value = linkParameters.mtu ?? "";
    document.getElementById("destinationTos").value = linkParameters.tos || "";
    document.getElementById("destinationMaxBitrateKbps").value = linkParameters.max_bitrate_kbps || "";
    const srtParams = destination?.srt || {};
    document.getElementById("destinationLatencyMs").value = srtParams.latency_ms || "";
    document.getElementById("destinationRetransmissionBandwidthKbps").value = srtParams.retransmission_bandwidth_kbps || "";
    document.getElementById("destinationPassphrase").value = srtParams.passphrase || "";
    hydrateStreamIdConfig("destination", srtParams, "");

    const redundancy = destination?.path_redundancy || {};
    document.getElementById("pathRedundancyEnabled").checked = !!redundancy.enabled;
    hydrateRouteEndpoint("destinationSecondary", redundancy.secondary_endpoint || {}, {
        bind_ip: redundancy.secondary_endpoint?.bind_ip || getExplicitOutputBind(config, "backup"),
        address: "",
        port: ""
    });
    syncDestinationUrlPreview();
}

function openModal(id) {
    document.getElementById(id).classList.add("active");
}

function closeModal(id) {
    document.getElementById(id).classList.remove("active");
    document.getElementById("serviceForm").reset();
    document.getElementById("serviceId").value = "";
    document.getElementById("modalTitle").innerText = "Create New Service";
    document.getElementById("advancedOptions").classList.remove("active");
    document.getElementById("sourceProtocol").value = "srt";
    document.getElementById("destinationBuilderProtocol").value = "srt";
    document.getElementById("normalDestinationEnabled").checked = true;
    setTargetNodeForCreate();
    hydrateStreamIdConfig("source", {});
    hydrateStreamIdConfig("destination", {});
    populateDestinationBuilder("");
    populateBindingFields({});
    populateRouteEndpointSelects({});
    setRouteEditorVisibility();
    setHlsControlVisibility();
}

[
    "sourceProtocol",
    "sourceStreamIdMode",
    "destinationBuilderProtocol",
    "destinationMode",
    "destinationStreamIdMode",
    "normalDestinationEnabled",
    "pathRedundancyEnabled",
    "enableHlsPreview",
    "enableFullHls"
].forEach(id => document.getElementById(id).addEventListener("change", setRouteEditorVisibility));

document.getElementById("enableFullHls").addEventListener("change", setHlsControlVisibility);

document.getElementById("destinationBuilderProtocol").addEventListener("change", () => {
    if (document.getElementById("destinationBuilderProtocol").value !== "raw") {
        document.getElementById("destinationUrl").value = "";
    }
    syncDestinationUrlPreview();
});

[
    "destinationHost",
    "destinationPort",
    "destinationPath",
    "destinationKey",
    "destinationMode",
    "destinationStreamIdCustomValue",
    "destinationPassphrase",
    "pbkeylen",
    "destinationTtl",
].forEach(id => document.getElementById(id).addEventListener("input", syncDestinationUrlPreview));

document.getElementById("serviceForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const id = document.getElementById("serviceId").value;
    const isEdit = !!id;

    let keylenParsed = parseInt(document.getElementById("pbkeylen").value, 10);

    const existingBindings = isEdit ? (servicesMap[id].config.node_bindings || {}) : {};
    const lowResHlsEnabled = document.getElementById("enableHlsPreview").checked;
    const fullHlsEnabled = document.getElementById("enableFullHls").checked;
    const source = buildSourceConfigFromForm();
    const destinations = buildDestinationConfigFromForm();
    const legacyFields = buildLegacyFieldsFromStructured(source, destinations);
    const destinationUrl = buildDestinationUrlFromFields();
    if (!destinationUrl && !lowResHlsEnabled && !fullHlsEnabled) {
        alert("Destination URL is required unless Low-Res or Full HLS output is enabled.");
        return;
    }

    const payload = {
        id: id || "",
        name: document.getElementById("serviceName").value,
        source,
        destinations,
        ...legacyFields,

        target_node: document.getElementById("targetNode").value,

        local_bind_ip: document.getElementById("localBindIp").value || null,
        node_bindings: buildNodeBindingsFromForm(existingBindings),
        pbkeylen: keylenParsed !== 0 ? keylenParsed : null,

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

    setTargetNodeForEdit(s.config.target_node);

    document.getElementById("localBindIp").value = s.config.local_bind_ip || "";
    populateBindingFields(s.config);
    document.getElementById("pbkeylen").value = s.config.pbkeylen || "0";
    document.getElementById("streamid").value = s.config.streamid || "";

    document.getElementById("backupInputIp").value = s.config.backup_input_ip || "";
    document.getElementById("autoFailover").checked = s.config.auto_failover || false;
    document.getElementById("strictProbing").checked = s.config.strict_probing || false;
    const hlsOutputs = getHlsOutputs(s.config);
    document.getElementById("enableHlsPreview").checked = hlsOutputs.low_res.enabled;
    document.getElementById("enableFullHls").checked = hlsOutputs.full_res.enabled;
    document.getElementById("fullHlsBufferHours").value = Math.max(1, Math.ceil((hlsOutputs.full_res.buffer_seconds || 3600) / 3600));
    hydrateSourceConfig(s.config);
    hydrateDestinationConfig(s.config);
    populateRouteEndpointSelects(s.config);
    setRouteEditorVisibility();
    setHlsControlVisibility();

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

populateRouteEndpointSelects({});
setRouteEditorVisibility();
setHlsControlVisibility();
