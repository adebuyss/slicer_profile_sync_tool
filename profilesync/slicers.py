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
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Slicer:
    key: str
    display: str
    default_profile_dirs: list[Path]  # user may override


def _detect_user_dirs(base: Path) -> list[Path]:
    """
    Find numeric user_id subdirectories under base/user/.
    e.g. ~/Library/Application Support/BambuStudio/user/12345/
    Returns sorted list of discovered user dirs.
    """
    user_root = base / "user"
    if not user_root.exists():
        return []

    found = []
    for entry in user_root.iterdir():
        if entry.is_dir() and entry.name.isdigit():
            found.append(entry)
    return sorted(found, key=lambda p: p.name)


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

    # Look for data_dir/user/<numeric_id>/ in each candidate
    for candidate in candidates:
        data_dir = candidate / "data_dir"
        user_dirs = _detect_user_dirs(data_dir)
        if user_dirs:
            return user_dirs

    return []


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
    macOS slicer profile locations (auto-detect numeric user_id subdirs).
    Checks portable data_dir first, then standard Application Support paths.
    """
    home = Path.home()
    app_support = home / "Library" / "Application Support"

    # OrcaSlicer and variants
    orca_base = app_support / "OrcaSlicer"
    snapmaker_base = app_support / "Snapmaker_Orca"

    # Bambu Studio
    bambu_base = app_support / "BambuStudio"

    # Elegoo Slicer (based on OrcaSlicer)
    elegoo_base = app_support / "ElegooSlicer"

    # Check portable data_dir first, then standard paths
    orca_dirs = _detect_data_dir("orcaslicer") or _detect_user_dirs(orca_base)
    snapmaker_dirs = _detect_data_dir("snapmakerorca") or _detect_user_dirs(snapmaker_base)
    bambu_dirs = _detect_data_dir("bambustudio") or _detect_user_dirs(bambu_base)
    creality_dirs = _detect_creality_version(app_support)
    elegoo_dirs = _detect_data_dir("elegooslicer") or _detect_user_dirs(elegoo_base)

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
    Checks portable data_dir first, then native (~/.config/), then Flatpak paths.
    """
    home = Path.home()
    config_dir = home / ".config"
    flatpak_dir = home / ".var" / "app"

    # Native paths under ~/.config/
    orca_base = config_dir / "OrcaSlicer"
    snapmaker_base = config_dir / "SnapmakerOrcaSlicer"
    bambu_base = config_dir / "BambuStudio"
    elegoo_base = config_dir / "ElegooSlicer"

    # Flatpak paths
    flatpak_orca_base = flatpak_dir / "io.github.softfever.OrcaSlicer" / "config" / "OrcaSlicer"
    flatpak_bambu_base = flatpak_dir / "com.bambulab.BambuStudio" / "config" / "BambuStudio"

    # Check portable data_dir first, then native, then Flatpak
    orca_dirs = (
        _detect_data_dir("orcaslicer")
        or _detect_user_dirs(orca_base)
        or _detect_user_dirs(flatpak_orca_base)
    )
    snapmaker_dirs = _detect_data_dir("snapmakerorca") or _detect_user_dirs(snapmaker_base)
    bambu_dirs = (
        _detect_data_dir("bambustudio")
        or _detect_user_dirs(bambu_base)
        or _detect_user_dirs(flatpak_bambu_base)
    )
    elegoo_dirs = _detect_data_dir("elegooslicer") or _detect_user_dirs(elegoo_base)

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
    Windows slicer profile locations (auto-detect numeric user_id subdirs).
    """
    # Windows uses %APPDATA% which is typically C:\Users\USERNAME\AppData\Roaming
    appdata = Path(os.getenv("APPDATA", ""))
    if not appdata or not appdata.exists():
        # Fallback to constructing the path manually
        appdata = Path.home() / "AppData" / "Roaming"

    # OrcaSlicer and variants
    orca_base = appdata / "OrcaSlicer"
    snapmaker_base = appdata / "Snapmaker_Orca"

    # Bambu Studio
    bambu_base = appdata / "BambuStudio"

    # Elegoo Slicer (based on OrcaSlicer)
    elegoo_base = appdata / "ElegooSlicer"

    # Creality Print on Windows
    # Typically in %APPDATA%\Creality\Creality Print\7.0
    creality_base = appdata / "Creality" / "Creality Print"

    # Check portable data_dir first, then standard AppData paths
    orca_dirs = _detect_data_dir("orcaslicer") or _detect_user_dirs(orca_base)
    snapmaker_dirs = _detect_data_dir("snapmakerorca") or _detect_user_dirs(snapmaker_base)
    bambu_dirs = _detect_data_dir("bambustudio") or _detect_user_dirs(bambu_base)
    elegoo_dirs = _detect_data_dir("elegooslicer") or _detect_user_dirs(elegoo_base)

    # Detect Creality Print version on Windows
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
