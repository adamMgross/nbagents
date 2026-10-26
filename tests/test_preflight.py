from __future__ import annotations

from pathlib import Path

from nbalake import preflight

GB = 2**30
ROOT = Path("/lake")


def test_a_supported_platform_with_room_for_the_whole_lake_has_no_problems() -> None:
    for platform in ("linux", "darwin"):
        assert preflight.problems(platform, preflight.REQUIRED_BYTES, 0, ROOT) == []


def test_windows_is_told_to_use_wsl() -> None:
    (problem,) = preflight.problems("win32", preflight.REQUIRED_BYTES, 0, ROOT)

    assert "WSL" in problem


def test_too_little_free_disk_names_the_shortfall_and_the_way_to_move_the_lake() -> None:
    (problem,) = preflight.problems("linux", 10 * GB, 0, ROOT)

    assert f"{preflight.REQUIRED_BYTES / GB:.0f} GB" in problem
    assert "10 GB" in problem
    assert "NBALAKE_ROOT" in problem


def test_a_partly_built_lake_counts_toward_the_space_it_needs() -> None:
    built = 30 * GB

    assert preflight.problems("linux", preflight.REQUIRED_BYTES - built, built, ROOT) == []
    assert preflight.problems("linux", preflight.REQUIRED_BYTES - built - GB, built, ROOT) != []


def test_free_bytes_of_a_lake_not_yet_created_measures_its_nearest_existing_parent(
    tmp_path: Path,
) -> None:
    assert preflight.free_bytes(tmp_path / "a" / "b" / "lake") > 0


def test_lake_bytes_sums_every_file_under_the_root_and_is_zero_before_it_exists(
    tmp_path: Path,
) -> None:
    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "blob").write_bytes(b"x" * 300)
    (tmp_path / "catalog.sqlite").write_bytes(b"x" * 20)

    assert preflight.lake_bytes(tmp_path) == 320
    assert preflight.lake_bytes(tmp_path / "missing") == 0
