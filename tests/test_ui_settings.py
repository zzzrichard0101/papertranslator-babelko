from babelko import ui_settings


def test_ui_preferences_are_local_and_invalid_values_revert(monkeypatch, tmp_path):
    monkeypatch.setenv("BABELKO_HOME", str(tmp_path))
    assert ui_settings.load() == ui_settings.DEFAULTS

    saved = ui_settings.store({
        "theme": "night", "accent": "iris", "glass": False,
        "motion": False, "density": "compact", "preview_layout": "focus",
        "text_scale": 1.2, "mode": "qwen",
    })
    assert saved["theme"] == "night"
    assert saved["preview_layout"] == "focus"
    assert "mode" not in saved
    assert ui_settings.load() == saved

    ui_settings.store({"theme": "unknown", "text_scale": 4, "motion": "no"})
    assert ui_settings.load() == ui_settings.DEFAULTS
