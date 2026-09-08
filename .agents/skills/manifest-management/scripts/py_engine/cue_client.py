import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


def find_workspace_root(start_path: Optional[Path] = None) -> Path:
    """Finds the workspace root directory by searching parents."""
    if "WORKSPACE_ROOT" in os.environ:
        return Path(os.environ["WORKSPACE_ROOT"])
    curr = (start_path or Path.cwd()).resolve()
    for p in [curr, *curr.parents]:
        if (p / "cue" / "cue.mod").exists():
            return p
        if (p / "cue.mod").exists():
            return p
    return Path.cwd()


class CueClient:
    """Client for invoking and interacting with the CUE toolchain."""

    def __init__(self, workspace_root: Optional[str] = None):
        if workspace_root is None:
            self.workspace_root = find_workspace_root(Path(__file__).resolve())
        else:
            self.workspace_root = Path(workspace_root)

        cue_dir = self.workspace_root / "cue"
        if (cue_dir / "cue.mod").exists():
            self.cue_root = cue_dir
        else:
            self.cue_root = self.workspace_root

    def vet(self) -> tuple[bool, str]:
        """Runs cue vet across the CUE configuration project."""
        cmd = ["cue", "vet", "./..."]
        res = subprocess.run(
            cmd,
            cwd=str(self.cue_root),
            capture_output=True,
            text=True,
        )
        return res.returncode == 0, res.stderr or res.stdout

    def export_system(self) -> Dict[str, Any]:
        """Exports the unified system manifest data structure as a dictionary."""
        cmd = ["cue", "export", "./catalog", "-e", "system"]
        res = subprocess.run(
            cmd,
            cwd=str(self.cue_root),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"CUE export failed: {res.stderr or res.stdout}")
        return json.loads(res.stdout)

    def eval_expression(self, expr: str) -> Dict[str, Any]:
        """Evaluates a specific CUE expression and returns parsed JSON."""
        cmd = ["cue", "export", "./catalog", "-e", expr]
        res = subprocess.run(
            cmd,
            cwd=str(self.cue_root),
            capture_output=True,
            text=True,
        )
        if res.returncode != 0:
            raise RuntimeError(f"CUE eval expression '{expr}' failed: {res.stderr or res.stdout}")
        return json.loads(res.stdout)

