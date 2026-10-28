"""
tests/test_app_config.py
------------------------
Unit tests for app_config load/save/validate and launcher safety checks.
Uses a temp directory — never touches the real config file.
"""

import sys, os, json, tempfile
from pathlib import Path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from unittest.mock import patch
from copy import deepcopy

import src.app_config as ac
from src.launcher import launch, get_launch_map, _open_url, _open_app


# ── Helpers ───────────────────────────────────────────────────────────────────
def _tmp_cfg_path(tmp_path: Path) -> Path:
    return tmp_path / "data" / "visionassist_config.json"


def _patch_paths(tmp_path: Path):
    """Redirect DATA_DIR and CONFIG_FILE to a temp directory."""
    data_dir    = tmp_path / "data"
    config_file = data_dir / "visionassist_config.json"
    return (
        patch.object(ac, "DATA_DIR",    data_dir),
        patch.object(ac, "CONFIG_FILE", config_file),
    )


# ════════════════════════════════════════════════════════════════════════════
# app_config tests
# ════════════════════════════════════════════════════════════════════════════

class TestAppConfigLoad:
    def test_creates_default_when_missing(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        assert "registered_apps" in cfg
        assert "profiles" in cfg
        assert cfg["schema_version"] == 1

    def test_config_file_written_on_first_load(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            ac.load()
            config_file = tmp_path / "data" / "visionassist_config.json"
            assert config_file.exists()

    def test_roundtrip_save_and_load(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
            cfg["registered_apps"].append({
                "name": "TestApp", "type": "app",
                "path_or_url": "testapp.exe",
                "launch_gesture": "PEACE", "enabled": True,
            })
            ac.save(cfg)
            loaded = ac.load()
        names = [a["name"] for a in loaded["registered_apps"]]
        assert "TestApp" in names

    def test_invalid_json_raises_runtime_error(self, tmp_path):
        data_dir = tmp_path / "data"
        data_dir.mkdir(parents=True)
        cfg_file = data_dir / "visionassist_config.json"
        cfg_file.write_text("{bad json", encoding="utf-8")
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            with pytest.raises(RuntimeError, match="Cannot read config"):
                ac.load()


class TestAppConfigValidation:
    def test_duplicate_app_names_deduplicated(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        cfg["registered_apps"] = [
            {"name": "A", "type": "app", "path_or_url": "a.exe",
             "launch_gesture": None, "enabled": True},
            {"name": "A", "type": "app", "path_or_url": "a2.exe",
             "launch_gesture": None, "enabled": True},
        ]
        validated = ac._validate(cfg)
        names = [a["name"] for a in validated["registered_apps"]]
        assert names.count("A") == 1

    def test_invalid_gesture_set_to_none(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        cfg["registered_apps"] = [{
            "name": "X", "type": "app", "path_or_url": "x.exe",
            "launch_gesture": "FLYING_KICK",   # not valid
            "enabled": True,
        }]
        validated = ac._validate(cfg)
        assert validated["registered_apps"][0]["launch_gesture"] is None

    def test_active_profile_corrected_if_missing(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        cfg["active_profile"] = "nonexistent_profile"
        validated = ac._validate(cfg)
        assert validated["active_profile"] in cfg["profiles"]

    def test_validate_app_entry_website_needs_http(self):
        err = ac.validate_app_entry("website", "ftp://example.com")
        assert err is not None
        assert "http" in err.lower()

    def test_validate_app_entry_valid_url(self):
        err = ac.validate_app_entry("website", "https://www.google.com")
        assert err is None

    def test_validate_app_entry_empty_path(self):
        err = ac.validate_app_entry("app", "")
        assert err is not None

    def test_validate_app_entry_bare_exe_ok(self):
        # Bare exe names are allowed (resolved via PATH at launch time)
        err = ac.validate_app_entry("app", "notepad.exe")
        assert err is None


class TestAppConfigHelpers:
    def test_get_app_found(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        app = ac.get_app(cfg, "Notepad")
        assert app is not None
        assert app["name"] == "Notepad"

    def test_get_app_not_found(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        assert ac.get_app(cfg, "DoesNotExist") is None

    def test_add_app(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        cfg = ac.add_app(cfg, "Calc", "app", "calc.exe", "PEACE")
        names = [a["name"] for a in cfg["registered_apps"]]
        assert "Calc" in names

    def test_add_app_replaces_existing(self, tmp_path):
        p1, p2 = _patch_paths(tmp_path)
        with p1, p2:
            cfg = ac.load()
        cfg = ac.add_app(cfg, "Notepad", "app", "notepad2.exe", "POINTING")
        notepads = [a for a in cfg["registered_apps"] if a["name"] == "Notepad"]
        assert len(notepads) == 1
        assert notepads[0]["path_or_url"] == "notepad2.exe"


# ════════════════════════════════════════════════════════════════════════════
# Launcher tests
# ════════════════════════════════════════════════════════════════════════════

class TestLauncher:
    def test_disabled_app_not_launched(self):
        entry = {"name": "Notepad", "type": "app", "path_or_url": "notepad.exe",
                 "enabled": False}
        ok, msg = launch(entry)
        assert ok is False
        assert "disabled" in msg.lower()

    def test_empty_path_returns_error(self):
        entry = {"name": "X", "type": "app", "path_or_url": "", "enabled": True}
        ok, msg = launch(entry)
        assert ok is False

    def test_invalid_url_scheme_returns_error(self):
        ok, msg = _open_url("ftp://example.com", "Test")
        assert ok is False
        assert "invalid" in msg.lower() or "http" in msg.lower()

    def test_nonexistent_absolute_path_returns_error(self):
        ok, msg = _open_app("/absolute/nonexistent/app.exe", "Test")
        assert ok is False
        assert "not found" in msg.lower()

    def test_get_launch_map_only_enabled(self):
        cfg = {
            "registered_apps": [
                {"name": "A", "type": "app", "path_or_url": "a.exe",
                 "launch_gesture": "THUMBS_UP", "enabled": True},
                {"name": "B", "type": "app", "path_or_url": "b.exe",
                 "launch_gesture": "PEACE", "enabled": False},   # disabled
            ]
        }
        m = get_launch_map(cfg)
        assert "THUMBS_UP" in m
        assert "PEACE" not in m

    def test_get_launch_map_first_wins_on_duplicate_gesture(self):
        cfg = {
            "registered_apps": [
                {"name": "A", "type": "app", "path_or_url": "a.exe",
                 "launch_gesture": "THUMBS_UP", "enabled": True},
                {"name": "B", "type": "app", "path_or_url": "b.exe",
                 "launch_gesture": "THUMBS_UP", "enabled": True},  # same gesture
            ]
        }
        m = get_launch_map(cfg)
        assert m["THUMBS_UP"]["name"] == "A"

    def test_get_launch_map_no_gesture_excluded(self):
        cfg = {
            "registered_apps": [
                {"name": "A", "type": "app", "path_or_url": "a.exe",
                 "launch_gesture": None, "enabled": True},
            ]
        }
        m = get_launch_map(cfg)
        assert len(m) == 0

    def test_open_url_calls_webbrowser(self):
        with patch("webbrowser.open", return_value=True) as mock_open:
            ok, msg = _open_url("https://www.google.com", "Google")
        assert ok is True
        mock_open.assert_called_once_with("https://www.google.com")
        assert "Google" in msg
