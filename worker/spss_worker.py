"""Noema SPSS worker.

Runs on the Python that ships with IBM SPSS Statistics (3.8 on SPSS 27).
Kept compatible with Python 3.8: no match statements, no `X | Y` types.

Usage:
    <spss python> spss_worker.py <request.json> <response.json>

The request is {"action": "...", ...}. The response is written to the
response file, because SPSS itself prints tables to stdout.
"""
import json
import locale
import os
import sys
import tempfile
import traceback
import xml.etree.ElementTree as ET


# --- Locale fix --------------------------------------------------------------
# Windows 11 reports "Turkish_Türkiye.1254". SPSS 27 decodes that name as UTF-8
# and crashes on "ü" (0xfc). We pin a locale Python can both set and parse,
# then make SPSS's locale lookup fall back to it.

LOCALE_CANDIDATES = ("Turkish_Turkey.1254", "English_United States.1252",
                     "en_US.UTF-8", "C")


def _fix_locale():
    for name in LOCALE_CANDIDATES:
        try:
            locale.setlocale(locale.LC_ALL, name)
            locale.getlocale()  # SPSS calls this while starting
            return name
        except (locale.Error, ValueError):
            continue
    return None


FIXED_LOCALE = _fix_locale()

# SPSS echoes syntax and tables to stdout (worker.log). With a cp1252 console
# a Turkish letter such as "I-dot" raised UnicodeEncodeError there, so never
# let printing fail.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

import spss  # noqa: E402  (must come after the locale fix)
import analyses  # noqa: E402

_spss_mod = sys.modules["spss.spss"]
_orig_get_c_locale = _spss_mod.PyInvokeSpss.GetCLocale


def _safe_get_c_locale():
    try:
        return _orig_get_c_locale()
    except UnicodeDecodeError:
        return (FIXED_LOCALE or "C",)


_spss_mod.PyInvokeSpss.GetCLocale = _safe_get_c_locale

def spss_path(path):
    """Path safe to put into syntax. SPSS 27 encodes syntax with the 1252 code
    page, which has no "I-dot", "s-cedilla" or "g-breve", so on Windows a
    non-ASCII path is replaced by its 8.3 short name (the file is untouched)."""
    if os.name != "nt":
        return path
    try:
        path.encode("ascii")
        return path
    except UnicodeEncodeError:
        pass
    import ctypes
    buf = ctypes.create_unicode_buffer(1024)
    n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024)
    if n and buf.value:
        return buf.value
    raise ValueError("Dosya yolunda Turkce karakter var ve SPSS bu yolu acamiyor. "
                     "Dosyayi adinda Turkce karakter olmayan bir klasore kopyalayin.")


# --- Helpers -----------------------------------------------------------------

OMS_NS = "{http://www.ibm.com/software/analytics/spss/xml/oms}"


def q(path):
    """Quote a value for SPSS syntax (single quotes doubled)."""
    return "'" + str(path).replace("'", "''") + "'"


def open_dataset(path):
    if not os.path.isfile(path):
        raise ValueError("Dosya bulunamadi: %s" % path)
    return "GET FILE=%s.\nDATASET NAME noema WINDOW=FRONT." % q(spss_path(path))


MAX_CHARTS = 16


def run_syntax_capture(syntax, charts=False):
    """Run syntax with OMS capturing every table as OXML.

    With charts=True a second OMS writes every chart as PNG (via an HTML
    destination, which puts the images next to the HTML file). Returns
    (syntax, tables, charts) where charts is a list of
    {"name": ..., "png_base64": ...}, at most MAX_CHARTS.
    """
    import base64
    import shutil
    fd, xml_path = tempfile.mkstemp(suffix=".xml", prefix="noema_")
    os.close(fd)
    chart_dir = tempfile.mkdtemp(prefix="noema_charts_") if charts else None
    import time as _time
    t_start = _time.time()
    chart_error = None
    images = []
    try:
        spss.Submit("SET OLANG=ENGLISH.\n"
                    "OMS /SELECT TABLES WARNINGS /DESTINATION FORMAT=OXML OUTFILE=%s /TAG='noema'."
                    % q(xml_path))
        chart_oms = False
        if charts:
            # Separate Submit: if SPSS rejects the chart destination, the
            # analysis still runs and we report why there are no charts.
            try:
                spss.Submit("OMS /SELECT CHARTS /DESTINATION FORMAT=HTML OUTFILE=%s "
                            "IMAGES=YES IMAGEFORMAT=PNG CHARTSIZE=70 IMAGEROOT='noema' "
                            "/TAG='noema_ch'." % q(os.path.join(chart_dir, "charts.htm")))
                chart_oms = True
            except Exception as e:  # noqa: BLE001
                chart_error = "%s %s" % (e, _last_error())
        try:
            spss.Submit(syntax)
        finally:
            spss.Submit("OMSEND TAG=['noema'%s]." % (" 'noema_ch'" if chart_oms else ""))
        tables = parse_oxml(xml_path)
        if charts:
            import re
            files, seen, stray, embedded = [], set(), [], []
            for root, _, names in os.walk(chart_dir):
                for n in names:
                    if n.lower().endswith(".png"):
                        full = os.path.join(root, n)
                        seen.add(os.path.normcase(os.path.abspath(full)))
                        files.append((os.path.getmtime(full), n, full))
            # Also follow <img src> in the HTML, in case SPSS wrote elsewhere.
            html = os.path.join(chart_dir, "charts.htm")
            srcs = []
            if os.path.isfile(html):
                with open(html, "rb") as f:
                    text = f.read().decode("utf-8", "replace")
                srcs = re.findall(r'src="([^"]+)"', text, flags=re.I)
                # SPSS 27 embeds the charts in the HTML as data URIs.
                for i, src in enumerate(srcs):
                    # SPSS 27 writes JPEG here even with IMAGEFORMAT=PNG.
                    m = re.match(r"data:image/([a-z]+);base64,(.*)$", src.strip(), flags=re.I | re.S)
                    if m:
                        kind = m.group(1).lower()
                        mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg"}.get(kind, "image/" + kind)
                        embedded.append({"name": "chart%02d.%s" % (i + 1, kind), "mime": mime,
                                         "png_base64": re.sub(r"\s+", "", m.group(2))})
                for src in srcs:
                    if src.startswith("data:"):
                        continue
                    full = src if os.path.isabs(src) else os.path.join(chart_dir, src)
                    key = os.path.normcase(os.path.abspath(full))
                    if full.lower().endswith(".png") and os.path.isfile(full) and key not in seen:
                        seen.add(key)
                        files.append((os.path.getmtime(full), os.path.basename(full), full))
            for d in {os.getcwd(), tempfile.gettempdir()}:
                try:
                    names = os.listdir(d)
                except OSError:
                    continue
                for n in names:
                    full = os.path.join(d, n)
                    key = os.path.normcase(os.path.abspath(full))
                    if (n.lower().startswith("noema") and n.lower().endswith(".png")
                            and key not in seen and os.path.getmtime(full) >= t_start - 1):
                        seen.add(key)
                        files.append((os.path.getmtime(full), n, full))
                        stray.append(full)
            if not files and not embedded:
                listing = []
                for root, _, names in os.walk(chart_dir):
                    listing += [os.path.relpath(os.path.join(root, n), chart_dir) for n in names]
                images.append({"name": "_debug", "text": json.dumps({
                    "files": listing,
                    "html_size": os.path.getsize(html) if os.path.isfile(html) else None,
                    "img_src": [x[:80] for x in srcs[:10]],
                    "cwd": os.getcwd(),
                    "chart_oms_error": chart_error,
                    "last_error": _last_error()}, ensure_ascii=False)})
            found = list(embedded)
            for _, n, full in sorted(files):
                with open(full, "rb") as f:
                    found.append({"name": n,
                                  "png_base64": base64.b64encode(f.read()).decode("ascii")})
            images.extend(found[:MAX_CHARTS])
            if len(found) > MAX_CHARTS:
                images.append({"name": "_note", "text": "%d grafikten ilk %d tanesi gonderildi"
                               % (len(found), MAX_CHARTS)})
            for f in stray:  # PNGs SPSS left outside chart_dir
                try:
                    os.remove(f)
                except OSError:
                    pass
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass
        if chart_dir:
            shutil.rmtree(chart_dir, ignore_errors=True)
    return syntax, tables, images


def _label(el):
    return el.get("text") or el.get("varName") or el.get("label") or ""


def _walk(el, path, cells):
    for child in el:
        tag = child.tag.replace(OMS_NS, "")
        if tag == "cell":
            value = child.get("number")
            try:
                value = float(value) if value is not None else child.get("text")
            except ValueError:
                value = child.get("text")
            cells.append({"path": list(path), "value": value,
                          "text": child.get("text")})
        elif tag == "category":
            _walk(child, path + [_label(child)], cells)
        elif tag == "group":
            # Nested column headers (e.g. "minority = Yes" over Observed and
            # Expected) live on groups; keep them so cells stay distinguishable.
            label = _label(child)
            _walk(child, path + [label] if label else path, cells)
        elif tag == "dimension":
            _walk(child, path, cells)


def parse_oxml(xml_path):
    """Flatten every pivot table into {title, subtype, command, cells, notes}."""
    if not os.path.getsize(xml_path):
        return []
    root = ET.parse(xml_path).getroot()
    tables = []
    for command in root.iter(OMS_NS + "command"):
        cmd = command.get("command") or command.get("text")
        for pt in command.iter(OMS_NS + "pivotTable"):
            cells = []
            _walk(pt, [], cells)
            notes = [n.text for n in pt.iter(OMS_NS + "note") if n.text]
            footnotes = [f.get("text") for f in pt.iter(OMS_NS + "footnote")
                         if f.get("text")]
            tables.append({
                "command": cmd,
                "title": pt.get("text"),
                "subtype": pt.get("subType"),
                "cells": cells,
                "notes": notes + footnotes,
            })
    return tables


# --- Actions -----------------------------------------------------------------

def action_ping(req):
    spss.Submit("SHOW N.")
    return {"ok": True, "locale": FIXED_LOCALE, "python": sys.version}


def action_inspect(req):
    path = req["path"]
    spss.Submit(open_dataset(path))
    variables = []
    spss.StartDataStep()
    try:
        ds = spss.Dataset()
        for v in ds.varlist:
            mv = v.missingValues  # (type, v1, v2, v3)
            variables.append({
                "name": v.name,
                "label": v.label,
                "type": "numeric" if v.type == 0 else "string(%d)" % v.type,
                "measurement": v.measurementLevel,
                "format": v.format,
                "value_labels": {_key(k): lab for k, lab in v.valueLabels.data.items()},
                "missing": describe_missing(mv),
            })
    finally:
        spss.EndDataStep()
    n_cases = spss.GetCaseCount()
    return {"path": path, "n_cases": n_cases, "n_variables": len(variables),
            "variables": variables}


def _key(k):
    if isinstance(k, float) and k.is_integer():
        return str(int(k))
    return str(k).strip()


def describe_missing(mv):
    if not mv or mv[0] == 0:
        return None
    kind = mv[0]
    vals = [x for x in mv[1:] if x is not None]
    if kind > 0:
        return {"discrete": vals}
    if kind == -2:
        return {"range": vals[:2]}
    if kind == -3:
        return {"range": vals[:2], "discrete": vals[2:]}
    return {"raw": list(mv)}


def variable_info(name, distinct=False):
    """Look up a variable in the active dataset (call after GET FILE)."""
    for i in range(spss.GetVariableCount()):
        if spss.GetVariableName(i).lower() == name.lower():
            info = {"index": i, "is_string": spss.GetVariableType(i) > 0}
            if distinct:
                cur = spss.Cursor([i])
                try:
                    vals = set(str(r[0]).strip() for r in cur.fetchall()
                               if r[0] is not None and str(r[0]).strip())
                finally:
                    cur.close()
                info["n_distinct"] = len(vals)
            return info
    raise ValueError("Degisken bulunamadi: %s" % name)


def action_analysis(req):
    kind = req["kind"]
    if kind not in analyses.BUILDERS:
        raise ValueError("Bilinmeyen analiz: %s" % kind)
    path = req["path"]
    spss.Submit(open_dataset(path))
    syntax = analyses.BUILDERS[kind](req, variable_info)
    pre, post, cond = analyses.filter_syntax(req.get("filter"), variable_info)
    syntax = pre + syntax + ("\n" + post if post else "")
    # Fail early with a clear message if a variable does not exist.
    for key in ("variables", "group", "row", "column", "reverse_items", "dependent",
                "factors", "predictors", "categorical", "covariates", "dependents"):
        vals = req.get(key)
        for v in ([vals] if isinstance(vals, str) else (vals or [])):
            variable_info(v)
    for pair in req.get("pairs") or []:
        for v in pair:
            variable_info(v)
    syntax, tables, charts = run_syntax_capture(syntax, charts=bool(req.get("charts")))
    menu = analyses.rm_anova_menu(req) if kind == "rm_anova" else analyses.MENU.get(kind)
    if kind == "scale_score":
        items, _, fmt = analyses.scale_score_expr(req)
        rev = set(r.lower() for r in (req.get("reverse_items") or []))
        used = [analyses.REVERSE_PREFIX + i if i.lower() in rev else i for i in items]
        menu = menu % {"name": req.get("score_name") or "noema_puan",
                       "expr": fmt % ", ".join(used)}
    if req.get("reverse_items"):
        menu = (analyses.REVERSE_MENU % analyses.reverse_total(req)) + " ; sonra " + menu
    if cond:
        menu = (analyses.FILTER_MENU % cond) + " ; sonra " + menu
    if req.get("exact"):
        menu += analyses.EXACT_NOTE
    out = {"path": path, "analysis": kind, "filter": cond, "syntax": syntax,
           "spss_menu": menu, "tables": tables}
    if req.get("charts"):
        out["charts"] = charts
    return out


def action_descriptives(req):
    req = dict(req, kind="descriptives")
    return action_analysis(req)


ACTIONS = {
    "ping": action_ping,
    "inspect": action_inspect,
    "descriptives": action_descriptives,
    "analysis": action_analysis,
}


def handle(req):
    try:
        return {"ok": True, "result": ACTIONS[req["action"]](req)}
    except spss.SpssError as e:
        return {"ok": False, "error": "SPSS hatasi: %s" % e,
                "spss_last_error": _last_error()}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                "traceback": traceback.format_exc()}


def _safe_temp_path(path):
    """Return path only if it lies inside a noema_* folder in the temp dir.

    The MCP server creates these files with tempfile.mkdtemp(prefix="noema_"),
    so anything else on the command line is rejected (path traversal guard).
    """
    base = os.path.normcase(os.path.realpath(tempfile.gettempdir()))
    full = os.path.realpath(path)
    parent = os.path.dirname(full)
    if (os.path.normcase(os.path.dirname(parent)) != base
            or not os.path.basename(parent).startswith("noema_")
            or not os.path.normcase(full).startswith(base + os.sep)):
        raise SystemExit("Gecersiz gecici dosya yolu: %s" % path)
    return full


def serve(port_file):
    """Keep the SPSS engine warm and answer requests over a localhost socket.

    Protocol: one JSON object per line in each direction. Every request must
    carry the token from NOEMA_TOKEN. The worker exits when the MCP server
    disconnects (so it never outlives Claude) or after NOEMA_IDLE_SECONDS
    without a request.
    """
    import socket
    token = os.environ.get("NOEMA_TOKEN", "")
    idle = float(os.environ.get("NOEMA_IDLE_SECONDS", "1800"))
    if not token:
        raise SystemExit("NOEMA_TOKEN gerekli")
    port_file = _safe_temp_path(port_file)
    spss.Submit("SHOW N.")  # start the engine before announcing the port
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    srv.settimeout(120)  # the server should connect right away
    tmp = port_file + ".tmp"
    with open(tmp, "w") as f:
        f.write(str(srv.getsockname()[1]))
    os.replace(tmp, port_file)
    try:
        conn, _ = srv.accept()
    except socket.timeout:
        return
    srv.close()
    conn.settimeout(idle)
    stream = conn.makefile("rwb")
    try:
        while True:
            try:
                line = stream.readline()
            except socket.timeout:
                break  # idle too long
            if not line:
                break  # MCP server went away
            try:
                req = json.loads(line.decode("utf-8"))
            except ValueError:
                resp = {"ok": False, "error": "Gecersiz istek"}
            else:
                if req.get("token") != token:
                    resp = {"ok": False, "error": "Yetkisiz istek"}
                elif req.get("action") == "shutdown":
                    stream.write(b'{"ok": true}\n')
                    stream.flush()
                    break
                else:
                    resp = handle(req)
            stream.write((json.dumps(resp, ensure_ascii=False) + "\n").encode("utf-8"))
            stream.flush()
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        # Manual check: spss_worker.py --test [file.sav]
        req = {"action": "inspect", "path": sys.argv[2]} if len(sys.argv) > 2 else {"action": "ping"}
        out = {"ok": True, "result": ACTIONS[req["action"]](req)}
        print("\n=== NOEMA ===")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        spss.StopSPSS()
        return
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "--serve":
            serve(sys.argv[2])
        else:
            raise SystemExit("Kullanim: spss_worker.py --serve PORT_DOSYASI | --test [dosya.sav]")
    finally:
        try:
            spss.StopSPSS()
        except Exception:  # noqa: BLE001
            pass


def _last_error():
    try:
        return spss.GetLastErrorMessage()
    except Exception:  # noqa: BLE001
        return None


if __name__ == "__main__":
    main()
