from __future__ import annotations

from pathlib import Path


def create_windows_shortcut(shortcut_path: Path, target_path: Path) -> bool:
    try:
        import win32com.client  # type: ignore[import-not-found]
    except ImportError:
        return False

    shell = win32com.client.Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.WorkingDirectory = str(target_path.parent)
    shortcut.Description = f"FileFlow: moved to {target_path.parent}"
    shortcut.save()
    return True
