"""Tests for TTS isolated venv management."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Venv path construction
# ---------------------------------------------------------------------------


def test_venv_paths():
    """Venv dirs use correct structure under ~/.local/share/dictare/tts-env/."""
    from dictare.tts.venv import get_venv_dir

    for engine in ("piper", "coqui", "outetts", "kokoro"):
        venv_dir = get_venv_dir(engine)
        assert venv_dir == Path.home() / ".local" / "share" / "dictare" / "tts-env" / engine


def test_get_venv_python_returns_none_for_missing(tmp_path: Path):
    """get_venv_python returns None when venv doesn't exist."""
    from dictare.tts.venv import get_venv_python

    with patch("dictare.tts.venv._VENV_ROOT", tmp_path):
        for engine in ("piper", "coqui", "outetts", "kokoro"):
            assert get_venv_python(engine) is None


def test_get_venv_python_returns_none_for_system_engines():
    """System engines (say, espeak) should never use a venv."""
    from dictare.tts.venv import get_venv_python

    assert get_venv_python("say") is None
    assert get_venv_python("espeak") is None


def test_get_venv_bin_dir_returns_none_for_missing(tmp_path: Path):
    """get_venv_bin_dir returns None when venv doesn't exist."""
    from dictare.tts.venv import get_venv_bin_dir

    with patch("dictare.tts.venv._VENV_ROOT", tmp_path):
        for engine in ("piper", "coqui", "outetts", "kokoro"):
            assert get_venv_bin_dir(engine) is None


def test_get_venv_bin_dir_returns_none_for_non_venv_engines():
    """Non-venv engines return None from get_venv_bin_dir."""
    from dictare.tts.venv import get_venv_bin_dir

    assert get_venv_bin_dir("say") is None
    assert get_venv_bin_dir("espeak") is None
    assert get_venv_bin_dir("unknown") is None


# ---------------------------------------------------------------------------
# Dictare source path
# ---------------------------------------------------------------------------


def test_get_dictare_src_path():
    """get_dictare_src_path returns a directory containing the dictare package."""
    from dictare.tts.venv import get_dictare_src_path

    src_path = Path(get_dictare_src_path())
    assert src_path.is_dir()
    assert (src_path / "dictare").is_dir()
    assert (src_path / "dictare" / "__init__.py").is_file()


# ---------------------------------------------------------------------------
# is_venv_installed
# ---------------------------------------------------------------------------


def test_is_venv_installed_false_when_missing(tmp_path: Path):
    """is_venv_installed returns False when venv doesn't exist."""
    from dictare.tts.venv import is_venv_installed

    with patch("dictare.tts.venv._VENV_ROOT", tmp_path):
        for engine in ("piper", "coqui", "outetts", "kokoro"):
            assert is_venv_installed(engine) is False


def test_is_venv_installed_with_existing_python(tmp_path: Path):
    """is_venv_installed returns True when venv python exists."""
    from dictare.tts.venv import is_venv_installed

    with patch("dictare.tts.venv._VENV_ROOT", tmp_path):
        # Create a fake venv with a python binary
        venv_dir = tmp_path / "piper" / "bin"
        venv_dir.mkdir(parents=True)
        (venv_dir / "python").touch()

        assert is_venv_installed("piper") is True


# ---------------------------------------------------------------------------
# EngineStatus venv fields
# ---------------------------------------------------------------------------


def test_engine_status_venv_fields():
    """check_all_tts_engines includes venv_installed and needs_venv fields."""
    from dictare.utils.platform import check_all_tts_engines

    engines = check_all_tts_engines()
    assert len(engines) >= 6  # say, espeak, piper, coqui, outetts, kokoro

    # System engines don't need venvs
    for eng in engines:
        if eng["name"] in ("say", "espeak"):
            assert eng["needs_venv"] is False
            assert eng["venv_installed"] is False

    # Venv engines should have needs_venv=True
    venv_names = {"piper", "coqui", "outetts", "kokoro"}
    for eng in engines:
        if eng["name"] in venv_names:
            assert eng["needs_venv"] is True
            assert "venv_installed" in eng


def test_engine_status_to_dict_includes_venv_fields():
    """EngineStatus.to_dict() includes venv_installed and needs_venv."""
    from dictare.utils.platform import EngineStatus

    status = EngineStatus(
        name="piper",
        available=True,
        description="test",
        platform_ok=True,
        install_hint="",
        needs_venv=True,
        venv_installed=True,
    )
    d = status.to_dict()
    assert d["needs_venv"] is True
    assert d["venv_installed"] is True


# ---------------------------------------------------------------------------
# install_venv / uninstall_venv
# ---------------------------------------------------------------------------


def test_install_venv_unknown_engine():
    """install_venv raises ValueError for unknown engine."""
    from dictare.tts.venv import install_venv

    with pytest.raises(ValueError, match="Unknown venv engine"):
        install_venv("unknown_engine")


def test_uninstall_venv_unknown_engine():
    """uninstall_venv raises ValueError for unknown engine."""
    from dictare.tts.venv import uninstall_venv

    with pytest.raises(ValueError, match="Unknown venv engine"):
        uninstall_venv("unknown_engine")


def test_uninstall_venv_when_not_installed(tmp_path: Path):
    """uninstall_venv succeeds even if venv doesn't exist."""
    from dictare.tts.venv import uninstall_venv

    with patch("dictare.tts.venv._VENV_ROOT", tmp_path):
        assert uninstall_venv("piper") is True


# ---------------------------------------------------------------------------
# Spawn worker uses venv python
# ---------------------------------------------------------------------------


def test_spawn_worker_uses_venv_python():
    """_spawn_worker uses venv python and injects PYTHONPATH when venv exists."""
    mock_config = MagicMock()
    mock_config.tts.engine = "piper"
    mock_config.tts.language = "en"
    mock_config.tts.speed = 175
    mock_config.tts.voice = ""

    mock_http = MagicMock()
    mock_http.port = 8770
    mock_http._tts_connected_event = MagicMock()
    mock_http._tts_connected_event.is_set.return_value = True

    fake_venv_python = "/fake/tts-env/piper/bin/python"
    fake_src_path = "/fake/src"

    with (
        patch("dictare.tts.venv.get_venv_python", return_value=fake_venv_python),
        patch("dictare.tts.venv.get_worker_pythonpath", return_value=fake_src_path),
        patch("subprocess.Popen") as mock_popen,
    ):
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        from dictare.core.tts_manager import TTSManager

        mgr = TTSManager(mock_config)
        mgr._spawn_worker(mock_http)

        # Verify Popen was called with venv python
        popen_call = mock_popen.call_args
        cmd = popen_call[0][0]
        assert cmd[0] == fake_venv_python

        # Verify PYTHONPATH and COQUI_TOS_AGREED were set in env
        env = popen_call[1].get("env")
        assert env is not None
        assert env["PYTHONPATH"] == fake_src_path
        assert env["COQUI_TOS_AGREED"] == "1"


def test_spawn_worker_uses_sys_executable_without_venv():
    """_spawn_worker falls back to sys.executable when no venv exists."""
    import sys

    mock_config = MagicMock()
    mock_config.tts.engine = "espeak"
    mock_config.tts.language = "en"
    mock_config.tts.speed = 175
    mock_config.tts.voice = ""

    mock_http = MagicMock()
    mock_http.port = 8770
    mock_http._tts_connected_event = MagicMock()
    mock_http._tts_connected_event.is_set.return_value = True

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        from dictare.core.tts_manager import TTSManager

        mgr = TTSManager(mock_config)
        mgr._spawn_worker(mock_http)

        popen_call = mock_popen.call_args
        cmd = popen_call[0][0]
        assert cmd[0] == sys.executable

        # Env includes COQUI_TOS_AGREED but no PYTHONPATH (no venv)
        env = popen_call[1].get("env")
        assert env is not None
        assert env["COQUI_TOS_AGREED"] == "1"
        assert "PYTHONPATH" not in env


# ---------------------------------------------------------------------------
# VENV_ENGINES registry
# ---------------------------------------------------------------------------


def test_venv_engines_registry():
    """VENV_ENGINES has expected engine entries with package lists."""
    from dictare.tts.venv import VENV_ENGINES

    assert "piper" in VENV_ENGINES
    assert "coqui" in VENV_ENGINES
    assert "outetts" in VENV_ENGINES

    # System engines should NOT be in VENV_ENGINES
    assert "say" not in VENV_ENGINES
    assert "espeak" not in VENV_ENGINES

    # Each entry should be a list of package names
    for engine, packages in VENV_ENGINES.items():
        assert isinstance(packages, list)
        assert len(packages) > 0
        for pkg in packages:
            assert isinstance(pkg, str)
