from pathlib import Path


def test_hls_copy_uses_config_id():
    app_js = Path("frontend/app.js").read_text()

    assert "/previews/${previewIdPath}/low_res/stream.m3u8" in app_js
    assert "/previews/${previewIdPath}/full_res/stream.m3u8" in app_js
    assert "/previews/${s.id}/stream.m3u8" not in app_js


def test_frontend_assets_are_versioned_for_release_cache_busting():
    index_html = Path("frontend/index.html").read_text()

    assert 'href="style.css?v=route-editor-v2-ui-reviewer-fixes"' in index_html
    assert 'src="app.js?v=route-editor-v2-ui-reviewer-fixes"' in index_html
    assert 'href="style.css"' not in index_html
    assert 'src="app.js"></script>' not in index_html


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
    assert "destinationStreamIdMode" in index_html
    assert "destinationStreamIdCustomValue" in index_html
    assert '<option value="rtmps">RTMPS destination</option>' in index_html
    assert '<option value="rist">RIST destination</option>' in index_html
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
    assert "function setRouteEditorVisibility" in app_js
    assert "source_protocol: source.protocol" in app_js
    assert "hls_outputs" in app_js
    assert "normalDestinationEnabled && !hlsEnabled" in app_js


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
    app_js = Path("frontend/app.js").read_text()

    assert 'style="max-height: 90vh; overflow-y: auto;"' not in index_html
    assert "width: min(1120px, calc(100vw - 32px));" in style_css
    assert "max-width: 500px" not in style_css
    assert 'gridTemplateColumns = "1fr 1fr"' not in app_js
    assert "@media (max-width: 760px)" in style_css
    assert "grid-template-columns: 1fr;" in style_css
    assert "min-width: 0;" in style_css
    assert ".app-container" in style_css
    assert "display: block;" in style_css
    assert "width: max-content;" in style_css


def test_dashboard_binding_summary_is_labeled_as_target_binding():
    app_js = Path("frontend/app.js").read_text()

    assert "TARGET IN" in app_js
    assert "Target node binding. Active owner may differ during failover." in app_js


def test_route_editor_v2_controls_are_present():
    index_html = Path("frontend/index.html").read_text()
    app_js = Path("frontend/app.js").read_text()

    assert "route-section-title" in index_html
    assert "sourceUdpType" in index_html
    assert "destinationUdpType" in index_html
    assert "sourceStreamIdMode" in index_html
    assert "destinationStreamIdMode" in index_html
    assert "pathRedundancyEnabled" in index_html
    assert "destinationSecondaryInterface" in index_html
    assert "normalDestinationEnabled" in index_html
    assert "function buildRouteEndpointFromForm" in app_js
    assert "function hydrateRouteEndpoint" in app_js
    assert "function buildStreamIdConfig" in app_js
    assert "function hydrateStreamIdConfig" in app_js
    assert "function buildSourceConfigFromForm" in app_js
    assert "function hydrateSourceConfig" in app_js
    assert "function buildDestinationConfigFromForm" in app_js
    assert "function hydrateDestinationConfig" in app_js
    assert "function buildLegacyFieldsFromStructured" in app_js


def test_route_editor_v2_serializes_structured_and_legacy_fields():
    app_js = Path("frontend/app.js").read_text()

    assert "source = buildSourceConfigFromForm()" in app_js
    assert "destinations = buildDestinationConfigFromForm()" in app_js
    assert "source," in app_js
    assert "destinations," in app_js
    assert "...legacyFields" in app_js
    assert "primary_endpoint: buildRouteEndpointFromForm(\"source\")" in app_js
    assert "primary_endpoint: buildRouteEndpointFromForm(\"destination\")" in app_js
    assert "path_redundancy: protocol === \"srt\" ? buildPathRedundancyFromForm() : null" in app_js


def test_target_node_preserves_legacy_values_only_on_edit():
    index_html = Path("frontend/index.html").read_text()
    app_js = Path("frontend/app.js").read_text()

    assert '<option value="worker_1">' not in index_html
    assert "function resetTargetNodeOptions" in app_js
    assert "function setTargetNodeForCreate" in app_js
    assert "function setTargetNodeForEdit" in app_js
    assert "option[data-legacy-target='true']" in app_js
    assert "legacyOption.dataset.legacyTarget = \"true\"" in app_js
    assert "legacyOption.textContent = `Existing legacy ${targetNode}`" in app_js
    assert "select.value = targetNode" in app_js
    assert "setTargetNodeForCreate();" in app_js
    assert "setTargetNodeForEdit(s.config.target_node);" in app_js
    assert '["primary", "backup", "all"].includes(s.config.target_node) ? s.config.target_node : "primary"' not in app_js


def test_pbkeylen_stays_top_level_legacy_only():
    app_js = Path("frontend/app.js").read_text()

    assert "pbkeylen: keylenParsed !== 0 ? keylenParsed : null" in app_js
    assert '"pbkeylen"' in app_js
    assert "pbkeylen:" not in app_js.split("function buildSrtParametersFromForm", 1)[1].split("function buildLinkParametersFromForm", 1)[0]
    assert "destinationPbkeylen" not in app_js


def test_destination_stream_id_does_not_leak_to_legacy_source_streamid():
    app_js = Path("frontend/app.js").read_text()
    legacy_helper = app_js.split("function buildLegacyFieldsFromStructured", 1)[1].split("function setRouteEditorVisibility", 1)[0]

    assert "destinationStreamId" not in legacy_helper
    assert "source.protocol === \"srt\" && sourceStreamId.mode === \"custom\"" in legacy_helper
    assert 'document.getElementById("streamid").value.trim()' not in legacy_helper
    assert ": null;" in legacy_helper
