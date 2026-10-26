"""Build the frozen nbalake app into dist/nbalake and pack it as dist/nbalake-<platform>.tar.gz.

Usage: uv run --group build python packaging/build.py
"""

from __future__ import annotations

import os
import platform
import shutil
import tarfile
from pathlib import Path

import duckdb
import PyInstaller.__main__

from nbalake.explore.skills import DOCS
from nbalake.runtime import EXTENSIONS

REPO = Path(__file__).resolve().parent.parent
DIST = REPO / "dist"
WORK = REPO / "build"
EXTENSION_NAMES = ("ducklake", "sqlite")


def platform_name() -> str:
    machine = {"x86_64": "x86_64", "amd64": "x86_64", "arm64": "arm64", "aarch64": "arm64"}
    system = {"Darwin": "macos", "Linux": "linux"}[platform.system()]
    return f"{system}-{machine[platform.machine().lower()]}"


def install_extensions(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)
    con = duckdb.connect(config={"extension_directory": str(directory)})
    for name in EXTENSION_NAMES:
        con.execute(f"INSTALL {name}")
    con.close()


def build() -> Path:
    extensions = WORK / EXTENSIONS
    install_extensions(extensions)
    data = [(REPO / "docs" / name, f"docs/{name}") for name in DOCS]
    PyInstaller.__main__.run(
        [
            str(REPO / "packaging" / "launcher.py"),
            "--name=nbalake",
            "--onedir",
            "--noconfirm",
            "--clean",
            f"--distpath={DIST}",
            f"--workpath={WORK}",
            f"--specpath={WORK}",
            "--collect-data=nbalake",
            "--collect-submodules=nbalake",
            "--collect-all=duckdb",
            *(f"--add-data={src}{os.pathsep}{dest}" for src, dest in data),
        ]
    )
    app = DIST / "nbalake"
    # Copied after PyInstaller so it never re-signs them, which breaks DuckDB's signature footer.
    shutil.copytree(extensions, app / "_internal" / EXTENSIONS)
    (app / "nba").symlink_to("nbalake")
    archive = DIST / f"nbalake-{platform_name()}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(app, arcname="nbalake")
    return archive


if __name__ == "__main__":
    print(build())
