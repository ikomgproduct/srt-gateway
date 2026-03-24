const API_URL = "http://localhost:8000/api";
let servicesMap = {};
let systemNodeRole = "primary";

async function fetchNodeRole() {
    try {
        const res = await fetch(`${API_URL}/node_role`);
        const data = await res.json();
        systemNodeRole = data.role;
        document.getElementById('nodeIdentity').innerText = `${systemNodeRole} Node`;
        
        if (systemNodeRole === "standalone") {
            document.getElementById('hardwareNodeGroup').style.display = 'none';
        } else {
            document.getElementById('hardwareNodeRow').style.gridTemplateColumns = '1fr 1fr';
            document.getElementById('hardwareNodeGroup').parentElement.firstElementChild.style.gridColumn = 'auto';
        }
    } catch(e) {}
}
fetchNodeRole();

async function fetchServices() {
    try {
        const res = await fetch(`${API_URL}/services`);
        const data = await res.json();
        renderServices(data);
    } catch (err) {
        console.error("Failed to fetch services", err);
    }
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
        const statusClass = `status-${s.status}`;
        
        let actionsHtml = "";
        if (s.status === "running") {
            actionsHtml = `<button class="btn-danger" style="padding: 6px 12px; font-size: 0.8rem;" onclick="stopService('${c.id}')" title="Stop"><i class="fa-solid fa-stop"></i></button>`;
            actionsHtml += `<button class="btn-secondary" style="padding: 6px 12px; font-size: 0.8rem; margin-left:4px;" onclick="startService('${c.id}', ${s.active_input === 'main' ? 'true' : 'false'})" title="Manual Hot-Swap Input"><i class="fa-solid fa-rotate"></i> Feed</button>`;
        } else if (s.status === "stopped" || s.status === "error") {
            actionsHtml = `<button class="btn-primary" style="padding: 6px 12px; font-size: 0.8rem;" onclick="startService('${c.id}')"><i class="fa-solid fa-play"></i> Start</button>`;
        } else {
            actionsHtml = `<button class="btn-secondary" style="padding: 6px 12px; font-size: 0.8rem;" disabled><i class="fa-solid fa-spinner fa-spin"></i></button>`;
        }

        const path = c.source_path ? c.source_path : '';
        const sourceLine = `${c.source_protocol.toUpperCase()}://${c.source_ip}:${c.source_port}${path}`;
        const encryptionText = c.pbkeylen && c.pbkeylen > 0 ? `<i class="fa-solid fa-lock" style="color:var(--accent);"></i> ${c.pbkeylen * 8}-bit` : `<i class="fa-solid fa-lock-open" style="color:var(--text-muted);"></i> None`;

        let nodeColor = c.target_node === 'primary' ? '#5e6ad2' : (c.target_node === 'backup' ? '#20c997' : '#e2e8f0');
        let hideNodeInfo = systemNodeRole === "standalone" ? `style="display:none;"` : '';

        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>
                <div style="font-weight: 600; margin-bottom: 6px; font-size: 1rem;">${c.name}</div>
                <span class="status-badge ${statusClass}">${s.status}</span>
                ${s.error_msg ? `<div style="color: var(--danger); font-size: 0.75rem; margin-top: 6px; max-width: 150px; overflow:hidden; text-overflow:ellipsis;" title="${s.error_msg}"><i class="fa-solid fa-triangle-exclamation"></i> Error</div>` : ''}
            </td>
            <td>
                <div style="font-weight: 600; color: var(--text-main); margin-bottom: 2px;">${c.source_protocol.toUpperCase()}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase;">${c.source_mode}</div>
            </td>
            <td>
                <div style="font-family: monospace; color: var(--text-main); background: rgba(0,0,0,0.2); padding: 4px 8px; border-radius: 4px; margin-bottom: 6px;" title="Main Source Feed">MAIN: ${c.source_ip}</div>
                ${c.backup_input_ip ? `<div style="font-family: monospace; color: var(--accent); background: rgba(32,201,151,0.1); padding: 4px 8px; border-radius: 4px;" title="Standby Backup Feed">BACKUP: ${c.backup_input_ip}</div>` : ''}
            </td>
            <td>
                <div style="max-width: 200px; overflow: hidden; text-overflow: ellipsis; color: var(--text-muted);" title="${c.destination_url}">${c.destination_url}</div>
            </td>
            <td>
                <div class="status-badge" style="background: ${s.active_input === 'main' ? 'rgba(94,106,210,0.2)' : 'rgba(32,201,151,0.2)'}; color: ${s.active_input === 'main' ? 'var(--primary)' : 'var(--accent)'}; margin-bottom:6px;">${s.active_input.toUpperCase()} FEED</div>
                <div ${hideNodeInfo} style="font-size: 0.7rem; font-weight:600; color: ${nodeColor}; margin-bottom:4px;"><i class="fa-solid fa-server"></i> ${c.target_node.toUpperCase()} NODE</div>
                <div style="font-size: 0.75rem; color: var(--text-muted); font-weight:600;">${c.auto_failover ? '<i class="fa-solid fa-shield" style="color:var(--accent);"></i> Auto-Switch ON' : 'Manual Switch'} ${c.strict_probing ? '&bull; <span style="color:var(--danger);"><i class="fa-solid fa-magnifying-glass-chart"></i> Strict Watch</span>' : ''}</div>
            </td>
            <td>
                <div style="font-size: 0.85rem;">${encryptionText}</div>
            </td>
            <td class="td-video">
                <div class="td-video-inner">
                    ${s.status === 'running' ? `
                        <img src="/previews/${c.id}/preview.jpg?t=${Date.now()}" style="width:100%; height:100%; object-fit:cover;" onerror="this.onerror=null; this.src=''; this.parentElement.innerHTML='<div style=\\'color:var(--text-muted);font-size:0.75rem;\\'><i class=\\'fa-solid fa-spinner fa-spin\\'></i> Buffering...</div>';">
                    ` : `
                        <div style="color: rgba(255,255,255,0.1);"><i class="fa-solid fa-video-slash" style="font-size:1.5rem;"></i></div>
                    `}
                </div>
                ${c.enable_hls_preview ? `<div style="text-align:center; margin-top:8px;"><button style="background:transparent; border:1px solid var(--primary); color:var(--primary); padding:4px 8px; border-radius:4px; font-weight:600; cursor:pointer; font-size:0.7rem; transition:0.2s;" onclick="navigator.clipboard.writeText('${window.location.origin}/previews/${s.id}/stream.m3u8'); this.innerHTML='<i class=\\'fa-solid fa-check\\'></i> Copied!'; setTimeout(()=>this.innerHTML='<i class=\\'fa-solid fa-link\\'></i> Copy HLS Link',2000);"><i class="fa-solid fa-link"></i> Copy HLS Link</button></div>` : ''}
            </td>
            <td>
                <div class="td-actions">
                    ${actionsHtml}
                    ${systemNodeRole !== "standalone" ? `<button class="icon-btn" style="margin-left: 12px; color: ${nodeColor};" onclick="swapNode('${c.id}', '${c.target_node}')" title="Move Stream to Twin Hardware Node"><i class="fa-solid fa-server"></i> Move</button>` : ''}
                    <button class="icon-btn" style="margin-left: 4px;" onclick="editService('${c.id}')" title="Edit Properties"><i class="fa-solid fa-gear"></i></button>
                    <button class="icon-btn delete" onclick="deleteService('${c.id}')" title="Delete Pipeline"><i class="fa-solid fa-trash"></i></button>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

setInterval(fetchServices, 4000);
fetchServices();

async function swapNode(id, currentNode) {
    const payload = servicesMap[id].config;
    // Swap cyclically between primary -> backup -> all
    let next = 'primary';
    if (currentNode === 'primary') next = 'backup';
    else if (currentNode === 'backup') next = 'all';
    
    payload.target_node = next;
    // Sending PUT to REST API instantly saves it into config.json.
    // The Cluster Sync Loop running on both hardware nodes catches the config.json MTIME upgrade 
    // precisely 2 seconds later and perfectly manages process tear-down and spin-up seamlessly without User intervention!
    await fetch(`${API_URL}/services/${id}`, { method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
    fetchServices();
}

function openModal(id) {
    document.getElementById(id).classList.add('active');
}

function closeModal(id) {
    document.getElementById(id).classList.remove('active');
    document.getElementById('serviceForm').reset();
    document.getElementById('serviceId').value = "";
    document.getElementById('modalTitle').innerText = "Create New Service";
    document.getElementById('advancedOptions').style.display = 'none';
}

document.getElementById('serviceForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const id = document.getElementById('serviceId').value;
    const isEdit = !!id;
    
    let keylenParsed = parseInt(document.getElementById('pbkeylen').value, 10);
    
    const payload = {
        id: id || "",
        name: document.getElementById('serviceName').value,
        source_protocol: document.getElementById('sourceProtocol').value,
        source_mode: document.getElementById('sourceMode').value,
        source_ip: document.getElementById('sourceIp').value || "0.0.0.0",
        source_port: parseInt(document.getElementById('sourcePort').value, 10),
        source_path: document.getElementById('sourcePath').value,
        destination_url: document.getElementById('destinationUrl').value,
        
        target_node: document.getElementById('targetNode').value,
        
        local_bind_ip: document.getElementById('localBindIp').value || null,
        latency_ms: document.getElementById('latencyMs').value ? parseInt(document.getElementById('latencyMs').value, 10) : null,
        passphrase: document.getElementById('passphrase').value || null,
        pbkeylen: keylenParsed !== 0 ? keylenParsed : null,
        streamid: document.getElementById('streamid').value || null,

        backup_input_ip: document.getElementById('backupInputIp').value || null,
        auto_failover: document.getElementById('autoFailover').checked,
        strict_probing: document.getElementById('strictProbing').checked,
        enable_hls_preview: document.getElementById('enableHlsPreview').checked,
        
        enabled: true
    };
    
    try {
        const method = isEdit ? 'PUT' : 'POST';
        const url = isEdit ? `${API_URL}/services/${id}` : `${API_URL}/services`;
        
        const res = await fetch(url, {
            method,
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            closeModal('createModal');
            fetchServices();
        } else {
            const err = await res.json();
            alert("Error: " + JSON.stringify(err.detail));
        }
    } catch (err) {
        console.error(err);
        alert("Failed to save service");
    }
});

function editService(id) {
    const s = servicesMap[id];
    if (!s) return;
    document.getElementById('modalTitle').innerText = "Edit Service Properties";
    document.getElementById('serviceId').value = s.config.id;
    document.getElementById('serviceName').value = s.config.name;
    document.getElementById('sourceProtocol').value = s.config.source_protocol || "srt";
    document.getElementById('sourceMode').value = s.config.source_mode || "listener";
    document.getElementById('sourceIp').value = s.config.source_ip || "0.0.0.0";
    document.getElementById('sourcePort').value = s.config.source_port;
    document.getElementById('sourcePath').value = s.config.source_path || "";
    document.getElementById('destinationUrl').value = s.config.destination_url;
    
    document.getElementById('targetNode').value = s.config.target_node || "primary";
    
    document.getElementById('localBindIp').value = s.config.local_bind_ip || "";
    document.getElementById('latencyMs').value = s.config.latency_ms || "";
    document.getElementById('passphrase').value = s.config.passphrase || "";
    document.getElementById('pbkeylen').value = s.config.pbkeylen || "0";
    document.getElementById('streamid').value = s.config.streamid || "";

    document.getElementById('backupInputIp').value = s.config.backup_input_ip || "";
    document.getElementById('autoFailover').checked = s.config.auto_failover || false;
    document.getElementById('strictProbing').checked = s.config.strict_probing || false;
    document.getElementById('enableHlsPreview').checked = s.config.enable_hls_preview || false;
    
    openModal('createModal');
}

async function deleteService(id) {
    if (!confirm("Are you sure you want to delete this routing pipeline?")) return;
    await fetch(`${API_URL}/services/${id}`, { method: 'DELETE' });
    fetchServices();
}

async function startService(id, useBackup=false) {
    await fetch(`${API_URL}/services/${id}/start?use_backup=${useBackup}`, { method: 'POST' });
    fetchServices();
}

async function stopService(id) {
    await fetch(`${API_URL}/services/${id}/stop`, { method: 'POST' });
    fetchServices();
}
