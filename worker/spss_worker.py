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

def _fix_locale():
    for name in ("Turkish_Turkey.1254", "English_United States.1252",
                 "en_US.UTF-8", "C"):
        try:
            locale.setlocale(locale.LC_ALL, name)
            locale.getlocale()  # SPSS calls this while starting
            return name
        except (locale.Error, ValueError):
            continue
    return None


FIXED_LOCALE = _fix_locale()

import spss  # noqa: E402  (must come after the locale fix)

_spss_mod = sys.modules["spss.spss"]
_orig_get_c_locale = _spss_mod.PyInvokeSpss.GetCLocale


def _safe_get_c_locale():
    try:
        return _orig_get_c_locale()
    except UnicodeDecodeError:
        return (FIXED_LOCALE or "C",)


_spss_mod.PyInvokeSpss.GetCLocale = _safe_get_c_locale


# --- Helpers -----------------------------------------------------------------

OMS_NS = "{http://www.ibm.com/software/analytics/spss/xml/oms}"


def q(path):
    """Quote a value for SPSS syntax (single quotes doubled)."""
    return "'" + str(path).replace("'", "''") + "'"


def open_dataset(path):
    if not os.path.isfile(path):
        raise ValueError("Dosya bulunamadi: %s" % path)
    return "GET FILE=%s.\nDATASET NAME noema WINDOW=FRONT." % q(path)


def run_syntax_capture(syntax):
    """Run syntax with OMS capturing every table as OXML; return (syntax, tables)."""
    fd, xml_path = tempfile.mkstemp(suffix=".xml", prefix="noema_")
    os.close(fd)
    full = "\n".join([
        "SET OLANG=ENGLISH.",
        "OMS /SELECT TABLES /DESTINATION FORMAT=OXML OUTFILE=%s /TAG='noema'." % q(xml_path),
        syntax,
        "OMSEND TAG=['noema'].",
    ])
    try:
        spss.Submit(full)
        tables = parse_oxml(xml_path)
    finally:
        try:
            os.remove(xml_path)
        except OSError:
            pass
    return syntax, tables


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
        elif tag in ("dimension", "group"):
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


VALID_STATS = {"MEAN", "STDDEV", "MIN", "MAX", "VARIANCE", "RANGE", "SUM",
               "SEMEAN", "KURTOSIS", "SKEWNESS"}


def action_descriptives(req):
    path = req["path"]
    variables = req["variables"]
    stats = [s.upper() for s in req.get("statistics") or
             ["MEAN", "STDDEV", "MIN", "MAX", "SKEWNESS", "KURTOSIS"]]
    bad = [s for s in stats if s not in VALID_STATS]
    if bad:
        raise ValueError("Gecersiz istatistik: %s" % ", ".join(bad))
    if not variables:
        raise ValueError("En az bir degisken gerekli")
    for name in variables:
        if not name.replace("_", "").replace(".", "").replace("@", "").replace("#", "").replace("$", "").isalnum():
            raise ValueError("Gecersiz degisken adi: %s" % name)
    spss.Submit(open_dataset(path))
    syntax = "DESCRIPTIVES VARIABLES=%s\n  /STATISTICS=%s." % (
        " ".join(variables), " ".join(stats))
    syntax, tables = run_syntax_capture(syntax)
    return {"path": path, "syntax": syntax, "tables": tables}


ACTIONS = {
    "ping": action_ping,
    "inspect": action_inspect,
    "descriptives": action_descriptives,
}


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--test":
        # Manual check: spss_worker.py --test [file.sav]
        req = {"action": "inspect", "path": sys.argv[2]} if len(sys.argv) > 2 else {"action": "ping"}
        out = {"ok": True, "result": ACTIONS[req["action"]](req)}
        print("\n=== NOEMA ===")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        spss.StopSPSS()
        return
    req_path, resp_path = sys.argv[1], sys.argv[2]
    with open(req_path, encoding="utf-8") as f:
        req = json.load(f)
    try:
        result = {"ok": True, "result": ACTIONS[req["action"]](req)}
    except spss.SpssError as e:
        result = {"ok": False, "error": "SPSS hatasi: %s" % e,
                  "spss_last_error": _last_error()}
    except Exception as e:  # noqa: BLE001
        result = {"ok": False, "error": "%s: %s" % (type(e).__name__, e),
                  "traceback": traceback.format_exc()}
    with open(resp_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
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
