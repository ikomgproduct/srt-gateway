from pathlib import Path


def test_hls_copy_uses_config_id():
    app_js = Path("frontend/app.js").read_text()

    assert "/previews/${previewIdPath}/stream.m3u8" in app_js
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
    assert "function buildDestinationUrlFromFields" in app_js
    assert "srt://${host}:${port}" in app_js
