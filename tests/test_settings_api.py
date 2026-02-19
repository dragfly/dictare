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
    """GET /settings — redirects to SPA or serves fallback HTML."""

    def test_settings_redirects_to_ui(self, client):
        r = client.get("/settings", follow_redirects=False)
        assert r.status_code in (301, 302, 307, 308)
        assert "/ui" in r.headers.get("location", "")

    def test_ui_serves_html(self, client):
        r = client.get("/ui/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]

    def test_ui_contains_sveltekit_app(self, client):
        r = client.get("/ui/")
        html = r.text
        assert "<title>VoxType Settings</title>" in html


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


class TestTomlSectionGet:
    """GET /settings/toml-section/{section}"""

    def test_agent_types_returns_content_from_file(self, client, tmp_path):
        """Fetch returns the raw content from the config file (WYSIWYG)."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[agent_types.claude]\ncommand = ["claude"]\n'
        )
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.get("/settings/toml-section/agent_types")
        assert r.status_code == 200
        data = r.json()
        assert data["section"] == "agent_types"
        assert "agent_types" in data["content"]
        assert "claude" in data["content"]

    def test_agent_types_returns_template_when_absent(self, client, tmp_path):
        """Fetch returns the comment-only template when the section is not in the file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("")  # no agent_types section
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.get("/settings/toml-section/agent_types")
        assert r.status_code == 200
        content = r.json()["content"]
        # Template is comment-only
        assert "#" in content
        assert all(
            line.startswith("#") or not line.strip()
            for line in content.splitlines()
        )

    def test_shortcuts_returns_content(self, client):
        r = client.get("/settings/toml-section/keyboard.shortcuts")
        assert r.status_code == 200
        data = r.json()
        assert data["section"] == "keyboard.shortcuts"
        assert isinstance(data["content"], str)

    def test_unknown_section_returns_404(self, client):
        r = client.get("/settings/toml-section/nonexistent")
        assert r.status_code == 404

    def test_content_includes_comments(self, client, tmp_path):
        """Template header (when no section in file) contains comments."""
        config_file = tmp_path / "nonexistent_config.toml"
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.get("/settings/toml-section/agent_types")
        assert r.status_code == 200
        assert "#" in r.json()["content"]


class TestTomlSectionPost:
    """POST /settings/toml-section/{section}"""

    def test_save_agent_types(self, client, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        toml_content = """
default_agent_type = "claude"

[agent_types.claude]
command = ["claude"]
description = "Claude Code"
"""
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.post(
                "/settings/toml-section/agent_types",
                json={"content": toml_content},
            )
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

        # Verify persisted
        from voxtype.config import load_config
        config = load_config(config_file)
        assert config.default_agent_type == "claude"
        assert "claude" in config.agent_types
        assert config.agent_types["claude"].command == ["claude"]

    def test_save_agent_types_preserves_continue_args(self, client, tmp_path):
        """continue_args must survive a round-trip through the TOML editor."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        toml_content = """
[agent_types.sonnet]
command = ["claude", "--model", "claude-sonnet-4-6"]
continue_args = ["-c"]
description = "Claude Sonnet"
"""
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.post(
                "/settings/toml-section/agent_types",
                json={"content": toml_content},
            )
        assert r.status_code == 200

        from voxtype.config import load_config
        config = load_config(config_file)
        assert config.agent_types["sonnet"].continue_args == ["-c"]

    def test_serialize_agent_types_includes_continue_args(self, client, tmp_path):
        """GET agent_types returns continue_args from the raw config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            '[agent_types.sonnet]\n'
            'command = ["claude", "--model", "claude-sonnet-4-6"]\n'
            'continue_args = ["-c"]\n'
        )
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.get("/settings/toml-section/agent_types")
        assert r.status_code == 200
        assert "continue_args" in r.json()["content"]
        assert '"-c"' in r.json()["content"]

    def test_fetch_preserves_user_comments(self, client, tmp_path):
        """GET agent_types preserves comments the user added to the file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            "# my custom comment\n"
            "[agent_types.sonnet]\n"
            'command = ["claude"]\n'
        )
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.get("/settings/toml-section/agent_types")
        assert r.status_code == 200
        assert "my custom comment" in r.json()["content"]

    def test_invalid_toml_returns_422(self, client):
        r = client.post(
            "/settings/toml-section/agent_types",
            json={"content": "[[[ invalid toml ==="},
        )
        assert r.status_code == 422

    def test_missing_command_returns_422(self, client, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        toml_content = """
[agent_types.claude]
description = "Missing command field"
"""
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.post(
                "/settings/toml-section/agent_types",
                json={"content": toml_content},
            )
        assert r.status_code == 422

    def test_empty_content_returns_400(self, client):
        r = client.post(
            "/settings/toml-section/agent_types",
            json={"content": "   "},
        )
        assert r.status_code == 400

    def test_unknown_section_returns_404(self, client):
        r = client.post(
            "/settings/toml-section/nonexistent",
            json={"content": "foo = 1"},
        )
        assert r.status_code == 404

    def test_save_shortcuts(self, client, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text("")
        toml_content = """
[[keyboard.shortcuts]]
keys = "ctrl+shift+l"
command = "toggle-listening"
"""
        with patch("voxtype.config.get_config_path", return_value=config_file):
            r = client.post(
                "/settings/toml-section/keyboard.shortcuts",
                json={"content": toml_content},
            )
        assert r.status_code == 200

        from voxtype.config import load_config
        config = load_config(config_file)
        assert len(config.keyboard.shortcuts) == 1
        assert config.keyboard.shortcuts[0]["keys"] == "ctrl+shift+l"
        assert config.keyboard.shortcuts[0]["command"] == "toggle-listening"
