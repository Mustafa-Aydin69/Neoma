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
    "reliability": "Analyze > Scale > Reliability Analysis (Model: Alpha; Statistics: Item, Scale, Scale if item deleted)",
}

FILTER_MENU = "Once: Data > Select Cases > If condition is satisfied > %s"

EXACT_NOTE = " (Exact... dugmesi > Exact)"


def filter_syntax(flt, info):
    """Keep only the cases where variable == value. Applies to the working
    copy only; the .sav file is never saved."""
    if not flt:
        return "", None
    var = check_name(flt.get("variable"))
    is_str = info(var)["is_string"]
    cond = "%s = %s" % (var, literal(flt.get("value"), is_str))
    return "SELECT IF (%s).\nEXECUTE.\n" % cond, cond


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


def b_reliability(req, info):
    items = names(req.get("variables"), minimum=2, label="madde")
    label = str(req.get("scale_name") or "Olcek").replace("'", "")[:60]
    return ("RELIABILITY\n  /VARIABLES=%s\n  /SCALE('%s') ALL\n  /MODEL=ALPHA\n"
            "  /STATISTICS=DESCRIPTIVE SCALE\n  /SUMMARY=TOTAL." % (" ".join(items), label))


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
}
