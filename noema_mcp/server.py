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
import atexit
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent

ROOT = Path(__file__).resolve().parent.parent
WORKER = ROOT / "worker" / "spss_worker.py"
LOG_DIR = Path(os.environ.get("NOEMA_LOG_DIR", Path.home() / "Noema" / "logs"))
TIMEOUT = int(os.environ.get("NOEMA_TIMEOUT", "300"))
# 1 (default): keep one SPSS engine running between calls. 0: start SPSS per call.
PERSISTENT = os.environ.get("NOEMA_PERSISTENT", "1") != "0"
IDLE_SECONDS = int(float(os.environ.get("NOEMA_IDLE_MINUTES", "30")) * 60)
START_TIMEOUT = int(os.environ.get("NOEMA_START_TIMEOUT", "180"))
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

INSTRUCTIONS = """Noema, yerel IBM SPSS Statistics motorunda analiz calistirir.
Kurallar:
- Tum istatistikler bu araclardan, yani SPSS'ten gelmeli. Hicbir testi Python ile
  ya da elle hesaplama; bir arac hata verirse hatayi kullaniciya acikca bildir
  ve SPSS'te nasil cozulecegini anlat, sonucu baska yoldan uretme.
- Istenen analiz icin arac yoksa (ya da gorunmuyorsa) bunu soyle ve DUR. Baska
  bir aracin ciktisindan formulle turetme yapma (or. korelasyonlardan R^2 veya
  beta hesaplamak yasak). Kullanici araci guncellemeyi unutmus olabilir:
  "git pull yapip Claude'u yeniden baslatin" de.
- path her zaman .sav dosyasinin TAM yoludur. Bilmiyorsan kullanicidan iste.
- Analizden once inspect_dataset ile degisken adlarini, olcum duzeylerini ve
  eksik deger tanimlarini kontrol et.
- Her sonucta calisan syntax'i ve spss_menu yolunu kullaniciya goster.
"""

mcp = FastMCP("noema-spss", instructions=INSTRUCTIONS)


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


class WarmWorker:
    """One long-lived SPSS worker, reached over a localhost socket.

    Started on first use. If it dies (idle timeout, crash, SPSS error that
    kills the engine) it is restarted once, transparently, on the next call.
    """

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen | None = None
        self.stream = None
        self.sock: socket.socket | None = None
        self.token = ""
        self.started_at = 0.0

    def _start(self) -> None:
        self._stop()
        self.token = secrets.token_hex(16)
        tmpdir = tempfile.mkdtemp(prefix="noema_")
        port_file = os.path.join(tmpdir, "port")
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        log = open(LOG_DIR / "worker.log", "ab")
        env = dict(os.environ, NOEMA_TOKEN=self.token,
                   NOEMA_IDLE_SECONDS=str(IDLE_SECONDS))
        self.proc = subprocess.Popen(
            [find_spss_python(), str(WORKER), "--serve", port_file],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            env=env, creationflags=NO_WINDOW,
        )
        log.close()
        deadline = time.monotonic() + START_TIMEOUT
        while not os.path.exists(port_file):
            if self.proc.poll() is not None:
                raise RuntimeError("SPSS isci sureci baslarken kapandi. "
                                   f"Ayrinti: {LOG_DIR / 'worker.log'}")
            if time.monotonic() > deadline:
                self._stop()
                raise RuntimeError("SPSS motoru zamaninda baslamadi.")
            time.sleep(0.2)
        port = int(Path(port_file).read_text())
        self.sock = socket.create_connection(("127.0.0.1", port), timeout=10)
        self.sock.settimeout(TIMEOUT)
        self.stream = self.sock.makefile("rwb")
        self.started_at = time.monotonic()

    def _alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None and self.stream is not None

    def _stop(self) -> None:
        for closer in (getattr(self.stream, "close", None), getattr(self.sock, "close", None)):
            try:
                if closer:
                    closer()
            except OSError:
                pass
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = self.stream = self.sock = None

    def request(self, req: dict) -> dict:
        with self.lock:
            last_error = None
            for _ in range(2):  # one transparent restart
                fresh = False
                try:
                    if not self._alive():
                        self._start()
                        fresh = True
                    payload = dict(req, token=self.token)
                    self.stream.write((json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.stream.flush()
                    line = self.stream.readline()
                    if not line:
                        raise ConnectionError("Isci sureci baglantiyi kapatti")
                    resp = json.loads(line.decode("utf-8"))
                    resp["engine"] = "yeni baslatildi" if fresh else "sicak"
                    return resp
                except socket.timeout:
                    self._stop()
                    return {"ok": False, "error": f"SPSS {TIMEOUT} sn icinde yanit vermedi; motor yeniden baslatilacak."}
                except (OSError, ConnectionError, ValueError) as e:
                    last_error = e
                    self._stop()
            return {"ok": False, "error": f"SPSS isci sureciyle iletisim kurulamadi: {last_error}",
                    "log": str(LOG_DIR / "worker.log")}

    def shutdown(self) -> None:
        with self.lock:
            if self._alive():
                try:
                    self.stream.write((json.dumps({"action": "shutdown", "token": self.token}) + "\n").encode())
                    self.stream.flush()
                except OSError:
                    pass
            self._stop()


WORKER_POOL = WarmWorker()
atexit.register(WORKER_POOL.shutdown)


def call_worker_oneshot(request: dict) -> dict:
    with tempfile.TemporaryDirectory(prefix="noema_") as tmp:
        req_path = Path(tmp) / "request.json"
        resp_path = Path(tmp) / "response.json"
        req_path.write_text(json.dumps(request, ensure_ascii=False), encoding="utf-8")
        proc = subprocess.run(
            [find_spss_python(), str(WORKER), str(req_path), str(resp_path)],
            # stdin must NOT be inherited: it is the MCP stdio pipe.
            stdin=subprocess.DEVNULL, capture_output=True, timeout=TIMEOUT,
            creationflags=NO_WINDOW,
        )
        if not resp_path.exists():
            return {"ok": False, "error": "Isci sureci yanit yazmadi.",
                    "returncode": proc.returncode,
                    "stderr": proc.stderr.decode("utf-8", "replace")[-4000:]}
        return json.loads(resp_path.read_text(encoding="utf-8"))


def call_worker(request: dict) -> dict:
    t0 = time.monotonic()
    resp = WORKER_POOL.request(request) if PERSISTENT else call_worker_oneshot(request)
    resp["elapsed_seconds"] = round(time.monotonic() - t0, 2)
    log_run(request, resp)
    return resp


def log_run(request: dict, response: dict) -> None:
    """Append every run to a JSONL log, and the syntax to a .sps file."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now().isoformat(timespec="seconds")
    logged = response
    result = response.get("result")
    if isinstance(result, dict) and result.get("charts"):
        logged = dict(response, result=dict(result, charts=["%d grafik" % len(result["charts"])]))
    with open(LOG_DIR / "runs.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"time": now, "request": request, "response": logged},
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


def analysis(kind: str, path: str, filter_variable=None, filter_value=None, **params):
    req = {"action": "analysis", "kind": kind, "path": path}
    if filter_variable:
        if filter_value is None:
            return {"ok": False, "error": "filter_variable verildiyse filter_value da gerekli"}
        req["filter"] = {"variable": filter_variable, "value": filter_value}
    req.update({k: v for k, v in params.items() if v is not None and v is not False})
    resp = call_worker(req)
    return with_charts(resp)


def with_charts(resp: dict):
    """Move PNG charts out of the JSON and send them as MCP image content, so
    Claude can look at boxplots, Q-Q plots, residual and scree plots."""
    result = resp.get("result") if isinstance(resp.get("result"), dict) else None
    charts = result.pop("charts", None) if result else None
    if charts is None:
        return resp
    images, notes = [], []
    for c in charts:
        if c.get("png_base64"):
            images.append(ImageContent(type="image", data=c["png_base64"],
                                       mimeType=c.get("mime") or "image/png"))
        elif c.get("name") == "_debug":
            result["charts_debug"] = c.get("text")
        elif c.get("text"):
            notes.append(c["text"])
    result["charts_sent"] = len(images)
    if notes:
        result["charts_note"] = "; ".join(notes)
    if not images:
        result["charts_note"] = (result.get("charts_note") or
                                 "Grafik dosyasi bulunamadi; charts_debug alanini kullaniciya aynen goster")
        return resp
    text = TextContent(type="text", text=json.dumps(resp, ensure_ascii=False))
    return CallToolResult(content=[text, *images], structuredContent=resp)


# Every analysis tool also accepts filter_variable/filter_value to analyse one
# subgroup only (e.g. grup = 1 for the experimental group); the nonparametric
# tools accept exact=True for exact p-values (recommended when n is small).
# Every analysis tool returns: syntax (exact SPSS syntax that ran), spss_menu
# (where the same dialog lives in the SPSS GUI, English UI) and tables
# (every output table, flattened to cells with a row/column path).


@mcp.tool()
def run_descriptives(path: str, variables: list[str],
                     statistics: list[str] | None = None,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Betimsel istatistik (DESCRIPTIVES). Surekli/olcek degiskenler icin.

    statistics: MEAN, STDDEV, MIN, MAX, VARIANCE, RANGE, SUM, SEMEAN,
                SKEWNESS, KURTOSIS. Bos: MEAN STDDEV MIN MAX SKEWNESS KURTOSIS.
    """
    return analysis("descriptives", path, filter_variable=filter_variable, filter_value=filter_value, variables=variables, statistics=statistics)


@mcp.tool()
def run_frequencies(path: str, variables: list[str],
                    statistics: list[str] | None = None,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Frekans tablosu (FREQUENCIES). Kategorik degiskenler ve demografik bilgiler icin.

    statistics (istege bagli): MEAN, MEDIAN, MODE, STDDEV, VARIANCE, MINIMUM,
                MAXIMUM, RANGE, SKEWNESS, KURTOSIS, SEMEAN, SUM.
    """
    return analysis("frequencies", path, filter_variable=filter_variable, filter_value=filter_value, variables=variables, statistics=statistics)


@mcp.tool()
def run_normality(path: str, variables: list[str], group: str | None = None,
        charts: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Normallik testi (EXAMINE): Kolmogorov-Smirnov ve Shapiro-Wilk, carpiklik/basiklik.

    group verilirse her grup icin ayri test yapilir (t-testi/ANOVA oncesi bu kullanilmali).
    charts=True: grafikleri (boxplot, normal Q-Q) resim olarak da dondurur (en fazla 16).
    """
    return analysis("normality", path, charts=charts, filter_variable=filter_variable, filter_value=filter_value, variables=variables, group=group)


@mcp.tool()
def run_ttest_independent(path: str, variables: list[str], group: str,
                          group_values: list[str | float],
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Bagimsiz orneklem t-testi. Levene testi ve etki buyuklugu (Cohen's d) dahil.

    group: iki gruplu degisken; group_values: karsilastirilacak iki kod, or. [1, 2] veya ["f", "m"].
    """
    return analysis("ttest_independent", path, filter_variable=filter_variable, filter_value=filter_value, variables=variables,
                    group=group, group_values=group_values)


@mcp.tool()
def run_ttest_paired(path: str, pairs: list[list[str]],
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Bagimli (eslestirilmis) orneklem t-testi, etki buyuklugu dahil.

    pairs: [["on_test", "son_test"], ...]
    """
    return analysis("ttest_paired", path, filter_variable=filter_variable, filter_value=filter_value, pairs=pairs)


@mcp.tool()
def run_anova_oneway(path: str, variables: list[str], group: str,
                     posthoc: list[str] | None = None,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Tek yonlu ANOVA: betimsel, Levene, Welch, eta-kare ve post hoc.

    group: sayisal kodlu grup degiskeni. posthoc: TUKEY, GH (Games-Howell),
    BONFERRONI, SCHEFFE, LSD, T2, DUNNETT. Bos: TUKEY GH.
    """
    return analysis("anova_oneway", path, filter_variable=filter_variable, filter_value=filter_value, variables=variables, group=group, posthoc=posthoc)


@mcp.tool()
def run_correlation(path: str, variables: list[str], method: str = "pearson",
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Korelasyon matrisi. method: "pearson" (normal dagilim) veya "spearman" (siralama/normal degil)."""
    return analysis("correlation", path, filter_variable=filter_variable, filter_value=filter_value, variables=variables, method=method)


@mcp.tool()
def run_regression(path: str, dependent: str, blocks: list[list[str]],
        method: str = "enter",
        charts: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Coklu dogrusal regresyon (REGRESSION).

    dependent: bagimli (yordanan) surekli degisken.
    blocks: yordayicilar, blok blok. Tek blok: [["x1", "x2"]]. Hiyerarsik
    regresyon: [["yas", "cinsiyet"], ["x1", "x2"]] (her blok R^2 degisimiyle).
    method: "enter" (varsayilan, tezlerde onerilen) veya "stepwise".
    Yordayicilar sayisal olmali; kategorik degiskenler icin kukla degisken gerekir.
    Cikti: model ozeti (R, R^2, duzeltilmis R^2, R^2 degisimi, Durbin-Watson),
    ANOVA, katsayilar (B, beta, t, p, %95 GA, kismi/yari kismi r, tolerans, VIF),
    artik istatistikleri.
    charts=True: grafikleri (artik-tahmin sacilimi, normal P-P) resim olarak da dondurur (en fazla 16).
    """
    return analysis("regression", path, charts=charts, filter_variable=filter_variable, filter_value=filter_value,
                    dependent=dependent, blocks=blocks, method=method)


@mcp.tool()
def run_anova_factorial(path: str, dependent: str, factors: list[str],
        charts: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Iki (ya da uc) yonlu bagimsiz gruplar ANOVA (UNIANOVA, tam faktoriyel).

    dependent: surekli bagimli degisken. factors: 2-3 gruplama degiskeni
    (or. ["cinsiyet", "egitim"]). Cikti: Levene, ana etkiler ve etkilesim
    (kismi eta kare), Tukey/Games-Howell post hoc istegi (3+ duzeyli faktorlerde;
    SPSS bazi desenlerde, or. bos hucre varsa, post hoc'u atlar: uyari tablolarini
    oku ve atlandiysa soyle), etkilesim icin Bonferroni'li basit etkiler.
    Once etkilesime bak. Bos hucre (bir grup kombinasyonunda hic kisi yok) varsa
    etkilesim sd'si duser; bunu kullaniciya soyle.
    charts=True: grafikleri (profil grafigi) resim olarak da dondurur (en fazla 16).
    """
    return analysis("anova_factorial", path, charts=charts, filter_variable=filter_variable, filter_value=filter_value,
                    dependent=dependent, factors=factors)


@mcp.tool()
def run_ancova(path: str, dependent: str, factors: list[str], covariates: list[str],
        charts: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Kovaryans analizi (ANCOVA, UNIANOVA ... WITH).

    dependent: surekli bagimli (or. son test). factors: 1-2 gruplama degiskeni
    (or. ["grup"]). covariates: kontrol edilen surekli degisken(ler) (or. ["ontest"]).
    Iki UNIANOVA calisir: (1) egim homojenligi kontrolu; Tests of Between-Subjects
    Effects tablosunda "faktor * kovaryat" satiri anlamsiz (p > ,05) olmali, anlamliysa
    ANCOVA varsayimi bozulur, bunu soyle. (2) asil ANCOVA: Levene, kovaryat ve faktor
    etkileri (kismi eta kare), duzeltilmis ortalamalar (Estimated Marginal Means,
    kovaryat ortalamasinda) ve Bonferroni'li ikili karsilastirmalar.
    Raporda ham ortalamalari degil duzeltilmis ortalamalari kullan.
    Ilk kovaryat icin gruplara gore sacilim grafigi, her grubun regresyon cizgisiyle
    cizilir (cizgiler paralelse egimler homojen).
    charts=True: profil grafigi (duzeltilmis ortalamalar) ve sacilim grafigini resim
    olarak da dondurur.
    """
    return analysis("ancova", path, charts=charts, filter_variable=filter_variable, filter_value=filter_value,
                    dependent=dependent, factors=factors, covariates=covariates)


@mcp.tool()
def run_manova(path: str, dependents: list[str], factors: list[str],
        covariates: list[str] | None = None,
        charts: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Cok degiskenli varyans analizi (MANOVA; kovaryat verilirse MANCOVA).

    dependents: 2+ iliskili surekli bagimli (or. olcegin alt boyutlari).
    factors: 1-2 gruplama degiskeni. covariates: istege bagli.
    Cikti: Box's M (kovaryans matrislerinin esitligi; p < ,001 ise bozuk sayilir,
    o zaman Pillai's Trace raporla), Multivariate Tests (Wilks' Lambda / Pillai,
    kismi eta kare), her bagimli icin Levene ve Tests of Between-Subjects Effects
    (tek degiskenli izleme testleri; Bonferroni: ,05 / bagimli sayisi), post hoc
    (kovaryat yoksa Tukey/Games-Howell) ve Bonferroni'li ikili karsilastirmalar.
    Once cok degiskenli testa bak; anlamli degilse tek degiskenli testleri yorumlama.
    charts=True: profil grafiklerini resim olarak da dondurur (en fazla 16).
    """
    return analysis("manova", path, charts=charts, filter_variable=filter_variable, filter_value=filter_value,
                    dependents=dependents, factors=factors, covariates=covariates)


@mcp.tool()
def run_logistic(path: str, dependent: str, predictors: list[str],
        categorical: list[str] | None = None, reference: str = "first",
        method: str = "enter",
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Ikili (binary) lojistik regresyon.

    dependent: iki kategorili sonuc (or. gecti/kaldi). predictors: tum yordayicilar.
    categorical: predictors icindeki kategorik olanlar (metin degiskenler burada
    olmali); reference: kategoriklerde referans grup "first" ya da "last".
    method: "enter" (onerilen), "forward" ya da "backward" (LR).
    Cikti: Omnibus testi, Nagelkerke R^2, Hosmer-Lemeshow, siniflandirma tablosu,
    B, Wald, p, Exp(B) (odds orani) ve %95 GA. Bagimli degiskenin kodlamasini
    'Dependent Variable Encoding' tablosundan kontrol et. Buyuk olcekli
    yordayicilarda (or. maas) Exp(B) 1,000 gorunebilir; bunu soyle ve
    kullaniciya olcegi bolerek (or. bin TL) yeni degisken olusturmasini oner.
    """
    return analysis("logistic", path, filter_variable=filter_variable, filter_value=filter_value,
                    dependent=dependent, predictors=predictors, categorical=categorical,
                    reference=reference, method=method)


@mcp.tool()
def run_factor(path: str, variables: list[str], extraction: str = "pc",
        rotation: str = "varimax", n_factors: int | None = None,
        charts: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Aciklayici faktor analizi (FACTOR).

    variables: olcek maddeleri (en az 3). extraction: "pc" (temel bilesenler),
    "paf" (temel eksen) ya da "ml". rotation: "varimax", "promax", "oblimin"
    ya da "none". n_factors verilmezse oz deger > 1 olan faktorler alinir.
    Cikti: KMO ve Bartlett, ortak varyanslar, aciklanan varyans, dondurulmus
    yuk matrisi (,30 alti gizli). Scree grafigi doner gelmez; kullaniciya
    SPSS'te bakmasini soyle.
    charts=True: grafikleri (scree) resim olarak da dondurur (en fazla 16).
    """
    return analysis("factor", path, charts=charts, filter_variable=filter_variable, filter_value=filter_value,
                    variables=variables, extraction=extraction, rotation=rotation,
                    n_factors=n_factors)


@mcp.tool()
def run_crosstabs(path: str, row: str, column: str,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Capraz tablo ve ki-kare testi (Phi/Cramer's V ve beklenen frekanslar dahil)."""
    return analysis("crosstabs", path, filter_variable=filter_variable, filter_value=filter_value, row=row, column=column)


@mcp.tool()
def run_mann_whitney(path: str, variables: list[str], group: str,
                     group_values: list[str | float],
        exact: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Mann-Whitney U: normal dagilmayan veride bagimsiz t-testinin alternatifi."""
    return analysis("mann_whitney", path, filter_variable=filter_variable, filter_value=filter_value, exact=exact, variables=variables,
                    group=group, group_values=group_values)


@mcp.tool()
def run_kruskal_wallis(path: str, variables: list[str], group: str,
                       group_range: list[float] | None = None,
        exact: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Kruskal-Wallis H: normal dagilmayan veride tek yonlu ANOVA'nin alternatifi.

    group_range: sayisal grup kodlarinin en kucugu ve en buyugu, or. [1, 4].
    Metin tipindeki grup degiskenlerinde gerekmez (otomatik kodlanir).
    """
    return analysis("kruskal_wallis", path, filter_variable=filter_variable, filter_value=filter_value, exact=exact, variables=variables,
                    group=group, group_range=group_range)


@mcp.tool()
def run_wilcoxon(path: str, pairs: list[list[str]],
        exact: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Wilcoxon isaretli siralar: normal dagilmayan veride bagimli t-testinin alternatifi."""
    return analysis("wilcoxon", path, filter_variable=filter_variable, filter_value=filter_value, exact=exact, pairs=pairs)


@mcp.tool()
def run_friedman(path: str, variables: list[str], exact: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Friedman testi + Kendall's W: ayni kisilerin 3+ olcumu (or. on test, son test, izleme).

    Tekrarli olcumler ANOVA'nin parametrik olmayan karsiligidir. Anlamliysa
    ikili karsilastirmalar run_wilcoxon ile yapilir (Bonferroni: alfa / karsilastirma sayisi).
    """
    return analysis("friedman", path, filter_variable=filter_variable, filter_value=filter_value,
                    variables=variables, exact=exact)


@mcp.tool()
def run_rm_anova(path: str, variables: list[str], group: str | None = None,
        factor_name: str = "zaman",
        charts: bool = False,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Tekrarli olcumler ANOVA (GLM). variables: ayni kisilerin olcumleri, sirayla
    (or. ["CatOnTop", "CatSonTop", "CatIzlTop"]).

    group verilirse karisik desen (zaman x grup) yapilir: Box M, Mauchly kuresellik,
    Levene, kismi eta-kare, Bonferroni'li ikili karsilastirmalar ve basit etkiler dahil.
    Kuresellik bozuksa Greenhouse-Geisser satiri raporlanmalidir.
    Advanced Statistics modulu gerekir.
    charts=True: grafikleri (profil grafigi) resim olarak da dondurur (en fazla 16).
    """
    return analysis("rm_anova", path, charts=charts, filter_variable=filter_variable, filter_value=filter_value,
                    variables=variables, group=group, factor_name=factor_name)


@mcp.tool()
def run_reliability(path: str, variables: list[str], scale_name: str | None = None,
        reverse_items: list[str] | None = None,
        scale_min: float | None = None, scale_max: float | None = None,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Guvenirlik analizi (Cronbach alfa). variables: olcegin MADDE degiskenleri.

    Madde-toplam korelasyonlari ve 'madde silinirse alfa' tablosu dahildir.
    reverse_items: ters puanlanacak maddeler (variables icinden); scale_min ve
    scale_max ile birlikte verilir (or. 1-4 olcek icin 1 ve 4). Ters maddeler
    yeni degiskenlere (noema_r_MADDE = min+max - MADDE) cevrilir; orijinal
    maddeler ve .sav degismez. Maddeler veride ZATEN cevrilmis olabilir: emin
    degilsen kullaniciya sor, iki kez cevirme.
    """
    return analysis("reliability", path, filter_variable=filter_variable, filter_value=filter_value,
                    variables=variables, scale_name=scale_name, reverse_items=reverse_items,
                    scale_min=scale_min, scale_max=scale_max)


@mcp.tool()
def run_scale_score(path: str, variables: list[str], method: str = "sum",
        score_name: str | None = None,
        reverse_items: list[str] | None = None,
        scale_min: float | None = None, scale_max: float | None = None,
        filter_variable: str | None = None,
        filter_value: str | float | None = None) -> dict:
    """Maddelerden olcek puani hesaplar (COMPUTE) ve betimsel istatistigini verir.

    method: 'sum' (toplam) ya da 'mean' (ortalama); bir maddesi bos olan kisiye
    puan verilmez. reverse_items/scale_min/scale_max run_reliability ile ayni.
    Puan yalnizca bu calismada vardir, .sav dosyasina kaydedilmez; diger
    analizlerde kullanmak icin kullanici syntax'i SPSS'te calistirip kendisi
    kaydetmelidir.
    """
    return analysis("scale_score", path, filter_variable=filter_variable, filter_value=filter_value,
                    variables=variables, method=method, score_name=score_name,
                    reverse_items=reverse_items, scale_min=scale_min, scale_max=scale_max)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
