"""Statistical operations and metadata for Askance.

`TESTS` is the source of truth for the catalog and dispatch. SciPy and statsmodels perform
the calculations; this module validates inputs and normalizes their results for MCP.
"""

from __future__ import annotations

import math
import threading
import warnings
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import version
from typing import Any

import scipy
from mcp.server.mcpserver.exceptions import ToolError
from scipy import stats
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.power import (
    FTestAnovaPower,
    GofChisquarePower,
    NormalIndPower,
    TTestIndPower,
    TTestPower,
)
from statsmodels.stats.proportion import proportion_effectsize

ALTERNATIVES = ("two-sided", "less", "greater")

# These keys are passed directly to statsmodels.stats.multitest.multipletests.
CORRECTION_METHODS = {
    "bonferroni": (
        "Single-step Bonferroni; controls the family-wise error rate under any dependence."
    ),
    "sidak": (
        "Single-step Sidak; controls the family-wise error rate for independent or positively "
        "dependent tests."
    ),
    "holm": "Step-down Holm-Bonferroni; controls the family-wise error rate under any dependence.",
    "holm-sidak": (
        "Step-down Holm-Sidak; controls the family-wise error rate for independent or "
        "positively dependent tests."
    ),
    "fdr_bh": (
        "Benjamini-Hochberg; controls the false discovery rate for independent or positively "
        "dependent tests."
    ),
    "fdr_by": "Benjamini-Yekutieli; controls the false discovery rate under any dependence.",
}

# statsmodels uses `n` differently across solvers. `n_is` tells callers whether the result
# counts all observations, one group, or matched pairs. `alternative` is passed to the solvers
# that accept one, so the result can say which test was sized.
POWER_DESIGNS: dict[str, dict[str, Any]] = {
    "one_sample_t": {
        "solver": TTestPower,
        "backend": "statsmodels.stats.power.TTestPower",
        "effect": "Cohen's d",
        "n_is": "total observations",
        "alternative": "two-sided",
        "pairs_with": "one_sample_t",
    },
    "paired_t": {
        "solver": TTestPower,
        "backend": "statsmodels.stats.power.TTestPower",
        "effect": "Cohen's d, on the paired differences",
        "n_is": "number of pairs",
        "alternative": "two-sided",
        "pairs_with": "paired_t",
    },
    "independent_t": {
        "solver": TTestIndPower,
        "backend": "statsmodels.stats.power.TTestIndPower",
        "effect": "Cohen's d",
        "n_is": "observations in the first group",
        "accepts_ratio": True,
        "alternative": "two-sided",
        "pairs_with": "independent_t",
    },
    "two_proportions": {
        "solver": NormalIndPower,
        "backend": "statsmodels.stats.power.NormalIndPower",
        "effect": "Cohen's h",
        "n_is": "observations in the first group",
        "accepts_ratio": True,
        "accepts_proportions": True,
        "alternative": "two-sided",
        # This sizes the uncorrected two-sample comparison. Yates' correction and Fisher's test
        # are more conservative, so the same n gives them less power.
        "pairs_with": "chi_square_independence on a 2x2 table, with correction disabled",
    },
    "one_way_anova": {
        "solver": FTestAnovaPower,
        "backend": "statsmodels.stats.power.FTestAnovaPower",
        "effect": "Cohen's f",
        "n_is": "total observations across all groups",
        "groups_arg": "k_groups",
        "groups_label": "number of groups",
        "pairs_with": "one_way_anova",
    },
    "chi_square": {
        "solver": GofChisquarePower,
        "backend": "statsmodels.stats.power.GofChisquarePower",
        "effect": "Cohen's w",
        "n_is": "total observations in the table",
        "table_shape": True,
        "pairs_with": "chi_square_independence",
    },
}

DERIVES_D = ("one_sample_t", "paired_t", "independent_t")

TESTS: dict[str, dict[str, Any]] = {
    "one_sample_t": {
        "tool": "test_samples",
        "summary": "Is a population mean different from a reference value?",
        "null_hypothesis": "The population mean equals `reference`.",
        "samples": 1,
        "needs_reference": True,
        "directional": True,
        "backend": "scipy.stats.ttest_1samp",
        "assumptions": [
            "Observations are independent.",
            "The data are approximately normal, or the sample is large enough for the "
            "normal approximation.",
        ],
    },
    "independent_t": {
        "tool": "test_samples",
        "summary": "Do two independent groups have different means?",
        "null_hypothesis": "The two population means are equal.",
        "samples": 2,
        "directional": True,
        "accepts_equal_var": True,
        "backend": "scipy.stats.ttest_ind",
        "assumptions": [
            "The two samples are independent.",
            "Each group is approximately normal.",
            "Welch's test is used by default; set equal_var to pool the variances.",
        ],
    },
    "paired_t": {
        "tool": "test_samples",
        "summary": "Is the mean difference between paired measurements non-zero?",
        "null_hypothesis": "The mean of the paired differences is zero.",
        "samples": 2,
        "paired": True,
        "directional": True,
        "backend": "scipy.stats.ttest_rel",
        "assumptions": [
            "Observations are correctly paired and of equal length.",
            "The paired differences are approximately normal.",
        ],
    },
    "mann_whitney_u": {
        "tool": "test_samples",
        "summary": "Do two independent samples come from the same distribution?",
        "null_hypothesis": "The two distributions are equal.",
        "samples": 2,
        "directional": True,
        "backend": "scipy.stats.mannwhitneyu",
        "assumptions": [
            "The two samples are independent.",
            "Reading the result as a difference in medians additionally requires similarly "
            "shaped distributions.",
        ],
    },
    "wilcoxon_signed_rank": {
        "tool": "test_samples",
        "summary": "Are paired differences centered on zero, without assuming normality?",
        "null_hypothesis": "The distribution of the paired differences is centered at zero.",
        "samples": 2,
        "paired": True,
        "directional": True,
        "backend": "scipy.stats.wilcoxon",
        "assumptions": [
            "Observations are correctly paired and of equal length.",
            "The differences are symmetrically distributed.",
            "Pairs with a zero difference are discarded before ranking (SciPy's default "
            "zero_method='wilcox').",
        ],
    },
    "one_way_anova": {
        "tool": "test_samples",
        "summary": "Do several independent groups have the same mean?",
        "null_hypothesis": "All group means are equal.",
        "samples": "2+",
        "backend": "scipy.stats.f_oneway",
        "assumptions": [
            "The samples are independent.",
            "Residuals are approximately normal.",
            "Group variances are equal. Askance does not currently provide Welch ANOVA.",
        ],
    },
    "kruskal_wallis": {
        "tool": "test_samples",
        "summary": "Do several independent groups come from the same distribution?",
        "null_hypothesis": "All group distributions are equal.",
        "samples": "2+",
        "backend": "scipy.stats.kruskal",
        "assumptions": [
            "The samples are independent.",
            "Reading the result as a difference in medians additionally requires similarly "
            "shaped distributions.",
            "The p-value uses a chi-square approximation; SciPy suggests at least 5 "
            "observations per group.",
        ],
    },
    "pearson_correlation": {
        "tool": "test_samples",
        "summary": "Is there a linear association between two paired variables?",
        "null_hypothesis": "The population Pearson correlation is zero.",
        "samples": 2,
        "paired": True,
        "directional": True,
        "backend": "scipy.stats.pearsonr",
        "assumptions": [
            "Pairs are independent and of equal length.",
            "The relationship is linear; the statistic is sensitive to outliers.",
            "The p-value assumes both variables are normally distributed.",
        ],
    },
    "spearman_correlation": {
        "tool": "test_samples",
        "summary": "Is there a monotonic association between two paired variables?",
        "null_hypothesis": "The population Spearman correlation is zero.",
        "samples": 2,
        "paired": True,
        "directional": True,
        "backend": "scipy.stats.spearmanr",
        "assumptions": [
            "Pairs are independent and of equal length.",
            "The variables are at least ordinal.",
            "SciPy documents the p-value as accurate only for large samples, more than about "
            "500 pairs.",
        ],
    },
    "chi_square_independence": {
        "tool": "test_contingency",
        "summary": "Are the row and column variables of a contingency table independent?",
        "null_hypothesis": "The row and column variables are independent.",
        "table": "r x c",
        "accepts_correction": True,
        "backend": "scipy.stats.chi2_contingency",
        "assumptions": [
            "Observations are independent and counts are frequencies, not proportions.",
            "Expected cell counts are large enough; check the reported expected table.",
            "Yates' continuity correction is applied to 2x2 tables unless disabled.",
        ],
    },
    "fisher_exact": {
        "tool": "test_contingency",
        "summary": "Is a 2x2 table consistent with an odds ratio of one?",
        "null_hypothesis": "The odds ratio is one.",
        "table": "2 x 2",
        "directional": True,
        "backend": "scipy.stats.fisher_exact",
        "assumptions": [
            "Observations are independent.",
            "The exact calculation remains valid for small counts.",
        ],
    },
    "binomial_exact": {
        "tool": "test_binomial",
        "summary": "Does an observed success rate differ from a reference probability?",
        "null_hypothesis": "The success probability equals `probability`.",
        "directional": True,
        "backend": "scipy.stats.binomtest",
        "assumptions": [
            "Independent trials with a constant success probability.",
            "The calculation is exact; it does not use a large-sample approximation.",
            "The confidence interval is SciPy's 'exact' (Clopper-Pearson) interval. It inverts "
            "the equal-tailed test, not the two-sided p-value, so near alpha the interval and "
            "the decision can disagree.",
        ],
    },
}


class AskanceError(ToolError, ValueError):
    """Caller-visible validation error.

    `ToolError` preserves the message in MCP responses. `ValueError` supports callers that
    use this module without MCP.
    """


# -- validation ------------------------------------------------------------


def _finite(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AskanceError(f"{what} must be a number, got {value!r}")
    try:
        number = float(value)
    except OverflowError:
        raise AskanceError(f"{what} is too large to represent as a floating-point number") from None
    if not math.isfinite(number):
        raise AskanceError(f"{what} must be finite, got {value!r}; remove or impute it first")
    return number


def _sample(values: Any, label: str) -> list[float]:
    if not isinstance(values, (list, tuple)) or isinstance(values, (str, bytes)):
        raise AskanceError(f"{label} must be an array of numbers")
    if not values:
        raise AskanceError(f"{label} is empty")
    return [_finite(v, f"{label}[{i}]") for i, v in enumerate(values)]


def _alpha(value: Any) -> float:
    alpha = _finite(value, "alpha")
    if not 0.0 < alpha < 1.0:
        raise AskanceError(f"alpha must be between 0 and 1 exclusive, got {alpha}")
    return alpha


def _alternative(value: Any, spec: dict[str, Any], test: str) -> str:
    if value not in ALTERNATIVES:
        raise AskanceError(f"alternative must be one of {list(ALTERNATIVES)}, got {value!r}")
    if value != "two-sided" and not spec.get("directional"):
        raise AskanceError(f"{test} is an omnibus test and only supports alternative='two-sided'")
    return value


def _spec(test: Any, tool: str) -> dict[str, Any]:
    if not isinstance(test, str) or test not in TESTS:
        raise AskanceError(f"unknown test {test!r}; call list_tests for the supported ids")
    spec = TESTS[test]
    if spec["tool"] != tool:
        raise AskanceError(f"{test} is run with {spec['tool']}, not {tool}")
    return spec


def _samples(values: Any, spec: dict[str, Any], test: str) -> list[list[float]]:
    if not isinstance(values, (list, tuple)) or not values:
        raise AskanceError("samples must be a non-empty array of numeric arrays")
    if not all(isinstance(s, (list, tuple)) for s in values):
        raise AskanceError(
            "samples must be an array of arrays, for example [[1, 2, 3]] for a one-sample test"
        )
    samples = [_sample(s, f"samples[{i}]") for i, s in enumerate(values)]

    required = spec["samples"]
    if required == "2+":
        if len(samples) < 2:
            raise AskanceError(f"{test} needs at least 2 samples, got {len(samples)}")
    elif len(samples) != required:
        raise AskanceError(f"{test} needs exactly {required} sample(s), got {len(samples)}")

    if spec.get("paired") and len({len(s) for s in samples}) != 1:
        raise AskanceError(
            f"{test} is paired, so every sample must have the same length, got "
            f"{[len(s) for s in samples]}"
        )
    return samples


def _table(values: Any, spec: dict[str, Any], test: str) -> list[list[int]]:
    if not isinstance(values, (list, tuple)) or not values:
        raise AskanceError("table must be a non-empty array of rows")
    rows = []
    for i, row in enumerate(values):
        if not isinstance(row, (list, tuple)) or not row:
            raise AskanceError(f"table[{i}] must be a non-empty array of counts")
        counts = []
        for j, cell in enumerate(row):
            if isinstance(cell, bool) or not isinstance(cell, int):
                raise AskanceError(f"table[{i}][{j}] must be an integer count, got {cell!r}")
            if cell < 0:
                raise AskanceError(f"table[{i}][{j}] must not be negative, got {cell}")
            counts.append(cell)
        rows.append(counts)
    if len({len(r) for r in rows}) != 1:
        raise AskanceError(f"table rows must have equal length, got {[len(r) for r in rows]}")
    if spec["table"] == "2 x 2" and (len(rows) != 2 or len(rows[0]) != 2):
        raise AskanceError(f"{test} needs a 2x2 table, got {len(rows)}x{len(rows[0])}")
    if len(rows) < 2 or len(rows[0]) < 2:
        raise AskanceError(
            f"{test} needs at least 2 rows and 2 columns to test an association, got "
            f"{len(rows)}x{len(rows[0])}"
        )
    if sum(sum(r) for r in rows) == 0:
        raise AskanceError("table is all zeros")
    # An empty row or column leaves a smaller table, whose test the backends report as p = 1
    # or refuse. Dropping it would change the degrees of freedom, so the caller must decide.
    for axis, lines in (("row", rows), ("column", list(zip(*rows)))):
        for i, line in enumerate(lines):
            if sum(line) == 0:
                raise AskanceError(
                    f"table {axis} {i} has no observations; every row and column of a test of "
                    "association needs at least one count"
                )
    return rows


# -- result shaping --------------------------------------------------------


def _number(value: Any) -> float | None:
    """A JSON-safe float. Non-finite results become null rather than invalid JSON."""
    if value is None:
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _result(
    test: str,
    statistic: Any,
    p_value: Any,
    alpha: float,
    alternative: str | None,
    method: dict[str, Any],
    sample_sizes: list[int],
    captured: list[warnings.WarningMessage],
    notes: tuple[str, ...] = (),
    **extra: Any,
) -> dict[str, Any]:
    messages = [f"{w.category.__name__}: {w.message}" for w in captured]
    messages.extend(notes)
    raw_statistic = statistic
    statistic, p_value = _number(statistic), _number(p_value)
    if p_value is None:
        messages.append(
            "The backend returned an undefined p-value, usually from constant or degenerate "
            "input. No decision can be made."
        )
        decision = None
    else:
        if statistic is None and raw_statistic is not None:
            messages.append(
                f"The backend returned a statistic of {float(raw_statistic)}, which JSON cannot "
                "represent, so it is reported as null."
            )
        decision = "reject_null" if p_value < alpha else "fail_to_reject"
    result = {
        "test": test,
        "null_hypothesis": TESTS[test]["null_hypothesis"],
        "statistic": statistic,
        "p_value": p_value,
        "alpha": alpha,
        "decision": decision,
        "sample_sizes": sample_sizes,
        "method": method,
        "versions": {"askance": version("askance"), "scipy": scipy.__version__},
        "warnings": messages,
    }
    if alternative is not None:
        result["alternative"] = alternative
    result.update(extra)
    return result


# -- dispatch --------------------------------------------------------------

# `warnings.catch_warnings` swaps process-wide state, and the MCP SDK runs each sync tool on a
# worker thread. Unserialized, overlapping calls record each other's warnings and restore each
# other's filters out of order, leaving the process modified after both return.
_BACKEND_LOCK = threading.Lock()


@contextmanager
def _backend(function: str) -> Iterator[list[warnings.WarningMessage]]:
    """Capture a backend call's warnings, and pass its input errors on to the caller.

    The MCP SDK reports only `ToolError` messages; any other exception reaches the caller as
    "Error executing tool", without the reason.
    """
    with _BACKEND_LOCK, warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        try:
            yield captured
        except AskanceError:
            raise
        except ValueError as exc:
            raise AskanceError(f"{function} rejected the input: {exc}") from exc


def run_samples_test(
    test: str,
    samples: Any,
    reference: Any = None,
    alternative: str = "two-sided",
    equal_var: bool = False,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Run a test whose input is one or more numeric samples."""
    spec = _spec(test, "test_samples")
    data = _samples(samples, spec, test)
    alternative = _alternative(alternative, spec, test)
    alpha = _alpha(alpha)

    if spec.get("needs_reference"):
        if reference is None:
            raise AskanceError(f"{test} needs a `reference` value to test against")
        reference = _finite(reference, "reference")
    elif reference is not None:
        raise AskanceError(f"{test} does not use `reference`")

    if equal_var and not spec.get("accepts_equal_var"):
        raise AskanceError(f"{test} does not use `equal_var`")

    if test == "wilcoxon_signed_rank" and data[0] == data[1]:
        raise AskanceError(
            f"every paired difference is zero; {test} discards zero differences, which leaves "
            "nothing to rank"
        )

    options: dict[str, Any] = {}
    extra: dict[str, Any] = {}
    directional = {"alternative": alternative} if spec.get("directional") else {}

    with _backend(spec["backend"]) as captured:
        if test == "one_sample_t":
            out = stats.ttest_1samp(data[0], popmean=reference, **directional)
            options = {"popmean": reference, **directional}
        elif test == "independent_t":
            out = stats.ttest_ind(data[0], data[1], equal_var=equal_var, **directional)
            options = {"equal_var": equal_var, **directional}
        elif test == "paired_t":
            out = stats.ttest_rel(data[0], data[1], **directional)
            options = dict(directional)
        elif test == "mann_whitney_u":
            out = stats.mannwhitneyu(data[0], data[1], **directional)
            options = dict(directional)
        elif test == "wilcoxon_signed_rank":
            out = stats.wilcoxon(data[0], data[1], **directional)
            options = dict(directional)
        elif test == "one_way_anova":
            out = stats.f_oneway(*data)
        elif test == "kruskal_wallis":
            out = stats.kruskal(*data)
        elif test == "pearson_correlation":
            out = stats.pearsonr(data[0], data[1], **directional)
            extra["correlation"] = _number(out.statistic)
            options = dict(directional)
        elif test == "spearman_correlation":
            out = stats.spearmanr(data[0], data[1], **directional)
            extra["correlation"] = _number(out.statistic)
            options = dict(directional)
        else:  # pragma: no cover - guarded by _spec
            raise AskanceError(f"{test} has no sample-based implementation")

    # Only the t-tests' results carry degrees of freedom; reporting any other would mean
    # computing it here.
    if hasattr(out, "df"):
        extra["degrees_of_freedom"] = _number(out.df)

    return _result(
        test,
        out.statistic,
        out.pvalue,
        alpha,
        alternative if spec.get("directional") else None,
        {"function": spec["backend"], "options": options},
        [len(s) for s in data],
        captured,
        **extra,
    )


def run_contingency_test(
    test: str,
    table: Any,
    alternative: str = "two-sided",
    correction: bool = True,
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Run a test of association on a table of counts."""
    spec = _spec(test, "test_contingency")
    counts = _table(table, spec, test)
    alternative = _alternative(alternative, spec, test)
    alpha = _alpha(alpha)

    extra: dict[str, Any] = {}
    with _backend(spec["backend"]) as captured:
        if test == "chi_square_independence":
            out = stats.chi2_contingency(counts, correction=correction)
            extra["degrees_of_freedom"] = int(out.dof)
            extra["expected_frequencies"] = [[_number(c) for c in row] for row in out.expected_freq]
            options = {"correction": correction and len(counts) == 2 == len(counts[0])}
        else:
            out = stats.fisher_exact(counts, alternative=alternative)
            extra["odds_ratio"] = _number(out.statistic)
            options = {"alternative": alternative}

    return _result(
        test,
        out.statistic,
        out.pvalue,
        alpha,
        alternative if spec.get("directional") else None,
        {"function": spec["backend"], "options": options},
        [sum(sum(r) for r in counts)],
        captured,
        **extra,
    )


def run_binomial_test(
    successes: Any,
    trials: Any,
    probability: Any = 0.5,
    alternative: str = "two-sided",
    alpha: float = 0.05,
) -> dict[str, Any]:
    """Run an exact binomial test on a count of successes."""
    spec = TESTS["binomial_exact"]
    alternative = _alternative(alternative, spec, "binomial_exact")
    alpha = _alpha(alpha)

    for name, value in (("successes", successes), ("trials", trials)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise AskanceError(f"{name} must be an integer, got {value!r}")
    if trials <= 0:
        raise AskanceError(f"trials must be positive, got {trials}")
    if not 0 <= successes <= trials:
        raise AskanceError(f"successes must be between 0 and trials ({trials}), got {successes}")
    probability = _finite(probability, "probability")
    if not 0.0 <= probability <= 1.0:
        raise AskanceError(f"probability must be between 0 and 1, got {probability}")

    with _backend(spec["backend"]) as captured:
        out = stats.binomtest(successes, trials, probability, alternative=alternative)
        interval = out.proportion_ci(confidence_level=1 - alpha, method="exact")

    notes: tuple[str, ...] = ()
    if (out.pvalue < alpha) == (interval.low <= probability <= interval.high):
        notes = (
            "The decision and the confidence interval disagree about `probability`. SciPy's "
            "two-sided p-value sums every outcome no more likely than the one observed, while "
            "the Clopper-Pearson interval inverts the equal-tailed test; near alpha they can "
            "differ.",
        )

    return _result(
        "binomial_exact",
        out.statistic,
        out.pvalue,
        alpha,
        alternative,
        {
            "function": spec["backend"],
            "options": {"p": probability, "alternative": alternative},
        },
        [trials],
        captured,
        notes,
        successes=successes,
        proportion=_number(out.statistic),
        proportion_confidence_interval={
            "low": _number(interval.low),
            "high": _number(interval.high),
            "confidence_level": 1 - alpha,
            "method": "exact",
        },
    )


def adjust_p_values(p_values: Any, method: str, alpha: float = 0.05) -> dict[str, Any]:
    """Correct a family of p-values for multiple testing."""
    if not isinstance(method, str) or method not in CORRECTION_METHODS:
        raise AskanceError(
            f"unknown method {method!r}; supported methods are {list(CORRECTION_METHODS)}"
        )
    if not isinstance(p_values, (list, tuple)) or not p_values:
        raise AskanceError("p_values must be a non-empty array of numbers")
    values = []
    for i, p in enumerate(p_values):
        number = _finite(p, f"p_values[{i}]")
        if not 0.0 <= number <= 1.0:
            raise AskanceError(f"p_values[{i}] must be between 0 and 1, got {number}")
        values.append(number)
    alpha = _alpha(alpha)

    with _backend("statsmodels.stats.multitest.multipletests") as captured:
        reject, adjusted, alpha_sidak, alpha_bonferroni = multipletests(
            values, alpha=alpha, method=method
        )

    return {
        "method": method,
        "description": CORRECTION_METHODS[method],
        "alpha": alpha,
        "p_values": values,
        "adjusted_p_values": [_number(p) for p in adjusted],
        "reject": [bool(r) for r in reject],
        "corrected_alpha": {
            "sidak": _number(alpha_sidak),
            "bonferroni": _number(alpha_bonferroni),
        },
        "versions": {
            "askance": version("askance"),
            "statsmodels": version("statsmodels"),
        },
        "warnings": [f"{w.category.__name__}: {w.message}" for w in captured],
    }


def _positive(value: Any, what: str) -> float:
    number = _finite(value, what)
    if number <= 0:
        raise AskanceError(f"{what} must be positive, got {number}")
    return number


def _effect_size(
    design: str,
    spec: dict[str, Any],
    effect_size: Any,
    proportions: Any,
    difference: Any,
    std_dev: Any,
) -> tuple[float | None, dict[str, Any]]:
    """Cohen's effect size, either supplied directly or derived from real quantities."""
    raw_given = proportions is not None or difference is not None or std_dev is not None
    if effect_size is not None and raw_given:
        raise AskanceError(
            f"give {design} either effect_size or the quantities to derive it from, not both"
        )

    if proportions is not None:
        if not spec.get("accepts_proportions"):
            raise AskanceError(f"{design} does not use `proportions`")
        if not isinstance(proportions, (list, tuple)) or len(proportions) != 2:
            raise AskanceError("proportions must be two numbers between 0 and 1, e.g. [0.10, 0.12]")
        first, second = (_finite(p, f"proportions[{i}]") for i, p in enumerate(proportions))
        for p in (first, second):
            if not 0.0 <= p <= 1.0:
                raise AskanceError(f"proportions must be between 0 and 1, got {p}")
        if first == second:
            raise AskanceError("the two proportions are equal, so there is no effect to detect")
        derived = float(proportion_effectsize(second, first))
        return abs(derived), {"from": "proportions", "proportions": [first, second]}

    if difference is not None or std_dev is not None:
        if design not in DERIVES_D:
            raise AskanceError(f"{design} does not use `difference` and `std_dev`")
        if difference is None or std_dev is None:
            raise AskanceError("give both `difference` and `std_dev`, or neither")
        size = abs(_finite(difference, "difference"))
        spread = _positive(std_dev, "std_dev")
        if size == 0:
            raise AskanceError("a difference of zero leaves no nonzero effect to detect")
        return size / spread, {
            "from": "difference / std_dev",
            "difference": size,
            "std_dev": spread,
        }

    if effect_size is None:
        return None, {"from": "solved"}
    return abs(_positive(effect_size, "effect_size")), {"from": "given"}


def _at_least_two(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 2:
        raise AskanceError(f"{name} must be an integer of at least 2, got {value!r}")
    return value


def analyze_power(
    design: str,
    effect_size: Any = None,
    n: Any = None,
    alpha: Any = 0.05,
    power: Any = None,
    ratio: Any = 1.0,
    groups: Any = None,
    proportions: Any = None,
    difference: Any = None,
    std_dev: Any = None,
    rows: Any = None,
    columns: Any = None,
) -> dict[str, Any]:
    """Solve for whichever one of effect size, sample size, alpha or power is left out."""
    if not isinstance(design, str) or design not in POWER_DESIGNS:
        raise AskanceError(
            f"unknown design {design!r}; supported designs are {list(POWER_DESIGNS)}"
        )
    spec = POWER_DESIGNS[design]

    size, effect_source = _effect_size(design, spec, effect_size, proportions, difference, std_dev)

    unknowns = [
        name
        for name, value in (("effect_size", size), ("n", n), ("alpha", alpha), ("power", power))
        if value is None
    ]
    if len(unknowns) != 1:
        raise AskanceError(
            "leave exactly one of effect_size, n, alpha, and power unspecified. effect_size "
            "may instead be derived from proportions or from difference and std_dev. "
            f"Unspecified: {', '.join(unknowns) or 'none'}. To solve for alpha, pass "
            "alpha=None because its default is 0.05."
        )
    solved_for = unknowns[0]

    if n is not None:
        n = _positive(n, "n")
        if n <= 1:
            raise AskanceError(f"n must be greater than 1, got {n}")
    if alpha is not None:
        alpha = _alpha(alpha)
    if power is not None:
        power = _finite(power, "power")
        if not 0.0 < power < 1.0:
            raise AskanceError(f"power must be between 0 and 1 exclusive, got {power}")
    if alpha is not None and power is not None and power <= alpha:
        raise AskanceError(
            f"power ({power}) must exceed alpha ({alpha}): with no effect at all, a test "
            "already rejects with probability alpha"
        )

    arguments: dict[str, Any] = {"effect_size": size, "alpha": alpha, "power": power}
    arguments["nobs1" if spec.get("accepts_ratio") else "nobs"] = n

    if spec.get("accepts_ratio"):
        arguments["ratio"] = _positive(ratio, "ratio")
    elif ratio != 1.0:
        raise AskanceError(f"{design} does not use `ratio`")

    if "groups_arg" in spec:
        if groups is None:
            raise AskanceError(f"{design} needs `groups`: the {spec['groups_label']}")
        arguments[spec["groups_arg"]] = _at_least_two(groups, "groups")
        if n is not None and n <= groups:
            raise AskanceError(
                f"n must be greater than groups for {design}, got n={n} and groups={groups}; "
                "the within-group degrees of freedom are n - groups"
            )
    elif groups is not None:
        hint = "; give the table's `rows` and `columns` instead" if spec.get("table_shape") else ""
        raise AskanceError(f"{design} does not use `groups`{hint}")

    if spec.get("table_shape"):
        if rows is None or columns is None:
            raise AskanceError(
                f"{design} needs `rows` and `columns`: the shape of the contingency table"
            )
        rows, columns = _at_least_two(rows, "rows"), _at_least_two(columns, "columns")
        # GofChisquarePower tests n_bins - 1 degrees of freedom, while a test of independence on
        # an r x c table has (r - 1)(c - 1).
        arguments["n_bins"] = (rows - 1) * (columns - 1) + 1
    elif rows is not None or columns is not None:
        raise AskanceError(f"{design} does not use `rows` or `columns`")

    if "alternative" in spec:
        arguments["alternative"] = spec["alternative"]

    with _backend(spec["backend"]) as captured:
        try:
            answer = float(spec["solver"]().solve_power(**arguments))
        except Exception as exc:
            raise AskanceError(
                f"statsmodels could not solve for {solved_for} with these inputs: {exc}"
            ) from exc

    if not math.isfinite(answer):
        raise AskanceError(
            f"statsmodels could not solve for {solved_for} with these inputs; it returned "
            f"{answer}. A very large effect can exceed the requested power even at the "
            "smallest sample, and a very small one can need an impractically large sample."
        )

    resolved = {"effect_size": size, "n": n, "alpha": alpha, "power": power}
    resolved[solved_for] = answer

    result = {
        "design": design,
        "solved_for": solved_for,
        "effect_size": _number(resolved["effect_size"]),
        "effect_size_metric": spec["effect"],
        "effect_size_source": effect_source,
        "n": _number(n),
        "n_is": spec["n_is"],
        "alpha": _number(resolved["alpha"]),
        "power": _number(resolved["power"]),
        "method": {
            "class": spec["backend"],
            "options": {
                key: arguments[key]
                for key in ("ratio", "alternative", "k_groups", "n_bins")
                if key in arguments
            },
        },
        "versions": {"askance": version("askance"), "statsmodels": version("statsmodels")},
        "warnings": [f"{w.category.__name__}: {w.message}" for w in captured],
    }
    if solved_for == "n":
        # Rounding down would leave the study short of the requested power. A one-way ANOVA
        # total is rounded to a multiple of groups, so that the groups can be equal.
        step = groups if "groups_arg" in spec else 1
        result["n"] = step * math.ceil(answer / step)
        result["n_exact"] = _number(answer)
    if spec.get("accepts_ratio"):
        second = arguments["ratio"] * resolved["n"]
        result["n_second_group"] = math.ceil(second) if solved_for == "n" else _number(second)
    if spec.get("table_shape"):
        result["rows"], result["columns"] = rows, columns
    return result


def list_tests() -> dict[str, Any]:
    """The catalog behind the MCP `list_tests` tool."""
    return {
        "tests": [
            {
                "id": test_id,
                "tool": spec["tool"],
                "summary": spec["summary"],
                "null_hypothesis": spec["null_hypothesis"],
                "input": (
                    f"{spec['samples']} numeric sample(s)"
                    + (", paired and equal length" if spec.get("paired") else "")
                    if "samples" in spec
                    else f"a {spec['table']} table of counts"
                    if "table" in spec
                    else "successes and trials"
                ),
                "alternatives": list(ALTERNATIVES) if spec.get("directional") else ["two-sided"],
                "assumptions": spec["assumptions"],
                "backend": spec["backend"],
            }
            for test_id, spec in TESTS.items()
        ],
        "correction_methods": [
            {"id": name, "description": description}
            for name, description in CORRECTION_METHODS.items()
        ],
        "power_designs": [
            {
                "id": design,
                "effect_size_metric": spec["effect"],
                "n_is": spec["n_is"],
                "pairs_with": spec["pairs_with"],
                "backend": spec["backend"],
            }
            for design, spec in POWER_DESIGNS.items()
        ],
        "notes": [
            "Askance never selects a test for you and never reports that assumptions hold.",
            "A p-value at or above alpha is reported as fail_to_reject, which is not evidence "
            "that the null hypothesis is true.",
            "Missing and non-finite values are rejected; clean the data before calling.",
            "Use power designs before collecting data and hypothesis tests afterward.",
            "Power designs for the t-tests and two_proportions size a two-sided test.",
        ],
        "versions": {
            "askance": version("askance"),
            "scipy": scipy.__version__,
            "statsmodels": version("statsmodels"),
        },
    }
