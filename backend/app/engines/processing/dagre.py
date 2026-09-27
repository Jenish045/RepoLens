"""Server-side Dagre layout, persisted once when module membership is analysed."""

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

NODE_SCRIPT = Path(__file__).with_name("dagre_layout.cjs")
NODE_WIDTH = 260
NODE_HEIGHT = 142


def layout_modules(modules: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        raise RuntimeError("Node.js is required for the configured Dagre module layout.")
    payload = {
        "nodes": [{"id": module["id"], "width": NODE_WIDTH, "height": NODE_HEIGHT} for module in modules],
        "edges": edges,
    }
    env = os.environ.copy()
    backend_root = Path(__file__).resolve().parents[3]
    repository_root = backend_root.parent
    local_modules = backend_root / "node_modules"
    development_modules = repository_root / "frontend" / "node_modules"
    module_search_paths = [str(path) for path in (local_modules, development_modules) if path.exists()]
    if module_search_paths:
        env["NODE_PATH"] = os.pathsep.join(module_search_paths + ([env["NODE_PATH"]] if env.get("NODE_PATH") else []))
    result = subprocess.run(
        [node, str(NODE_SCRIPT)],
        input=json.dumps(payload, sort_keys=True, separators=(",", ":")),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
        check=True,
        env=env,
    )
    positions = json.loads(result.stdout)
    if set(positions) != {module["id"] for module in modules}:
        raise RuntimeError("Dagre did not return a position for every module.")
    return positions
