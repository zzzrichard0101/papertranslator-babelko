"""Local, presentation-only preferences for the desktop workbench."""

from copy import deepcopy

from .storage import read, root, save


DEFAULTS = {
    "theme": "paper",
    "accent": "teal",
    "glass": True,
    "motion": True,
    "density": "comfortable",
    "preview_layout": "spread",
    "text_scale": 1.0,
}

CHOICES = {
    "theme": {"paper", "night"},
    "accent": {"teal", "iris", "coral"},
    "density": {"comfortable", "compact"},
    "preview_layout": {"spread", "focus"},
    "text_scale": {0.9, 1.0, 1.1, 1.2},
}


def normalize(value):
    """Discard unknown or malformed values without affecting translation options."""
    result = deepcopy(DEFAULTS)
    if not isinstance(value, dict):
        return result
    for key, choices in CHOICES.items():
        candidate = value.get(key)
        if type(candidate) in (str, float, int) and candidate in choices:
            result[key] = candidate
    for key in ("glass", "motion"):
        if type(value.get(key)) is bool:
            result[key] = value[key]
    return result


def load():
    path = root() / "ui-settings.json"
    try:
        return normalize(read(path))
    except (OSError, ValueError, TypeError):
        return deepcopy(DEFAULTS)


def store(value):
    settings = normalize(value)
    save(root() / "ui-settings.json", settings)
    return settings
