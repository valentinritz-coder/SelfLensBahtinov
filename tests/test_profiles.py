from __future__ import annotations

from pathlib import Path

from selflensbahtinov.validation import load_profile


def test_bundled_profiles_load() -> None:
    profile_paths = sorted(Path("profiles").glob("*.json"))
    assert profile_paths
    for path in profile_paths:
        profile = load_profile(path)
        assert profile.slug == path.stem
        assert profile.filter_thread_mm > 0


def test_known_filter_threads() -> None:
    assert load_profile(Path("profiles/fujifilm-xf100-400.json")).filter_thread_mm == 77.0
    assert load_profile(Path("profiles/fujifilm-xf16-80.json")).filter_thread_mm == 72.0
