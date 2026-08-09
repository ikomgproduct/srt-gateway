from pathlib import Path


def test_hls_copy_uses_config_id():
    app_js = Path("frontend/app.js").read_text()

    assert "/previews/${previewIdPath}/stream.m3u8" in app_js
    assert "/previews/${s.id}/stream.m3u8" not in app_js


def test_service_values_are_escaped_before_table_rendering():
    app_js = Path("frontend/app.js").read_text()

    assert "function escapeHtml" in app_js
    assert "const serviceName = escapeHtml(c.name);" in app_js
    assert "const destinationUrl = escapeHtml(c.destination_url || \"\");" in app_js
