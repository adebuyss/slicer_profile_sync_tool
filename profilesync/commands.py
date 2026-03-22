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

"""Command implementations for profilesync CLI."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .config import Config
from .git import (
    clone_or_open_repo,
    ensure_git_available,
    git_has_commits,
    guard_not_dev_repo,
    initialize_empty_repo,
    run,
    suggest_repo_dir_from_remote,
    validate_git_remote,
)
from .slicers import get_default_slicers, Slicer
from .sync import (
    export_from_slicers_to_repo,
    rebuild_exported_from_git,
)
from .ui import (
    dim,
    error,
    get_check_symbol,
    highlight,
    info,
    pick_many,
    pick_one,
    success,
)


def interactive_select_slicers(slicers: list[Slicer]) -> list[str] | None:
    """Interactively select which slicers to enable. Returns None if user quits."""
    labels = [s.display for s in slicers]
    selected = pick_many("Select slicers to sync:", labels)
    if selected is None:
        return None
    if not selected:
        return []
    chosen_names = [labels[i] for i in selected]
    print(f"  {success(get_check_symbol())} {', '.join(chosen_names)}")
    return [slicers[i].key for i in selected]


def interactive_configure_paths(enabled: list[str], slicers: list[Slicer]) -> dict[str, list[str]]:
    """Configure profile directories for each enabled slicer.

    When multiple directories are discovered (e.g. native + Flatpak +
    portable data_dir), the user is shown a numbered list and can pick
    one or more entries (comma-separated) or enter a custom path.
    """
    by_key = {s.key: s for s in slicers}
    result: dict[str, list[str]] = {}

    for key in enabled:
        s = by_key[key]
        dirs = s.default_profile_dirs

        # --- No directories found ---
        if not dirs:
            print(f"\n{highlight(s.display)}: (No directory auto-detected)")
            print("  Enter the profile directory path:")
            raw = input("> ").strip()
            result[key] = [raw] if raw else []
            continue

        # --- Exactly one directory found (original behaviour) ---
        if len(dirs) == 1:
            d = dirs[0]
            exists_marker = success(
                get_check_symbol()) if d.exists() else error("X")
            print(f"\n{highlight(s.display)}: [{exists_marker}] {d}")
            print(
                f"  Press {highlight('[ENTER]')} to use this directory, or enter a custom path:")
            raw = input("> ").strip()
            if not raw:
                result[key] = [str(d)]
            else:
                result[key] = [raw]
            continue

        # --- Multiple directories found – interactive picker ---
        labels = []
        for d in dirs:
            exists_marker = success(
                get_check_symbol()) if d.exists() else error("X")
            labels.append(f"[{exists_marker}] {d}")
        labels.append("Enter a custom path...")
        custom_idx = len(labels) - 1

        # Pre-check all real dirs, leave custom unchecked
        checked = [True] * len(dirs) + [False]

        print()  # spacing
        selected = pick_many(
            f"{highlight(s.display)}: Select profile directories:",
            labels,
            checked=checked,
        )

        if selected is None:
            # Cancelled — default to first dir
            result[key] = [str(dirs[0])]
            print(f"  {dim('(using default)')}")
            continue

        chosen: list[str] = []
        needs_custom = False
        for i in selected:
            if i == custom_idx:
                needs_custom = True
            elif i < len(dirs):
                chosen.append(str(dirs[i]))

        if needs_custom:
            custom = input("  Enter custom path: ").strip()
            if custom:
                chosen.append(custom)

        result[key] = chosen if chosen else [str(dirs[0])]

        n_chosen = len(result[key])
        print(f"  {success(get_check_symbol())} {n_chosen} director{'y' if n_chosen == 1 else 'ies'} selected")

    return result


# ---- Command implementations ---------------------------------------------------

def cmd_init(args: argparse.Namespace) -> int:
    """Initialize configuration and clone remote repo."""
    ensure_git_available()

    slicers = get_default_slicers()

    if args.remote:
        remote = args.remote
    else:
        print("GitHub remote (SSH recommended), e.g. git@github.com:USER/REPO.git")
        remote = input("Remote URL: ").strip()
        if not remote:
            print("Remote URL is required.")
            return 2

    # Validate the remote URL and check access
    is_valid, error_msg = validate_git_remote(remote)
    if not is_valid:
        print(error(f"\nError: {error_msg}"))
        return 2

    print(success(f"{get_check_symbol()} Remote repository is accessible\n"))

    suggested_repo_dir = suggest_repo_dir_from_remote(remote)

    if args.repo_dir:
        repo_dir = Path(args.repo_dir).expanduser()
    else:
        print(
            f"Local clone directory (press {highlight('[ENTER]')} to use default):\n  {suggested_repo_dir}")
        repo_dir_raw = input("Repo dir: ").strip()
        repo_dir = Path(repo_dir_raw).expanduser(
        ) if repo_dir_raw else suggested_repo_dir

    guard_not_dev_repo(repo_dir)

    enabled = interactive_select_slicers(slicers)
    if enabled is None:
        print(info("\nAborted. No changes were made to remote or local files."))
        return 0
    if not enabled:
        print("No slicers selected.")
        return 2

    paths = interactive_configure_paths(enabled, slicers)

    clone_or_open_repo(repo_dir, remote)

    # Configure editor for conflict resolution
    if args.editor:
        editor_cmd = args.editor
    else:
        git_editor = os.environ.get("GIT_EDITOR") or os.environ.get("EDITOR")

        editor_choices = [
            ("vim", "Vim"),
            ("nano", "Nano"),
            ("subl -w", "Sublime Text"),
            ("code --wait", "VS Code"),
        ]

        labels = [name for _, name in editor_choices]
        custom_idx = len(labels)
        labels.append("Custom (enter manually)")
        if git_editor:
            labels.append(f"Git default editor ({git_editor})")
        else:
            labels.append("Git default editor")

        choice = pick_one("\nSelect editor for conflict resolution:", labels)

        if choice is None:
            print(info("\nAborted. No changes were made to remote or local files."))
            return 0
        elif choice < len(editor_choices):
            editor_cmd = editor_choices[choice][0]
            print(f"  {success(get_check_symbol())} {labels[choice]}")
        elif choice == custom_idx:
            editor_cmd = input("  Enter editor command: ").strip() or None
        else:
            editor_cmd = git_editor
            print(f"  {success(get_check_symbol())} {labels[choice]}")

    cfg = Config(
        github_remote=remote,
        repo_dir=repo_dir,
        enabled_slicers=enabled,
        slicer_profile_dirs=paths,
        editor_cmd=editor_cmd,
    )
    cfg.save()
    print(f"\nSaved config to {Config.path()}")
    print(f"Repo directory: {repo_dir}")
    print("Next: run `profilesync sync`")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """Show current configuration."""
    cfg = Config.load()
    print(json.dumps({
        "github_remote": cfg.github_remote,
        "repo_dir": str(cfg.repo_dir),
        "enabled_slicers": cfg.enabled_slicers,
        "slicer_profile_dirs": cfg.slicer_profile_dirs,
        "editor_cmd": cfg.editor_cmd,
    }, indent=2))
    return 0


def cmd_reconfig(args: argparse.Namespace) -> int:
    """Re-detect slicer directories and let the user reconfigure paths.

    Loads the existing config, re-scans for profile directories on disk,
    then lets the user pick which ones to use.  Optionally re-select
    which slicers are enabled with --slicers or set import destinations
    with --dest.
    """
    cfg = Config.load()
    slicers = get_default_slicers()

    if args.slicers:
        # Let user re-pick which slicers to sync
        enabled = interactive_select_slicers(slicers)
        if enabled is None:
            print(info("\nAborted. Config unchanged."))
            return 0
        if not enabled:
            print("No slicers selected.")
            return 2
    else:
        enabled = cfg.enabled_slicers
        # Show what's currently enabled
        print("Currently enabled slicers:")
        by_key = {s.key: s for s in slicers}
        for key in enabled:
            display = by_key[key].display if key in by_key else key
            print(f"  {highlight(display)}")
        print(dim("  (use --slicers to change this selection)\n"))

    paths = interactive_configure_paths(enabled, slicers)

    cfg.enabled_slicers = enabled
    cfg.slicer_profile_dirs = paths

    # Import destination selection
    if args.dest:
        from .sync import SLICER_DISPLAY_NAMES
        import_dest: dict[str, str] = {}
        for key in enabled:
            dirs = paths.get(key, [])
            if len(dirs) <= 1:
                continue
            display = SLICER_DISPLAY_NAMES.get(key, key.capitalize())
            print()
            idx = pick_one(
                f"Import destination for {highlight(display)}:",
                dirs,
            )
            if idx is not None:
                import_dest[key] = dirs[idx]
                print(f"  {success(get_check_symbol())} {dirs[idx]}")
        if import_dest:
            cfg.import_dest = import_dest

    cfg.save()

    print(f"\n{success(get_check_symbol())} Config updated at {Config.path()}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    """Main sync command - launches the interactive TUI."""
    ensure_git_available()
    cfg = Config.load()
    # Check if repo is empty and initialize if needed
    clone_or_open_repo(cfg.repo_dir, cfg.github_remote)
    if not git_has_commits(cfg.repo_dir):
        initialize_empty_repo(cfg.repo_dir, cfg.github_remote)

    # 1) Fetch from server first to show accurate "remote state"
    result = run(["git", "ls-remote", "origin", "HEAD"],
                 cwd=cfg.repo_dir, check=False)
    remote_has_commits = result.returncode == 0 and result.stdout.strip()

    run(["git", "fetch", "origin"], cwd=cfg.repo_dir, check=False)

    # 2) Export current slicer state into the repo working tree, then
    #    read *all* uncommitted differences (not just what this call copied)
    export_from_slicers_to_repo(cfg)
    exported = rebuild_exported_from_git(cfg)

    # 3) Launch the interactive TUI
    from .tui import SyncApp, build_status_text
    status_text = build_status_text(
        cfg, exported, bool(remote_has_commits))
    app = SyncApp(
        cfg=cfg, exported=exported, status_text=status_text)
    result_code = app.run()
    return result_code if isinstance(result_code, int) else 0
