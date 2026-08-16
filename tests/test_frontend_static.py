from pathlib import Path


def test_hls_copy_uses_config_id():
    app_js = Path("frontend/app.js").read_text()

    assert "/previews/${previewIdPath}/low_res/stream.m3u8" in app_js
    assert "/previews/${previewIdPath}/full_res/stream.m3u8" in app_js
    assert "/previews/${s.id}/stream.m3u8" not in app_js


def test_service_values_are_escaped_before_table_rendering():
    app_js = Path("frontend/app.js").read_text()

    assert "function escapeHtml" in app_js
    assert "const serviceName = escapeHtml(c.name);" in app_js
    assert "const destinationUrl = c.destination_url || \"\";" in app_js
    assert "urlDisplayHtml(\"Destination\", destinationUrl)" in app_js


def test_service_actions_use_delegated_buttons():
    app_js = Path("frontend/app.js").read_text()

    assert "addEventListener(\"click\", handleTableAction)" in app_js
    assert "data-action=\"edit\"" in app_js
    assert "data-action=\"delete\"" in app_js
    assert "async function apiRequest" in app_js


def test_destination_builder_fields_are_present():
    index_html = Path("frontend/index.html").read_text()
    app_js = Path("frontend/app.js").read_text()

    assert "destinationBuilderProtocol" in index_html
    assert "destinationHost" in index_html
    assert "destinationStreamid" in index_html
    assert '<option value="udp">UDP destination</option>' in index_html
    assert "function buildDestinationUrlFromFields" in app_js
    assert "srt://${host}:${port}" in app_js
    assert "udp://${host}:${port}" in app_js


def test_hls_source_and_output_controls_are_present():
    index_html = Path("frontend/index.html").read_text()
    app_js = Path("frontend/app.js").read_text()

    assert '<option value="hls">HLS</option>' in index_html
    assert "sourceUrl" in index_html
    assert "enableFullHls" in index_html
    assert "fullHlsBufferHours" in index_html
    assert "function setSourceProtocolVisibility" in app_js
    assert "source_protocol: sourceProtocol" in app_js
    assert "hls_outputs" in app_js
    assert 'document.getElementById("destinationUrl").required = !hlsEnabled' in app_js


def test_binding_fields_are_present_and_submitted():
    index_html = Path("frontend/index.html").read_text()
    app_js = Path("frontend/app.js").read_text()

    assert "primaryInputBindIp" in index_html
    assert "primaryOutputBindIp" in index_html
    assert "backupNodeInputBindIp" in index_html
    assert "backupNodeOutputBindIp" in index_html
    assert "Single Worker Input Bind IP" not in index_html
    assert '<option value="worker_1">Single Worker (worker_1)</option>' not in index_html
    assert 'id="primaryInputBindIp" class="form-control-select"' in index_html
    assert "function buildNodeBindingsFromForm" in app_js
    assert "function populateInterfaceSelect" in app_js
    assert "/interfaces" in app_js
    assert "input_bind_ip" in app_js
    assert "output_bind_ip" in app_js


def test_binding_form_uses_explicit_values_not_legacy_fallback():
    app_js = Path("frontend/app.js").read_text()

    assert "function getExplicitInputBind" in app_js
    assert "function getExplicitOutputBind" in app_js
    assert "function getEffectiveInputBind" in app_js
    assert "function getEffectiveOutputBind" in app_js
    assert 'populateInterfaceSelect("primaryInputBindIp", "primary", "input", getExplicitInputBind(config, "primary"));' in app_js
    assert 'populateInterfaceSelect("backupNodeOutputBindIp", "backup", "output", getExplicitOutputBind(config, "backup"));' in app_js
    assert 'document.getElementById("primaryInputBindIp").value = getEffectiveInputBind' not in app_js


def test_modal_uses_wider_css_layout():
    index_html = Path("frontend/index.html").read_text()
    style_css = Path("frontend/style.css").read_text()

    assert 'style="max-height: 90vh; overflow-y: auto;"' not in index_html
    assert "width: min(960px, calc(100vw - 32px));" in style_css
    assert "max-width: 500px" not in style_css


def test_dashboard_binding_summary_is_labeled_as_target_binding():
    app_js = Path("frontend/app.js").read_text()

    assert "TARGET IN" in app_js
    assert "Target node binding. Active owner may differ during failover." in app_js
