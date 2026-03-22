# Copyright 2026 Duke
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Slicer detection for different platforms."""

from __future__ import annotations

import os
import platform
import shutil
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Slicer:
    key: str
    display: str
    default_profile_dirs: list[Path]  # user may override


def _detect_user_dirs(base: Path) -> list[Path]:
    """
    Find user subdirectories under base/user/.
    Matches numeric user IDs (e.g. 12345) and 'default' (logged-out profile).
    Returns sorted list of discovered user dirs (numeric first, then 'default').
    """
    user_root = base / "user"
    if not user_root.exists():
        return []

    found = []
    for entry in user_root.iterdir():
        if entry.is_dir() and (entry.name.isdigit() or entry.name == "default"):
            found.append(entry)
    # Sort numeric IDs first, then "default"
    return sorted(found, key=lambda p: (not p.name.isdigit(), p.name))


def _unique_dirs(*sources: list[Path]) -> list[Path]:
    """Merge multiple lists of Paths, removing duplicates while preserving order."""
    seen: set[Path] = set()
    result: list[Path] = []
    for dirs in sources:
        for d in dirs:
            resolved = d.resolve()
            if resolved not in seen:
                seen.add(resolved)
                result.append(d)
    return result


# ---- Portable data_dir detection ------------------------------------------------

# Map slicer keys to their executable names for shutil.which() lookup
_SLICER_EXECUTABLES: dict[str, list[str]] = {
    "orcaslicer": ["orca-slicer", "OrcaSlicer"],
    "bambustudio": ["bambu-studio", "BambuStudio"],
    "snapmakerorca": ["snapmaker-orca-slicer", "SnapmakerOrcaSlicer"],
    "elegooslicer": ["elegoo-slicer", "ElegooSlicer"],
}

# Common install directories per platform
_WINDOWS_INSTALL_DIRS: dict[str, list[str]] = {
    "orcaslicer": ["OrcaSlicer"],
    "bambustudio": ["BambuStudio"],
    "snapmakerorca": ["SnapmakerOrcaSlicer"],
    "elegooslicer": ["ElegooSlicer"],
}

_MACOS_APP_NAMES: dict[str, list[str]] = {
    "orcaslicer": ["OrcaSlicer.app"],
    "bambustudio": ["BambuStudio.app"],
    "snapmakerorca": ["SnapmakerOrcaSlicer.app"],
    "elegooslicer": ["ElegooSlicer.app"],
}

# Flatpak app IDs (Linux only) — multiple IDs per slicer supported
_FLATPAK_IDS: dict[str, list[tuple[str, str]]] = {
    # slicer_key: [(flatpak_app_id, config_folder_name), ...]
    "orcaslicer": [
        ("io.github.orcaslicer.OrcaSlicer", "OrcaSlicer"),
        ("io.github.softfever.OrcaSlicer", "OrcaSlicer"),
    ],
    "bambustudio": [
        ("com.bambulab.BambuStudio", "BambuStudio"),
    ],
}


def _detect_data_dir(slicer_key: str) -> list[Path]:
    """
    Detect portable data_dir folders for a slicer.

    OrcaSlicer (and forks) support a portable mode where a folder named
    'data_dir' placed next to the executable is used instead of the
    standard config location.  This function checks:
      1. Common install paths per platform
      2. The executable found via PATH (shutil.which)

    Returns user dirs found inside any discovered data_dir, or [].
    """
    candidates: list[Path] = []
    system = platform.system()

    if system == "Windows":
        # Check Program Files directories
        for pf in ["PROGRAMFILES", "PROGRAMFILES(X86)"]:
            pf_path = os.getenv(pf)
            if not pf_path:
                continue
            for dirname in _WINDOWS_INSTALL_DIRS.get(slicer_key, []):
                candidates.append(Path(pf_path) / dirname)

    elif system == "Darwin":
        # Check /Applications/<App>.app/Contents/MacOS/
        for app_name in _MACOS_APP_NAMES.get(slicer_key, []):
            candidates.append(
                Path("/Applications") / app_name / "Contents" / "MacOS")

    # All platforms: check executable on PATH
    for exe_name in _SLICER_EXECUTABLES.get(slicer_key, []):
        exe_path = shutil.which(exe_name)
        if exe_path:
            candidates.append(Path(exe_path).resolve().parent)

    # Collect user dirs from all data_dir candidates
    all_dirs: list[Path] = []
    for candidate in candidates:
        data_dir = candidate / "data_dir"
        all_dirs.extend(_detect_user_dirs(data_dir))

    return all_dirs


def _detect_flatpak_dirs(slicer_key: str) -> list[Path]:
    """Detect profile dirs inside Flatpak sandboxed config."""
    entries = _FLATPAK_IDS.get(slicer_key, [])
    all_dirs: list[Path] = []
    for app_id, config_name in entries:
        flatpak_base = Path.home() / ".var" / "app" / app_id / "config" / config_name
        all_dirs.extend(_detect_user_dirs(flatpak_base))
    return all_dirs


def _detect_creality_version(app_support: Path) -> list[Path]:
    """
    Detect Creality Print installation directory.
    Checks for version 7.0, then 6.0 if not found.
    Format: ~/Library/Application Support/Creality/Creality Print/7.0/
    """
    creality_base = app_support / "Creality" / "Creality Print"

    # Try version 7 first, then version 6
    for version in ["7.0", "6.0"]:
        version_dir = creality_base / version
        if version_dir.exists():
            return [version_dir]

    # If neither exists, return empty list
    return []


def _macos_default_slicers() -> list[Slicer]:
    """
    macOS slicer profile locations.
    Collects from portable data_dir and standard Application Support paths.
    """
    home = Path.home()
    app_support = home / "Library" / "Application Support"

    orca_base = app_support / "OrcaSlicer"
    snapmaker_base = app_support / "Snapmaker_Orca"
    bambu_base = app_support / "BambuStudio"
    elegoo_base = app_support / "ElegooSlicer"

    orca_dirs = _unique_dirs(
        _detect_user_dirs(orca_base),
        _detect_data_dir("orcaslicer"),
    )
    snapmaker_dirs = _unique_dirs(
        _detect_user_dirs(snapmaker_base),
        _detect_data_dir("snapmakerorca"),
    )
    bambu_dirs = _unique_dirs(
        _detect_user_dirs(bambu_base),
        _detect_data_dir("bambustudio"),
    )
    creality_dirs = _detect_creality_version(app_support)
    elegoo_dirs = _unique_dirs(
        _detect_user_dirs(elegoo_base),
        _detect_data_dir("elegooslicer"),
    )

    return [
        Slicer(
            key="orcaslicer",
            display="Orca Slicer",
            default_profile_dirs=orca_dirs if orca_dirs else [
                orca_base / "user" / "default"],
        ),
        Slicer(
            key="bambustudio",
            display="Bambu Studio",
            default_profile_dirs=bambu_dirs if bambu_dirs else [
                bambu_base / "user" / "default"],
        ),
        Slicer(
            key="snapmakerorca",
            display="Snapmaker Orca",
            default_profile_dirs=snapmaker_dirs if snapmaker_dirs else [
                snapmaker_base / "user" / "default"],
        ),
        Slicer(
            key="crealityprint",
            display="Creality Print",
            default_profile_dirs=creality_dirs if creality_dirs else [
                app_support / "Creality" / "Creality Print" / "7.0"],
        ),
        Slicer(
            key="elegooslicer",
            display="Elegoo Slicer",
            default_profile_dirs=elegoo_dirs if elegoo_dirs else [
                elegoo_base / "user" / "default"],
        ),
    ]


def _linux_default_slicers() -> list[Slicer]:
    """
    Linux slicer profile locations.
    Collects from native (~/.config/), Flatpak, and portable data_dir paths.
    """
    home = Path.home()
    config_dir = home / ".config"

    orca_base = config_dir / "OrcaSlicer"
    snapmaker_base = config_dir / "SnapmakerOrcaSlicer"
    bambu_base = config_dir / "BambuStudio"
    elegoo_base = config_dir / "ElegooSlicer"

    orca_dirs = _unique_dirs(
        _detect_user_dirs(orca_base),
        _detect_flatpak_dirs("orcaslicer"),
        _detect_data_dir("orcaslicer"),
    )
    snapmaker_dirs = _unique_dirs(
        _detect_user_dirs(snapmaker_base),
        _detect_data_dir("snapmakerorca"),
    )
    bambu_dirs = _unique_dirs(
        _detect_user_dirs(bambu_base),
        _detect_flatpak_dirs("bambustudio"),
        _detect_data_dir("bambustudio"),
    )
    elegoo_dirs = _unique_dirs(
        _detect_user_dirs(elegoo_base),
        _detect_data_dir("elegooslicer"),
    )

    # Creality Print on Linux
    creality_base = config_dir / "Creality" / "Creality Print"
    creality_dirs = []
    for version in ["7.0", "6.0"]:
        version_dir = creality_base / version
        if version_dir.exists():
            creality_dirs = [version_dir]
            break

    return [
        Slicer(
            key="orcaslicer",
            display="Orca Slicer",
            default_profile_dirs=orca_dirs if orca_dirs else [
                orca_base / "user" / "default"],
        ),
        Slicer(
            key="bambustudio",
            display="Bambu Studio",
            default_profile_dirs=bambu_dirs if bambu_dirs else [
                bambu_base / "user" / "default"],
        ),
        Slicer(
            key="snapmakerorca",
            display="Snapmaker Orca",
            default_profile_dirs=snapmaker_dirs if snapmaker_dirs else [
                snapmaker_base / "user" / "default"],
        ),
        Slicer(
            key="crealityprint",
            display="Creality Print",
            default_profile_dirs=creality_dirs if creality_dirs else [
                creality_base / "7.0"],
        ),
        Slicer(
            key="elegooslicer",
            display="Elegoo Slicer",
            default_profile_dirs=elegoo_dirs if elegoo_dirs else [
                elegoo_base / "user" / "default"],
        ),
    ]


def _windows_default_slicers() -> list[Slicer]:
    """
    Windows slicer profile locations.
    Collects from standard AppData and portable data_dir paths.
    """
    appdata = Path(os.getenv("APPDATA", ""))
    if not appdata or not appdata.exists():
        appdata = Path.home() / "AppData" / "Roaming"

    orca_base = appdata / "OrcaSlicer"
    snapmaker_base = appdata / "Snapmaker_Orca"
    bambu_base = appdata / "BambuStudio"
    elegoo_base = appdata / "ElegooSlicer"
    creality_base = appdata / "Creality" / "Creality Print"

    orca_dirs = _unique_dirs(
        _detect_user_dirs(orca_base),
        _detect_data_dir("orcaslicer"),
    )
    snapmaker_dirs = _unique_dirs(
        _detect_user_dirs(snapmaker_base),
        _detect_data_dir("snapmakerorca"),
    )
    bambu_dirs = _unique_dirs(
        _detect_user_dirs(bambu_base),
        _detect_data_dir("bambustudio"),
    )
    elegoo_dirs = _unique_dirs(
        _detect_user_dirs(elegoo_base),
        _detect_data_dir("elegooslicer"),
    )

    creality_dirs = []
    for version in ["7.0", "6.0"]:
        version_dir = creality_base / version
        if version_dir.exists():
            creality_dirs = [version_dir]
            break

    return [
        Slicer(
            key="orcaslicer",
            display="Orca Slicer",
            default_profile_dirs=orca_dirs if orca_dirs else [
                orca_base / "user" / "default"],
        ),
        Slicer(
            key="bambustudio",
            display="Bambu Studio",
            default_profile_dirs=bambu_dirs if bambu_dirs else [
                bambu_base / "user" / "default"],
        ),
        Slicer(
            key="snapmakerorca",
            display="Snapmaker Orca",
            default_profile_dirs=snapmaker_dirs if snapmaker_dirs else [
                snapmaker_base / "user" / "default"],
        ),
        Slicer(
            key="crealityprint",
            display="Creality Print",
            default_profile_dirs=creality_dirs if creality_dirs else [
                creality_base / "7.0"],
        ),
        Slicer(
            key="elegooslicer",
            display="Elegoo Slicer",
            default_profile_dirs=elegoo_dirs if elegoo_dirs else [
                elegoo_base / "user" / "default"],
        ),
    ]


def get_default_slicers() -> list[Slicer]:
    """
    Get default slicer paths for the current platform.
    """
    system = platform.system()
    if system == "Darwin":  # macOS
        return _macos_default_slicers()
    elif system == "Windows":
        return _windows_default_slicers()
    else:  # Linux or other Unix-like
        return _linux_default_slicers()
