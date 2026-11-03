"""Add the noema-spss server to Claude Desktop's config without touching other settings.

Usage (Claude Desktop must be fully closed):
    C:\\noema\\.venv\\Scripts\\python.exe tools\\add_to_claude_config.py [config_path]

Without config_path, the usual locations are tried. The easiest way to find
the real one: Settings > Desktop app > Extensions > Local MCP servers > Edit config.
A backup is written next to the file as claude_desktop_config.json.yedek.
"""
import glob
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def candidates():
    local = os.environ.get("LOCALAPPDATA", "")
    appdata = os.environ.get("APPDATA", "")
    yield from glob.glob(os.path.join(local, "Claude-Data", "*", "claude_desktop_config.json"))
    yield os.path.join(appdata, "Claude", "claude_desktop_config.json")
    yield os.path.expanduser("~/Library/Application Support/Claude/claude_desktop_config.json")


def find_spss_python():
    hits = sorted(glob.glob(r"C:\Program Files\IBM\SPSS\Statistics\*\Python3\python.exe"))
    return hits[-1] if hits else None


def main():
    if len(sys.argv) > 1:
        cfg = Path(sys.argv[1])
    else:
        found = [Path(p) for p in candidates() if os.path.isfile(p)]
        if not found:
            sys.exit("Config bulunamadi. Yolunu arguman olarak verin (Edit config ile bulabilirsiniz).")
        cfg = found[0]

    data = {}
    if cfg.exists() and cfg.read_text(encoding="utf-8").strip():
        shutil.copy2(cfg, str(cfg) + ".yedek")
        data = json.loads(cfg.read_text(encoding="utf-8"))

    python = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    env = {"PYTHONPATH": str(ROOT)}
    spss_py = os.environ.get("NOEMA_SPSS_PYTHON") or find_spss_python()
    if spss_py:
        env["NOEMA_SPSS_PYTHON"] = spss_py

    data.setdefault("mcpServers", {})["noema-spss"] = {
        "command": str(python),
        "args": ["-m", "noema_mcp.server"],
        "cwd": str(ROOT),
        "env": env,
    }
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print("EKLENDI:", cfg)
    print("SPSS Python:", spss_py or "BULUNAMADI - NOEMA_SPSS_PYTHON ayarlayin")


if __name__ == "__main__":
    main()
