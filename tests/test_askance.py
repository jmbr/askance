"""Statistical parity, validation, and MCP integration tests.

Every advertised calculation is compared with a direct backend call. The subprocess test
launches the installed command from an unrelated directory without an activated virtualenv.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters
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

from askance import hypothesis as H
from askance.server import mcp

ROOT = Path(__file__).resolve().parent.parent

A = [2.1, 3.4, 1.9, 5.6, 4.2, 3.3, 2.8, 4.9, 3.1, 2.2]
B = [4.5, 5.1, 3.9, 6.2, 5.8, 4.1, 5.5, 6.9, 4.4, 5.0]
C = [1.1, 2.2, 0.9, 3.4, 2.8, 1.7, 2.5, 3.1, 1.4, 2.0]
TABLE = [[12, 5], [3, 15]]
WIDE = [[10, 20, 30], [6, 9, 17]]

pytestmark = pytest.mark.filterwarnings("ignore::DeprecationWarning")


# -- statistical parity ----------------------------------------------------


def _expected(test: str) -> tuple[float, float]:
    match test:
        case "one_sample_t":
            r = stats.ttest_1samp(A, popmean=3.0)
        case "independent_t":
            r = stats.ttest_ind(A, B, equal_var=False)
        case "paired_t":
            r = stats.ttest_rel(A, B)
        case "mann_whitney_u":
            r = stats.mannwhitneyu(A, B)
        case "wilcoxon_signed_rank":
            r = stats.wilcoxon(A, B)
        case "one_way_anova":
            r = stats.f_oneway(A, B, C)
        case "kruskal_wallis":
            r = stats.kruskal(A, B, C)
        case "pearson_correlation":
            r = stats.pearsonr(A, B)
        case "spearman_correlation":
            r = stats.spearmanr(A, B)
        case "chi_square_independence":
            r = stats.chi2_contingency(TABLE)
        case "fisher_exact":
            r = stats.fisher_exact(TABLE)
        case "binomial_exact":
            r = stats.binomtest(7, 20, 0.5)
        case _:  # pragma: no cover
            raise AssertionError(f"no fixture for {test}")
    return float(r.statistic), float(r.pvalue)


def _run(test: str) -> dict:
    spec = H.TESTS[test]
    if spec["tool"] == "test_binomial":
        return H.run_binomial_test(7, 20, 0.5)
    if spec["tool"] == "test_contingency":
        return H.run_contingency_test(test, TABLE)
    samples = {1: [A], 2: [A, B], "2+": [A, B, C]}[spec["samples"]]
    return H.run_samples_test(test, samples, reference=3.0 if spec.get("needs_reference") else None)


@pytest.mark.parametrize("test", list(H.TESTS))
def test_matches_the_backend(test: str) -> None:
    statistic, p_value = _expected(test)
    result = _run(test)
    assert result["statistic"] == pytest.approx(statistic)
    assert result["p_value"] == pytest.approx(p_value)
    assert result["test"] == test
    assert result["method"]["function"] == H.TESTS[test]["backend"]
    assert result["versions"]["scipy"]


@pytest.mark.parametrize("test", list(H.TESTS))
def test_result_is_json_safe_and_decisive(test: str) -> None:
    result = _run(test)
    assert json.loads(json.dumps(result, allow_nan=False)) == result
    expected = "reject_null" if result["p_value"] < result["alpha"] else "fail_to_reject"
    assert result["decision"] == expected


@pytest.mark.parametrize("method", list(H.CORRECTION_METHODS))
def test_corrections_match_statsmodels(method: str) -> None:
    p_values = [0.001, 0.04, 0.03, 0.2, 0.7]
    reject, adjusted, _, _ = multipletests(p_values, alpha=0.05, method=method)
    result = H.adjust_p_values(p_values, method)
    assert result["adjusted_p_values"] == pytest.approx(list(adjusted))
    assert result["reject"] == list(reject)
    assert result["p_values"] == p_values, "input order must be preserved"


def test_correction_preserves_the_caller_order() -> None:
    """statsmodels may sort internally; results must retain the input order."""
    result = H.adjust_p_values([0.9, 0.001, 0.5], "holm")
    assert result["reject"] == [False, True, False]


def test_independent_t_defaults_to_welch() -> None:
    welch = H.run_samples_test("independent_t", [A, B])
    student = H.run_samples_test("independent_t", [A, B], equal_var=True)
    assert welch["statistic"] == pytest.approx(stats.ttest_ind(A, B, equal_var=False).statistic)
    assert student["statistic"] == pytest.approx(stats.ttest_ind(A, B, equal_var=True).statistic)
    assert welch["method"]["options"]["equal_var"] is False


@pytest.mark.parametrize("alternative", ["two-sided", "less", "greater"])
def test_directional_alternatives_reach_the_backend(alternative: str) -> None:
    result = H.run_samples_test("independent_t", [A, B], alternative=alternative)
    expected = stats.ttest_ind(A, B, equal_var=False, alternative=alternative)
    assert result["p_value"] == pytest.approx(float(expected.pvalue))
    assert result["alternative"] == alternative


def test_chi_square_reports_expected_counts_and_correction() -> None:
    result = H.run_contingency_test("chi_square_independence", WIDE)
    expected = stats.chi2_contingency(WIDE)
    assert result["degrees_of_freedom"] == int(expected.dof)
    assert result["expected_frequencies"][0] == pytest.approx(list(expected.expected_freq[0]))
    # Yates' correction only applies to 2x2, whatever the caller asked for.
    assert result["method"]["options"]["correction"] is False


def test_undefined_p_value_is_reported_rather_than_invented() -> None:
    """An undefined backend result must not become a decision."""
    result = H.run_samples_test("pearson_correlation", [[1.0, 1.0, 1.0], [1.0, 2.0, 3.0]])
    assert result["p_value"] is None
    assert result["decision"] is None
    assert result["warnings"]
    json.dumps(result, allow_nan=False)


# -- validation ------------------------------------------------------------


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: H.run_samples_test("nope", [A]), "unknown test"),
        (lambda: H.run_samples_test("fisher_exact", [A]), "test_contingency"),
        (lambda: H.run_samples_test("paired_t", [A, B[:3]]), "same length"),
        (lambda: H.run_samples_test("one_sample_t", [A, B]), "exactly 1"),
        (lambda: H.run_samples_test("independent_t", [A]), "exactly 2"),
        (lambda: H.run_samples_test("one_way_anova", [A]), "at least 2"),
        (lambda: H.run_samples_test("one_sample_t", [A]), "needs a `reference`"),
        (lambda: H.run_samples_test("paired_t", [A, B], reference=1.0), "does not use"),
        (lambda: H.run_samples_test("paired_t", [A, B], equal_var=True), "does not use"),
        (lambda: H.run_samples_test("one_way_anova", [A, B], alternative="less"), "omnibus"),
        (lambda: H.run_samples_test("independent_t", [A, B], alternative="up"), "alternative"),
        (lambda: H.run_samples_test("independent_t", [A, B], alpha=0), "alpha"),
        (lambda: H.run_samples_test("independent_t", [A, B], alpha=1), "alpha"),
        (lambda: H.run_samples_test("paired_t", [A, [float("nan")] * 10]), "finite"),
        (lambda: H.run_samples_test("paired_t", [A, [float("inf")] * 10]), "finite"),
        (lambda: H.run_samples_test("independent_t", [A, ["x"] * 10]), "must be a number"),
        (lambda: H.run_samples_test("independent_t", [A, []]), "empty"),
        (lambda: H.run_samples_test("independent_t", [A, B[0]]), "array of arrays"),
        (lambda: H.run_samples_test("independent_t", []), "non-empty"),
        (lambda: H.run_contingency_test("fisher_exact", WIDE), "2x2"),
        (lambda: H.run_contingency_test("chi_square_independence", [[1, 2], [3]]), "equal length"),
        (lambda: H.run_contingency_test("chi_square_independence", [[1, -2], [3, 4]]), "negative"),
        (lambda: H.run_contingency_test("chi_square_independence", [[1, 2.5], [3, 4]]), "integer"),
        (lambda: H.run_contingency_test("chi_square_independence", [[0, 0], [0, 0]]), "all zeros"),
        (lambda: H.run_binomial_test(30, 10), "between 0 and trials"),
        (lambda: H.run_binomial_test(-1, 10), "between 0 and trials"),
        (lambda: H.run_binomial_test(1, 0), "trials must be positive"),
        (lambda: H.run_binomial_test(1.5, 10), "must be an integer"),
        (lambda: H.run_binomial_test(1, 10, 1.5), "between 0 and 1"),
        (lambda: H.adjust_p_values([0.1], "nope"), "unknown method"),
        (lambda: H.adjust_p_values([0.1, 1.5], "holm"), "between 0 and 1"),
        (lambda: H.adjust_p_values([], "holm"), "non-empty"),
        (lambda: H.adjust_p_values([0.1, float("nan")], "holm"), "finite"),
    ],
)
def test_bad_input_is_refused_with_a_usable_message(call, message: str) -> None:
    with pytest.raises(H.AskanceError, match=re.escape(message)):
        call()


def test_booleans_are_not_numbers() -> None:
    """Python treats bool as int, but accepting it would corrupt numeric input."""
    with pytest.raises(H.AskanceError, match="must be a number"):
        H.run_samples_test("one_sample_t", [[True, False, True]], reference=0.5)


# -- power and sample size -------------------------------------------------

POWER_FIXTURES = {
    "one_sample_t": (TTestPower, {"effect_size": 0.5, "power": 0.8, "alpha": 0.05}, {}),
    "paired_t": (TTestPower, {"effect_size": 0.6, "power": 0.9, "alpha": 0.05}, {}),
    "independent_t": (
        TTestIndPower,
        {"effect_size": 0.5, "power": 0.8, "alpha": 0.05, "ratio": 1.0},
        {},
    ),
    "two_proportions": (
        NormalIndPower,
        {"effect_size": 0.2, "power": 0.8, "alpha": 0.05, "ratio": 1.0},
        {},
    ),
    "one_way_anova": (
        FTestAnovaPower,
        {"effect_size": 0.25, "power": 0.8, "alpha": 0.05, "k_groups": 3},
        {"groups": 3},
    ),
    "chi_square": (
        GofChisquarePower,
        {"effect_size": 0.3, "power": 0.8, "alpha": 0.05, "n_bins": 4},
        {"groups": 4},
    ),
}


@pytest.mark.parametrize("design", list(H.POWER_DESIGNS))
def test_power_matches_statsmodels(design: str) -> None:
    solver, backend_args, extra = POWER_FIXTURES[design]
    expected = float(solver().solve_power(**backend_args))
    result = H.analyze_power(
        design,
        effect_size=backend_args["effect_size"],
        power=backend_args["power"],
        alpha=backend_args["alpha"],
        **extra,
    )
    assert result["solved_for"] == "n"
    assert result["n_exact"] == pytest.approx(expected)
    # Rounding down would produce less power than requested.
    assert result["n"] == math.ceil(expected)
    assert result["method"]["class"] == H.POWER_DESIGNS[design]["backend"]
    json.loads(json.dumps(result, allow_nan=False))


@pytest.mark.parametrize("unknown", ["effect_size", "n", "alpha", "power"])
def test_solves_for_whichever_is_left_out(unknown: str) -> None:
    full = {"effect_size": 0.5, "n": 64.0, "alpha": 0.05, "power": 0.8}
    # alpha defaults to 0.05, so solving for it requires an explicit None.
    known = {k: (None if k == unknown else v) for k, v in full.items()}
    result = H.analyze_power("independent_t", **known)
    assert result["solved_for"] == unknown
    assert result[unknown] is not None

    # Round-trip through a second unknown to check the solver is internally consistent.
    answer = result.get("n_exact", result[unknown]) if unknown == "n" else result[unknown]
    target = "power" if unknown != "power" else "n"
    roundtrip = dict(full)
    roundtrip[unknown] = answer
    roundtrip[target] = None
    again = H.analyze_power("independent_t", **roundtrip)
    assert again[target] == pytest.approx(full[target], rel=0.02)


def test_proportions_become_cohens_h() -> None:
    """Callers may supply rates instead of calculating Cohen's h."""
    result = H.analyze_power("two_proportions", proportions=[0.10, 0.12], power=0.8)
    expected = abs(float(proportion_effectsize(0.12, 0.10)))
    assert result["effect_size"] == pytest.approx(expected)
    assert result["effect_size_source"]["from"] == "proportions"
    assert result["n"] == math.ceil(
        float(NormalIndPower().solve_power(effect_size=expected, power=0.8, alpha=0.05, ratio=1.0))
    )


def test_difference_and_spread_become_cohens_d() -> None:
    result = H.analyze_power("independent_t", difference=20.0, std_dev=40.0, power=0.8)
    assert result["effect_size"] == pytest.approx(0.5)
    assert result["effect_size_source"]["from"] == "difference / std_dev"


def test_sample_size_is_reported_for_the_right_thing() -> None:
    """Each statsmodels solver assigns a different meaning to sample size."""
    assert "first group" in H.POWER_DESIGNS["independent_t"]["n_is"]
    assert "total" in H.POWER_DESIGNS["one_way_anova"]["n_is"]
    assert H.analyze_power("independent_t", effect_size=0.5, power=0.8)["n_is"] == (
        "observations in the first group"
    )


@pytest.mark.parametrize(
    ("call", "message"),
    [
        (lambda: H.analyze_power("wilcoxon", effect_size=0.5, power=0.8), "unknown design"),
        (lambda: H.analyze_power("independent_t", effect_size=0.5), "leave exactly one"),
        (
            lambda: H.analyze_power("independent_t", effect_size=0.5, n=64, power=0.8),
            "leave exactly one",
        ),
        (
            lambda: H.analyze_power("independent_t", effect_size=0.5, proportions=[0.1, 0.2]),
            "not both",
        ),
        (lambda: H.analyze_power("one_way_anova", effect_size=0.25, power=0.8), "needs `groups`"),
        (
            lambda: H.analyze_power("one_way_anova", effect_size=0.25, power=0.8, groups=1),
            "at least 2",
        ),
        (
            lambda: H.analyze_power("independent_t", effect_size=0.5, power=0.8, groups=3),
            "does not use `groups`",
        ),
        (
            lambda: H.analyze_power(
                "one_way_anova", effect_size=0.25, power=0.8, groups=3, ratio=2
            ),
            "does not use `ratio`",
        ),
        (
            lambda: H.analyze_power("one_sample_t", proportions=[0.1, 0.2], power=0.8),
            "does not use `proportions`",
        ),
        (
            lambda: H.analyze_power("chi_square", difference=1, std_dev=2, power=0.8, groups=3),
            "does not use `difference`",
        ),
        (
            lambda: H.analyze_power("independent_t", difference=20.0, power=0.8),
            "both `difference` and `std_dev`",
        ),
        (
            lambda: H.analyze_power("two_proportions", proportions=[0.1, 0.1], power=0.8),
            "no effect to detect",
        ),
        (
            lambda: H.analyze_power("two_proportions", proportions=[0.1, 1.5], power=0.8),
            "between 0 and 1",
        ),
        (lambda: H.analyze_power("independent_t", effect_size=0, power=0.8), "must be positive"),
        (lambda: H.analyze_power("independent_t", effect_size=0.5, power=1.5), "power must be"),
        (
            lambda: H.analyze_power("independent_t", effect_size=0.5, n=1, alpha=0.05),
            "greater than 1",
        ),
        (
            lambda: H.analyze_power("independent_t", effect_size=0.5, power=0.8, ratio=0),
            "ratio must be positive",
        ),
    ],
)
def test_bad_power_request_is_refused(call, message: str) -> None:
    with pytest.raises(H.AskanceError, match=re.escape(message)):
        call()


def test_catalog_lists_the_power_designs() -> None:
    catalog = H.list_tests()
    assert {d["id"] for d in catalog["power_designs"]} == set(H.POWER_DESIGNS)
    for entry in catalog["power_designs"]:
        assert entry["effect_size_metric"] and entry["n_is"]


# -- catalog integrity -----------------------------------------------------


def test_every_advertised_test_is_callable() -> None:
    catalog = H.list_tests()
    advertised = {t["id"] for t in catalog["tests"]}
    assert advertised == set(H.TESTS)
    for entry in catalog["tests"]:
        assert entry["tool"] in {"test_samples", "test_contingency", "test_binomial"}
        assert entry["assumptions"] and entry["null_hypothesis"] and entry["summary"]
    assert {m["id"] for m in catalog["correction_methods"]} == set(H.CORRECTION_METHODS)


def test_readme_documents_exactly_the_supported_ids() -> None:
    """Keep the documented IDs in sync with the runtime catalogs."""
    readme = (ROOT / "README.md").read_text()
    supported = set(H.TESTS) | set(H.CORRECTION_METHODS) | set(H.POWER_DESIGNS)
    for name in supported:
        assert f"`{name}`" in readme, f"README does not document {name}"
    documented = set(re.findall(r"`([a-z0-9_]+)`", readme))
    for stale in documented - supported:
        assert not stale.endswith("_test"), f"README cites a test id that no longer exists: {stale}"


def test_readme_example_matches_scipy() -> None:
    readme = (ROOT / "README.md").read_text()
    result = H.run_samples_test(
        "independent_t",
        [[2.1, 3.4, 1.9, 5.6, 4.2], [4.5, 5.1, 3.9, 6.2, 5.8]],
    )
    for key in ("statistic", "p_value", "decision", "degrees_of_freedom"):
        assert f'"{key}": {json.dumps(result[key])}' in readme


# -- the MCP surface -------------------------------------------------------


@pytest.mark.anyio
async def test_tools_are_discoverable_and_read_only() -> None:
    async with Client(mcp) as client:
        tools = {t.name: t for t in (await client.list_tools()).tools}
    assert set(tools) == {
        "list_tests",
        "test_samples",
        "test_contingency",
        "test_binomial",
        "adjust_p_values",
        "analyze_power",
    }
    for tool in tools.values():
        assert tool.annotations is not None, f"{tool.name} has no annotations"
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.description
    enum = tools["test_samples"].input_schema["properties"]["test"]["enum"]
    assert enum == [t for t, s in H.TESTS.items() if s["tool"] == "test_samples"]


@pytest.mark.anyio
async def test_a_call_returns_structured_and_text_content() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "test_samples", {"test": "independent_t", "samples": [A, B]}
        )
    assert not result.is_error
    assert result.structured_content["decision"] == "reject_null"
    assert result.structured_content["p_value"] == pytest.approx(
        float(stats.ttest_ind(A, B, equal_var=False).pvalue)
    )
    assert json.loads(result.content[0].text) == result.structured_content


@pytest.mark.anyio
async def test_an_invalid_call_explains_itself_to_the_caller() -> None:
    async with Client(mcp) as client:
        result = await client.call_tool("test_samples", {"test": "paired_t", "samples": [A, B[:3]]})
    assert result.is_error
    assert "same length" in result.content[0].text


@pytest.mark.anyio
async def test_the_installed_command_serves_from_a_stripped_environment() -> None:
    """The installed command must not depend on an activated environment or checkout path."""
    command = Path(sys.executable).parent / "askance"
    if not command.exists():  # pragma: no cover - depends on the local install
        pytest.skip("askance is not installed in this environment")
    server = StdioServerParameters(
        command=str(command),
        args=[],
        cwd=tempfile.gettempdir(),
        env={"PATH": "/usr/bin:/bin", "HOME": os.path.expanduser("~")},
    )
    async with Client(server) as client:
        tools = {t.name for t in (await client.list_tools()).tools}
        result = await client.call_tool("test_binomial", {"successes": 7, "trials": 20})
    assert len(tools) == 6
    assert result.structured_content["p_value"] == pytest.approx(
        float(stats.binomtest(7, 20, 0.5).pvalue)
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


if __name__ == "__main__":  # pragma: no cover
    sys.exit(pytest.main([__file__, "-q"]))
