"""Syntax builders for the analyses Noema supports.

Runs inside SPSS's bundled Python (3.8): keep it 3.8-compatible.
Each builder takes the request dict and a `var_info` helper and returns
SPSS syntax. Builders never see raw user syntax; every name is validated.
"""

MENU = {
    "frequencies": "Analyze > Descriptive Statistics > Frequencies",
    "descriptives": "Analyze > Descriptive Statistics > Descriptives (Options: istatistikleri secin)",
    "normality": "Analyze > Descriptive Statistics > Explore > Plots > 'Normality plots with tests'",
    "ttest_independent": "Analyze > Compare Means > Independent-Samples T Test > Define Groups",
    "ttest_paired": "Analyze > Compare Means > Paired-Samples T Test",
    "anova_oneway": "Analyze > Compare Means > One-Way ANOVA (Options: Descriptive, Homogeneity of variance, Welch; Post Hoc: Tukey, Games-Howell)",
    "correlation": "Analyze > Correlate > Bivariate (Pearson veya Spearman)",
    "crosstabs": "Analyze > Descriptive Statistics > Crosstabs (Statistics: Chi-square, Phi and Cramer's V; Cells: Observed, Expected, Row, Column)",
    "mann_whitney": "Analyze > Nonparametric Tests > Legacy Dialogs > 2 Independent Samples (Mann-Whitney U)",
    "kruskal_wallis": "Analyze > Nonparametric Tests > Legacy Dialogs > K Independent Samples (Kruskal-Wallis H)",
    "wilcoxon": "Analyze > Nonparametric Tests > Legacy Dialogs > 2 Related Samples (Wilcoxon)",
    "friedman": "Analyze > Nonparametric Tests > Legacy Dialogs > K Related Samples (Friedman, Kendall's W)",
    "rm_anova": "Analyze > General Linear Model > Repeated Measures (Within-Subject Factor Name: %(factor)s, Number of Levels: %(k)d > Add > Define; olcumleri sirayla atayin%(between)s; Options/EM Means: Descriptive statistics, Estimates of effect size%(homog)s, Compare main effects > Bonferroni)",
    "reliability": "Analyze > Scale > Reliability Analysis (Model: Alpha; Statistics: Item, Scale, Scale if item deleted)",
    "scale_score": "Transform > Compute Variable (Target Variable: %(name)s; Numeric Expression: %(expr)s) ; sonra Analyze > Descriptive Statistics > Descriptives",
}

REVERSE_MENU = ("Once her ters madde icin: Transform > Compute Variable "
                "(Target Variable: noema_r_MADDE; Numeric Expression: %s - MADDE)")

REVERSE_PREFIX = "noema_r_"

FILTER_MENU = "Once: Data > Select Cases > If condition is satisfied > %s"

EXACT_NOTE = " (Exact... dugmesi > Exact)"


def filter_syntax(flt, info):
    """Analyse only the cases where variable == value, like Data > Select
    Cases > "Filter out unselected cases". FILTER (not SELECT IF) so that the
    logged syntax never deletes cases when the user reruns it in SPSS.
    Returns (before, after, condition)."""
    if not flt:
        return "", "", None
    var = check_name(flt.get("variable"))
    is_str = info(var)["is_string"]
    cond = "%s = %s" % (var, literal(flt.get("value"), is_str))
    before = ("* Noema: yalnizca %s olan vakalar analiz edilir (vakalar silinmez).\n"
              "COMPUTE noema_filt = (%s).\nFILTER BY noema_filt.\nEXECUTE.\n" % (cond, cond))
    return before, "FILTER OFF.\nUSE ALL.\n", cond


def _exact(req):
    return "\n  /METHOD=EXACT TIMER(5)" if req.get("exact") else ""


def check_name(name):
    name = str(name).strip()
    stripped = name
    for ch in "_.@#$":
        stripped = stripped.replace(ch, "")
    if not name or not stripped.isalnum() or name[0].isdigit():
        raise ValueError("Gecersiz degisken adi: %r" % name)
    return name


def names(values, minimum=1, label="degisken"):
    if isinstance(values, str):
        values = [values]
    out = [check_name(v) for v in (values or [])]
    if len(out) < minimum:
        raise ValueError("En az %d %s gerekli" % (minimum, label))
    return out


def literal(value, is_string):
    """Group value as SPSS literal: quoted for string variables."""
    if is_string:
        return "'" + str(value).replace("'", "''") + "'"
    try:
        num = float(value)
    except (TypeError, ValueError):
        raise ValueError("Sayisal degisken icin sayisal grup degeri gerekli: %r" % (value,))
    return str(int(num)) if num.is_integer() else repr(num)


# --- Builders ----------------------------------------------------------------

DESC_STATS = {"MEAN", "STDDEV", "MIN", "MAX", "VARIANCE", "RANGE", "SUM",
              "SEMEAN", "KURTOSIS", "SKEWNESS"}
FREQ_STATS = {"MEAN", "MEDIAN", "MODE", "STDDEV", "VARIANCE", "MINIMUM",
              "MAXIMUM", "RANGE", "SKEWNESS", "KURTOSIS", "SEMEAN", "SUM"}


def _stats(req, allowed, default):
    stats = [s.upper() for s in (req.get("statistics") or default)]
    bad = [s for s in stats if s not in allowed]
    if bad:
        raise ValueError("Gecersiz istatistik: %s. Gecerli: %s" % (", ".join(bad), ", ".join(sorted(allowed))))
    return stats


def b_descriptives(req, info):
    v = names(req.get("variables"))
    stats = _stats(req, DESC_STATS, ["MEAN", "STDDEV", "MIN", "MAX", "SKEWNESS", "KURTOSIS"])
    return "DESCRIPTIVES VARIABLES=%s\n  /STATISTICS=%s." % (" ".join(v), " ".join(stats))


def b_frequencies(req, info):
    v = names(req.get("variables"))
    stats = _stats(req, FREQ_STATS, [])
    syntax = "FREQUENCIES VARIABLES=%s\n  /ORDER=ANALYSIS" % " ".join(v)
    if stats:
        syntax += "\n  /STATISTICS=%s" % " ".join(stats)
    return syntax + "."


def b_normality(req, info):
    v = names(req.get("variables"))
    by = req.get("group")
    syntax = "EXAMINE VARIABLES=%s" % " ".join(v)
    if by:
        syntax += " BY %s" % check_name(by)
    syntax += "\n  /PLOT BOXPLOT NPPLOT\n  /STATISTICS DESCRIPTIVES EXTREME\n  /CINTERVAL 95\n  /MISSING LISTWISE"
    syntax += "\n  /NOTOTAL." if by else "\n  /TOTAL."
    return syntax


TMP_GROUP = "noema_grp"


def _two_groups(req, info, numeric_only=False):
    """Return (prelude, 'var(a b)'). String groups are recoded to 1/2 when
    the procedure needs a numeric grouping variable. The recode lives only in
    the working copy; the .sav file is never saved."""
    g = check_name(req.get("group"))
    vals = req.get("group_values") or []
    if len(vals) != 2:
        raise ValueError("group_values iki deger icermeli, or. [1, 2] veya ['f', 'm']")
    is_str = info(g)["is_string"]
    if is_str and numeric_only:
        prelude = ("RECODE %s (%s=1) (%s=2) (ELSE=SYSMIS) INTO %s.\n"
                   "VALUE LABELS %s 1 %s 2 %s.\nEXECUTE." % (
                       g, literal(vals[0], True), literal(vals[1], True), TMP_GROUP,
                       TMP_GROUP, literal(vals[0], True), literal(vals[1], True)))
        return prelude, "%s(1 2)" % TMP_GROUP
    return "", "%s(%s %s)" % (g, literal(vals[0], is_str), literal(vals[1], is_str))


def _autorecode(g):
    return "AUTORECODE VARIABLES=%s /INTO %s /PRINT." % (g, TMP_GROUP)


def b_ttest_independent(req, info):
    dv = names(req.get("variables"))
    _, grp = _two_groups(req, info)
    return ("T-TEST GROUPS=%s\n  /VARIABLES=%s\n  /ES DISPLAY(TRUE)\n"
            "  /CRITERIA=CI(.95)\n  /MISSING=ANALYSIS." % (grp, " ".join(dv)))


def _pairs(req):
    pairs = req.get("pairs") or []
    if not pairs:
        raise ValueError("pairs gerekli, or. [['oncesi', 'sonrasi']]")
    left, right = [], []
    for p in pairs:
        if len(p) != 2:
            raise ValueError("Her cift iki degisken icermeli: %r" % (p,))
        left.append(check_name(p[0]))
        right.append(check_name(p[1]))
    return "%s WITH %s (PAIRED)" % (" ".join(left), " ".join(right))


def b_ttest_paired(req, info):
    return ("T-TEST PAIRS=%s\n  /ES DISPLAY(TRUE)\n  /CRITERIA=CI(.95)\n"
            "  /MISSING=ANALYSIS." % _pairs(req))


def b_anova_oneway(req, info):
    dv = names(req.get("variables"))
    f = check_name(req.get("group"))
    prelude = ""
    if info(f)["is_string"]:
        prelude, f = _autorecode(f) + "\n", TMP_GROUP
    posthoc = [p.upper() for p in (req.get("posthoc") or ["TUKEY", "GH"])]
    allowed = {"TUKEY", "GH", "BONFERRONI", "SCHEFFE", "LSD", "T2", "DUNNETT"}
    bad = [p for p in posthoc if p not in allowed]
    if bad:
        raise ValueError("Gecersiz post hoc: %s" % ", ".join(bad))
    return prelude + ("ONEWAY %s BY %s\n  /ES=OVERALL\n  /STATISTICS DESCRIPTIVES HOMOGENEITY WELCH\n"
            "  /MISSING ANALYSIS\n  /CRITERIA=CILEVEL(0.95)\n  /POSTHOC=%s ALPHA(0.05)."
            % (" ".join(dv), f, " ".join(posthoc)))


def b_correlation(req, info):
    v = names(req.get("variables"), minimum=2)
    method = (req.get("method") or "pearson").lower()
    if method == "pearson":
        return ("CORRELATIONS\n  /VARIABLES=%s\n  /PRINT=TWOTAIL NOSIG\n"
                "  /STATISTICS DESCRIPTIVES\n  /MISSING=PAIRWISE." % " ".join(v))
    if method == "spearman":
        return ("NONPAR CORR\n  /VARIABLES=%s\n  /PRINT=SPEARMAN TWOTAIL NOSIG\n"
                "  /MISSING=PAIRWISE." % " ".join(v))
    raise ValueError("method 'pearson' veya 'spearman' olmali")


def b_crosstabs(req, info):
    r = check_name(req.get("row"))
    c = check_name(req.get("column"))
    return ("CROSSTABS\n  /TABLES=%s BY %s\n  /FORMAT=AVALUE TABLES\n"
            "  /STATISTICS=CHISQ PHI\n  /CELLS=COUNT EXPECTED ROW COLUMN\n"
            "  /COUNT ROUND CELL." % (r, c))


def b_mann_whitney(req, info):
    dv = names(req.get("variables"))
    prelude, grp = _two_groups(req, info, numeric_only=True)
    return (prelude + "\n" if prelude else "") + (
        "NPAR TESTS\n  /M-W= %s BY %s\n  /STATISTICS=DESCRIPTIVES QUARTILES\n  /MISSING ANALYSIS%s." % (" ".join(dv), grp, _exact(req)))


def b_kruskal_wallis(req, info):
    dv = names(req.get("variables"))
    g = check_name(req.get("group"))
    prelude = ""
    if info(g)["is_string"]:
        # AUTORECODE gives codes 1..k in sorted order of the distinct values.
        prelude, g = _autorecode(g) + "\n", TMP_GROUP
        lo, hi = 1, info(check_name(req.get("group")), distinct=True)["n_distinct"]
    else:
        lo, hi = req.get("group_range") or [None, None]
    if lo is None or hi is None:
        raise ValueError("group_range gerekli, or. [1, 3]")
    return prelude + ("NPAR TESTS\n  /K-W=%s BY %s(%s %s)\n  /STATISTICS=DESCRIPTIVES QUARTILES\n  /MISSING ANALYSIS%s."
            % (" ".join(dv), g, literal(lo, False), literal(hi, False), _exact(req)))


def b_wilcoxon(req, info):
    return ("NPAR TESTS\n  /WILCOXON=%s\n  /STATISTICS=DESCRIPTIVES QUARTILES\n  /MISSING ANALYSIS%s."
            % (_pairs(req), _exact(req)))


def b_friedman(req, info):
    v = names(req.get("variables"), minimum=3, label="olcum (ör. on, son, izleme)")
    return ("NPAR TESTS\n  /FRIEDMAN=%s\n  /STATISTICS=DESCRIPTIVES QUARTILES\n  /MISSING LISTWISE%s.\n"
            "NPAR TESTS\n  /KENDALL=%s\n  /MISSING LISTWISE%s."
            % (" ".join(v), _exact(req), " ".join(v), _exact(req)))


def reverse_items(req, items, info):
    """Reverse-score some items into NEW variables noema_r_<item> =
    (scale_min + scale_max) - item. The original items are never changed and
    the file is never saved. Returns (syntax_before, items_to_use)."""
    rev = req.get("reverse_items") or []
    if not rev:
        return "", items
    rev = names(rev, label="ters madde")
    lower = dict((i.lower(), i) for i in items)
    for r in rev:
        if r.lower() not in lower:
            raise ValueError("Ters madde %s, variables listesinde yok" % r)
        if info(r)["is_string"]:
            raise ValueError("Ters madde sayisal olmali: %s" % r)
    try:
        lo, hi = float(req["scale_min"]), float(req["scale_max"])
    except (KeyError, TypeError, ValueError):
        raise ValueError("Ters madde icin scale_min ve scale_max gerekli (or. 1 ve 4)")
    if lo >= hi:
        raise ValueError("scale_min, scale_max'tan kucuk olmali")
    total = lo + hi
    total_txt = ("%d" % total) if total == int(total) else ("%g" % total)
    lines = ["* Noema: ters maddeler yeni degiskenlere cevrilir (%s - madde); orijinal maddeler degismez." % total_txt]
    out = list(items)
    rev_l = set(r.lower() for r in rev)
    for idx, item in enumerate(items):
        if item.lower() in rev_l:
            new = REVERSE_PREFIX + item
            if len(new) > 64:
                raise ValueError("Degisken adi cok uzun: %s" % item)
            lines.append("COMPUTE %s = %s - %s." % (new, total_txt, item))
            lines.append("VARIABLE LABELS %s '%s (ters)'." % (new, item))
            out[idx] = new
    lines.append("EXECUTE.")
    return "\n".join(lines) + "\n", out


def reverse_total(req):
    return "%g" % (float(req["scale_min"]) + float(req["scale_max"]))


def b_reliability(req, info):
    items = names(req.get("variables"), minimum=2, label="madde")
    pre, items = reverse_items(req, items, info)
    label = str(req.get("scale_name") or "Olcek").replace("'", "")[:60]
    return pre + ("RELIABILITY\n  /VARIABLES=%s\n  /SCALE('%s') ALL\n  /MODEL=ALPHA\n"
            "  /STATISTICS=DESCRIPTIVE SCALE\n  /SUMMARY=TOTAL." % (" ".join(items), label))


def scale_score_expr(req):
    items = names(req.get("variables"), minimum=2, label="madde")
    method = str(req.get("method") or "sum").lower()
    if method not in ("sum", "mean"):
        raise ValueError("method 'sum' ya da 'mean' olmali")
    # SUM.n / MEAN.n: score only when every item is answered, so a missing
    # item never silently lowers a total.
    return items, method, "%s.%d(%%s)" % ("SUM" if method == "sum" else "MEAN", len(items))


def b_scale_score(req, info):
    items, method, fmt = scale_score_expr(req)
    name = check_name(req.get("score_name") or "noema_puan")
    try:
        info(name)
    except ValueError:
        pass  # good: the name is free
    else:
        raise ValueError("%s adinda bir degisken zaten var; baska bir score_name verin" % name)
    pre, used = reverse_items(req, items, info)
    expr = fmt % ", ".join(used)
    return pre + ("COMPUTE %s = %s.\nEXECUTE.\n"
                  "DESCRIPTIVES VARIABLES=%s\n  /STATISTICS=MEAN STDDEV MIN MAX SKEWNESS KURTOSIS."
                  % (name, expr, name))


def b_rm_anova(req, info):
    v = names(req.get("variables"), minimum=2, label="olcum (or. on, son, izleme)")
    factor = check_name(req.get("factor_name") or "zaman")
    between = req.get("group")
    prelude, design = "", ""
    lines = ["GLM %s" % " ".join(v)]
    if between:
        g = check_name(between)
        if info(g)["is_string"]:
            prelude, g = _autorecode(g) + "\n", TMP_GROUP
        lines[0] += " BY %s" % g
    lines.append("  /WSFACTOR=%s %d Polynomial" % (factor, len(v)))
    lines.append("  /METHOD=SSTYPE(3)")
    lines.append("  /EMMEANS=TABLES(%s) COMPARE ADJ(BONFERRONI)" % factor)
    if between:
        lines.append("  /EMMEANS=TABLES(%s) COMPARE ADJ(BONFERRONI)" % g)
        lines.append("  /EMMEANS=TABLES(%s*%s) COMPARE(%s) ADJ(BONFERRONI)" % (g, factor, factor))
        lines.append("  /EMMEANS=TABLES(%s*%s) COMPARE(%s) ADJ(BONFERRONI)" % (g, factor, g))
        lines.append("  /PRINT=DESCRIPTIVE ETASQ HOMOGENEITY")
    else:
        lines.append("  /PRINT=DESCRIPTIVE ETASQ")
    lines.append("  /CRITERIA=ALPHA(.05)")
    lines.append("  /WSDESIGN=%s" % factor)
    lines.append("  /DESIGN=%s." % g if between else "  /DESIGN.")
    return prelude + "\n".join(lines)


def rm_anova_menu(req):
    k = len(req.get("variables") or [])
    between = req.get("group")
    return MENU["rm_anova"] % {
        "factor": req.get("factor_name") or "zaman", "k": k,
        "between": ("; Between-Subjects Factor(s): %s" % between) if between else "",
        "homog": ", Homogeneity tests" if between else ""}


BUILDERS = {
    "descriptives": b_descriptives,
    "frequencies": b_frequencies,
    "normality": b_normality,
    "ttest_independent": b_ttest_independent,
    "ttest_paired": b_ttest_paired,
    "anova_oneway": b_anova_oneway,
    "correlation": b_correlation,
    "crosstabs": b_crosstabs,
    "mann_whitney": b_mann_whitney,
    "kruskal_wallis": b_kruskal_wallis,
    "wilcoxon": b_wilcoxon,
    "friedman": b_friedman,
    "reliability": b_reliability,
    "scale_score": b_scale_score,
    "rm_anova": b_rm_anova,
}
