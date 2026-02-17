"""Settings API endpoint tests.

Tests the /settings, /settings/schema, and POST /settings endpoints
using an in-process FastAPI TestClient.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from starlette.testclient import TestClient

from voxtype.config import Config


@pytest.fixture
def settings_app():
    """Create a minimal FastAPI app with settings routes for testing."""
    from unittest.mock import MagicMock

    from voxtype.core.http_server import OpenVIPServer

    engine = MagicMock()
    engine.get_status.return_value = {"state": "OFF"}
    server = OpenVIPServer(engine, controller=None, host="127.0.0.1", port=0)
    app = server._create_app()
    return app


@pytest.fixture
def client(settings_app):
    """TestClient for the FastAPI app."""
    return TestClient(settings_app)


class TestGetSettingsPage:
    """GET /settings — serves the HTML page."""

    def test_returns_html(self, client):
        r = client.get("/settings")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_contains_app_structure(self, client):
        r = client.get("/settings")
        html = r.text
        assert "<title>VoxType Settings</title>" in html
        assert "sidebar" in html
        assert "/settings/schema" in html


class TestGetSettingsSchema:
    """GET /settings/schema — returns JSON Schema + current values."""

    def test_returns_schema(self, client):
        r = client.get("/settings/schema")
        assert r.status_code == 200
        data = r.json()
        assert "schema" in data
        assert "values" in data
        assert "keys" in data
        assert "version" in data

    def test_schema_has_definitions(self, client):
        r = client.get("/settings/schema")
        schema = r.json()["schema"]
        assert "$defs" in schema
        assert "TTSConfig" in schema["$defs"]
        assert "AudioConfig" in schema["$defs"]

    def test_values_match_config(self, client):
        r = client.get("/settings/schema")
        values = r.json()["values"]
        config = Config()
        assert values["audio"]["sample_rate"] == config.audio.sample_rate

    def test_keys_list_has_entries(self, client):
        r = client.get("/settings/schema")
        keys = r.json()["keys"]
        assert len(keys) > 10
        # Each key has required fields
        k = keys[0]
        assert "key" in k
        assert "type" in k
        assert "description" in k

    def test_tts_engine_has_enum(self, client):
        r = client.get("/settings/schema")
        schema = r.json()["schema"]
        tts = schema["$defs"]["TTSConfig"]
        engine_field = tts["properties"]["engine"]
        assert "enum" in engine_field
        assert "say" in engine_field["enum"]
        assert "espeak" in engine_field["enum"]


class TestPostSettings:
    """POST /settings — update a config value."""

    def test_update_valid_key(self, client, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("[stt]\nmodel = \"large-v3-turbo\"\n")
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.post(
                "/settings",
                json={"key": "stt.model", "value": "base"},
            )
            assert r.status_code == 200
            data = r.json()
            assert data["status"] == "ok"
            assert data["key"] == "stt.model"

    def test_invalid_key_returns_404(self, client):
        r = client.post(
            "/settings",
            json={"key": "nonexistent.field", "value": "foo"},
        )
        assert r.status_code == 404

    def test_missing_key_returns_400(self, client):
        r = client.post("/settings", json={"value": "foo"})
        assert r.status_code == 400

    def test_invalid_value_returns_422(self, client, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("[output]\nmode = \"keyboard\"\n")
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.post(
                "/settings",
                json={"key": "output.mode", "value": "invalid_mode"},
            )
            assert r.status_code == 422
