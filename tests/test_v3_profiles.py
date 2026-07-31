from __future__ import annotations

import json
from pathlib import Path

import pytest

from selflensbahtinov.assembly_config import (
    MechanicalProfile,
    ProfileValidationError,
    load_mechanical_profile,
    load_print_preset,
    mechanical_profile_dir,
    print_preset_dir,
    search_mechanical_profiles,
)
from selflensbahtinov.cli import main


PROFILE_SLUGS = {"fujifilm-xf100-400", "fujifilm-xf16-80"}


def test_official_profile_catalog_is_schema_v3_only():
    paths = sorted(mechanical_profile_dir().glob("*.json"))
    profiles = [load_mechanical_profile(path) for path in paths]

    assert {profile.slug for profile in profiles} == PROFILE_SLUGS
    assert all(profile.schema_version == 3 for profile in profiles)
    assert all(profile.mounts == () for profile in profiles)


def test_official_unmeasured_profile_is_valid_but_not_assemblable():
    profile = load_mechanical_profile(
        mechanical_profile_dir() / "fujifilm-xf100-400.json"
    )

    assert profile.is_complete is False
    with pytest.raises(ProfileValidationError, match="no measured mounting surface"):
        profile.select_mount()


def test_schema_v2_is_rejected_without_migration(tmp_path: Path):
    path = tmp_path / "old-v2.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "manufacturer": "Old",
                "model": "Profile",
                "slug": "old-profile",
                "label": "OLD",
                "mounts": [],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(
        ProfileValidationError,
        match="only schema version 3 is accepted",
    ):
        load_mechanical_profile(path)


def test_default_print_preset_is_official_and_valid():
    preset = load_print_preset(print_preset_dir() / "default-pla.json")

    assert preset.name == "default-pla"
    assert preset.fit_clearance_mm == pytest.approx(0.35)
    assert preset.mask_thickness_mm == pytest.approx(2.0)
    assert preset.ring_wall_thickness_mm == pytest.approx(3.0)


def test_profile_search_reports_the_official_catalog():
    results = search_mechanical_profiles("Fujifilm")
    assert {profile.slug for profile in results} == PROFILE_SLUGS


def test_cli_creates_profile_then_adds_a_mount(tmp_path: Path, capsys):
    profile_path = tmp_path / "custom-lens.json"

    assert (
        main(
            [
                "create-profile",
                "--manufacturer",
                "Example",
                "--model",
                "Lens 100",
                "--label",
                "L100",
                "--output",
                str(profile_path),
            ]
        )
        == 0
    )
    created = load_mechanical_profile(profile_path)
    assert created == MechanicalProfile(
        schema_version=3,
        manufacturer="Example",
        model="Lens 100",
        slug="example-lens-100",
        label="L100",
        mounts=(),
    )

    assert (
        main(
            [
                "add-mount",
                str(profile_path),
                "--name",
                "hood-front-outer",
                "--type",
                "outer-slip-fit",
                "--diameter-mm",
                "92.6",
                "--usable-depth-mm",
                "8.0",
                "--status",
                "measured",
                "--preferred",
            ]
        )
        == 0
    )

    updated = load_mechanical_profile(profile_path)
    mount = updated.select_mount()
    assert mount.name == "hood-front-outer"
    assert mount.diameter_mm == pytest.approx(92.6)
    assert mount.usable_depth_mm == pytest.approx(8.0)
    assert mount.preferred is True
    capsys.readouterr()


def test_cli_search_show_and_validate_use_v3_profiles(capsys):
    assert main(["search", "100-400"]) == 0
    search_output = capsys.readouterr().out
    assert "fujifilm-xf100-400" in search_output
    assert "needs-measurement" in search_output

    assert main(["show", "fujifilm-xf100-400"]) == 0
    show_output = capsys.readouterr().out
    assert "mounts: none measured yet" in show_output

    assert main(["validate", "fujifilm-xf100-400"]) == 0
    validate_output = capsys.readouterr().out
    assert "OK schema-v3" in validate_output


def test_legacy_profile_system_is_removed_from_the_repository():
    assert not Path("profiles").exists()
    assert not Path("src/selflensbahtinov/validation.py").exists()
    assert not Path("src/selflensbahtinov/generator.py").exists()
    assert not Path(".github/workflows/generate-mask.yml").exists()
