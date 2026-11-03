"""Noema MCP server.

Runs on a modern Python (3.10+, needed by the MCP SDK). Every SPSS job is
handed to worker/spss_worker.py, which runs on SPSS's own bundled Python.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "worker" / "spss_worker.py"
LOG_DIR = Path(os.environ.get("NOEMA_LOG_DIR", Path.home() / "Noema" / "logs"))
TIMEOUT = int(os.environ.get("NOEMA_TIMEOUT", "300"))

mcp = FastMCP("noema-spss")


def find_spss_python() -> str:
    """NOEMA_SPSS_PYTHON wins; otherwise look in the usual install folders."""
    env = os.environ.get("NOEMA_SPSS_PYTHON")
    if env:
        return env
    if platform.system() == "Windows":
        patterns = [r"C:\Program Files\IBM\SPSS\Statistics\*\Python3\python.exe",
                    r"C:\Program Files\IBM\SPSS Statistics\*\Python3\python.exe"]
    else:  # macOS: to be confirmed on a real Mac install
        patterns = ["/Applications/IBM SPSS Statistics*/Python3/bin/python3*",
                    "/Applications/IBM SPSS Statistics*/*/Python3/bin/python3*"]
    hits = sorted(h for p in patterns for h in glob.glob(p))
    if not hits:
        raise RuntimeError("SPSS Python bulunamadi. NOEMA_SPSS_PYTHON ortam "
                           "degiskenine SPSS'in python.exe yolunu yazin.")
    return hits[-1]  # newest version


def call_worker(request: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="noema_") as tmp:
        req_path = Path(tmp) / "request.json"
        resp_path = Path(tmp) / "response.json"
        req_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [find_spss_python(), str(WORKER), str(req_path), str(resp_path)],
            # stdin must NOT be inherited: it is the MCP stdio pipe.
            stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if not resp_path.exists():
            return {"ok": False, "error": "Isci sureci yanit yazmadi.",
                    "returncode": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", "replace")[-4000:]}
        resp = json.loads(resp_path.read_text(encoding="utf-8"))
    log_run(request, resp)
    return resp


def log_run(request: dict, response: dict) -> None:
    """Append every run to a JSONL log, and the syntax to a .sps file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().isoformat(timespec="seconds")
    with open(LOG_DIR / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": now, "request": request, "response": response},
                           ensure_ascii=False) + "\n")
    syntax = (response.get("result") or {}).get("syntax")
    if syntax:
        with open(LOG_DIR / "syntax.sps", "a", encoding="utf-8") as f:
            f.write(f"* Noema {now} - {request.get('path')}.\n"
                    f"GET FILE='{request.get('path')}'.\n{syntax}\n\n")


@mcp.tool()
def check_spss() -> dict:
    """SPSS motoruna ulasilabildigini test eder. Ilk kullanimda calistirin."""
    return call_worker({"action": "ping"})


@mcp.tool()
def inspect_dataset(path: str) -> dict:
    """Bir .sav dosyasindaki degiskenleri, etiketleri, olcum duzeylerini,
    deger etiketlerini ve eksik deger tanimlarini dondurur.

    path: .sav dosyasinin tam yolu (or. C:\\Users\\...\\tez.sav)
    """
    return call_worker({"action": "inspect", "path": path})


@mcp.tool()
def run_descriptives(path: str, variables: list[str],
                     statistics: list[str] | None = None) -> dict:
    """SPSS DESCRIPTIVES komutunu calistirir ve gercek SPSS tablosunu dondurur.

    path: .sav dosyasinin tam yolu
    variables: sayisal degisken adlari (inspect_dataset ciktisindaki 'name')
    statistics: MEAN, STDDEV, MIN, MAX, VARIANCE, RANGE, SUM, SEMEAN,
                SKEWNESS, KURTOSIS. Bos birakilirsa MEAN STDDEV MIN MAX
                SKEWNESS KURTOSIS kullanilir.
    Yanittaki 'syntax' alani, ayni analizin SPSS syntax'idir.
    """
    return call_worker({"action": "descriptives", "path": path,
                        "variables": variables, "statistics": statistics})


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
