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


def analysis(kind: str, path: str, **params) -> dict:
    req = {"action": "analysis", "kind": kind, "path": path}
    req.update({k: v for k, v in params.items() if v is not None})
    return call_worker(req)


# Every analysis tool returns: syntax (exact SPSS syntax that ran), spss_menu
# (where the same dialog lives in the SPSS GUI, English UI) and tables
# (every output table, flattened to cells with a row/column path).


@mcp.tool()
def run_descriptives(path: str, variables: list[str],
                     statistics: list[str] | None = None) -> dict:
    """Betimsel istatistik (DESCRIPTIVES). Surekli/olcek degiskenler icin.

    statistics: MEAN, STDDEV, MIN, MAX, VARIANCE, RANGE, SUM, SEMEAN,
                SKEWNESS, KURTOSIS. Bos: MEAN STDDEV MIN MAX SKEWNESS KURTOSIS.
    """
    return analysis("descriptives", path, variables=variables, statistics=statistics)


@mcp.tool()
def run_frequencies(path: str, variables: list[str],
                    statistics: list[str] | None = None) -> dict:
    """Frekans tablosu (FREQUENCIES). Kategorik degiskenler ve demografik bilgiler icin.

    statistics (istege bagli): MEAN, MEDIAN, MODE, STDDEV, VARIANCE, MINIMUM,
                MAXIMUM, RANGE, SKEWNESS, KURTOSIS, SEMEAN, SUM.
    """
    return analysis("frequencies", path, variables=variables, statistics=statistics)


@mcp.tool()
def run_normality(path: str, variables: list[str], group: str | None = None) -> dict:
    """Normallik testi (EXAMINE): Kolmogorov-Smirnov ve Shapiro-Wilk, carpiklik/basiklik.

    group verilirse her grup icin ayri test yapilir (t-testi/ANOVA oncesi bu kullanilmali).
    """
    return analysis("normality", path, variables=variables, group=group)


@mcp.tool()
def run_ttest_independent(path: str, variables: list[str], group: str,
                          group_values: list[str | float]) -> dict:
    """Bagimsiz orneklem t-testi. Levene testi ve etki buyuklugu (Cohen's d) dahil.

    group: iki gruplu degisken; group_values: karsilastirilacak iki kod, or. [1, 2] veya ["f", "m"].
    """
    return analysis("ttest_independent", path, variables=variables,
                    group=group, group_values=group_values)


@mcp.tool()
def run_ttest_paired(path: str, pairs: list[list[str]]) -> dict:
    """Bagimli (eslestirilmis) orneklem t-testi, etki buyuklugu dahil.

    pairs: [["on_test", "son_test"], ...]
    """
    return analysis("ttest_paired", path, pairs=pairs)


@mcp.tool()
def run_anova_oneway(path: str, variables: list[str], group: str,
                     posthoc: list[str] | None = None) -> dict:
    """Tek yonlu ANOVA: betimsel, Levene, Welch, eta-kare ve post hoc.

    group: sayisal kodlu grup degiskeni. posthoc: TUKEY, GH (Games-Howell),
    BONFERRONI, SCHEFFE, LSD, T2, DUNNETT. Bos: TUKEY GH.
    """
    return analysis("anova_oneway", path, variables=variables, group=group, posthoc=posthoc)


@mcp.tool()
def run_correlation(path: str, variables: list[str], method: str = "pearson") -> dict:
    """Korelasyon matrisi. method: "pearson" (normal dagilim) veya "spearman" (siralama/normal degil)."""
    return analysis("correlation", path, variables=variables, method=method)


@mcp.tool()
def run_crosstabs(path: str, row: str, column: str) -> dict:
    """Capraz tablo ve ki-kare testi (Phi/Cramer's V ve beklenen frekanslar dahil)."""
    return analysis("crosstabs", path, row=row, column=column)


@mcp.tool()
def run_mann_whitney(path: str, variables: list[str], group: str,
                     group_values: list[str | float]) -> dict:
    """Mann-Whitney U: normal dagilmayan veride bagimsiz t-testinin alternatifi."""
    return analysis("mann_whitney", path, variables=variables,
                    group=group, group_values=group_values)


@mcp.tool()
def run_kruskal_wallis(path: str, variables: list[str], group: str,
                       group_range: list[float]) -> dict:
    """Kruskal-Wallis H: normal dagilmayan veride tek yonlu ANOVA'nin alternatifi.

    group_range: grup kodlarinin en kucugu ve en buyugu, or. [1, 4].
    """
    return analysis("kruskal_wallis", path, variables=variables,
                    group=group, group_range=group_range)


@mcp.tool()
def run_wilcoxon(path: str, pairs: list[list[str]]) -> dict:
    """Wilcoxon isaretli siralar: normal dagilmayan veride bagimli t-testinin alternatifi."""
    return analysis("wilcoxon", path, pairs=pairs)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
