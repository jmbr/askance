"""The MCP server: five read-only tools over the statistical core.

This module only translates MCP calls into `askance.hypothesis` calls. It holds no
statistical logic and no second copy of the test catalog, so the tools cannot advertise a
test that does not exist.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from askance import hypothesis as H

# Every tool computes a result from its arguments and touches nothing else.
READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Derived from the catalog so a test cannot appear in a schema without being callable.
SampleTest = Literal[tuple(t for t, s in H.TESTS.items() if s["tool"] == "test_samples")]  # type: ignore[valid-type]
ContingencyTest = Literal[tuple(t for t, s in H.TESTS.items() if s["tool"] == "test_contingency")]  # type: ignore[valid-type]
Method = Literal[tuple(H.CORRECTION_METHODS)]  # type: ignore[valid-type]
Design = Literal[tuple(H.POWER_DESIGNS)]  # type: ignore[valid-type]
Alternative = Literal[H.ALTERNATIVES]  # type: ignore[valid-type]

Alpha = Annotated[float, Field(gt=0, lt=1, description="Significance level.")]

mcp = MCPServer(
    name="askance",
    title="Askance",
    version=H.version("askance"),
    instructions=(
        "Hypothesis testing backed by SciPy and statsmodels. Call `list_tests` first to "
        "choose a test and see what it assumes: Askance never picks a test for you. Pass "
        "raw observations, not summaries, and clean missing values beforehand. A result of "
        "`fail_to_reject` means the data were not decisive, never that the null hypothesis "
        "is true. Use `adjust_p_values` whenever you run a family of related tests."
    ),
)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "List every hypothesis test and p-value correction this server supports, with the "
        "question each one answers, its null hypothesis, the input it needs, and its "
        "assumptions. Call this before running a test."
    ),
)
def list_tests() -> dict[str, Any]:
    """The catalog of supported tests and corrections."""
    return H.list_tests()


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Run a hypothesis test on one or more samples of raw numeric observations: "
        "one_sample_t, independent_t, paired_t, mann_whitney_u, wilcoxon_signed_rank, "
        "one_way_anova, kruskal_wallis, pearson_correlation, spearman_correlation. "
        "Samples are always a list of lists, so a one-sample test takes [[...]]."
    ),
)
def test_samples(
    test: SampleTest,
    samples: Annotated[
        list[list[float]],
        Field(description="One list of raw observations per group, e.g. [[1.2, 3.4], [2.2, 5.1]]."),
    ],
    reference: Annotated[
        float | None, Field(description="The value to compare against; one_sample_t only.")
    ] = None,
    alternative: Alternative = "two-sided",
    equal_var: Annotated[
        bool,
        Field(description="independent_t only: pool the variances (Student) instead of Welch."),
    ] = False,
    alpha: Alpha = 0.05,
) -> dict[str, Any]:
    """Run a sample-based hypothesis test."""
    return H.run_samples_test(test, samples, reference, alternative, equal_var, alpha)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Test association in a table of counts: chi_square_independence for an r x c table, "
        "or fisher_exact for a 2x2 table, which stays valid with small counts."
    ),
)
def test_contingency(
    test: ContingencyTest,
    table: Annotated[
        list[list[int]],
        Field(description="Rows of non-negative integer counts, e.g. [[8, 2], [1, 5]]."),
    ],
    alternative: Alternative = "two-sided",
    correction: Annotated[
        bool,
        Field(description="chi_square_independence: apply Yates' correction to a 2x2 table."),
    ] = True,
    alpha: Alpha = 0.05,
) -> dict[str, Any]:
    """Run a test of association on a contingency table."""
    return H.run_contingency_test(test, table, alternative, correction, alpha)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Exact binomial test: does an observed number of successes differ from a reference "
        "success probability? Use this for counts rather than raw observations."
    ),
)
def test_binomial(
    successes: Annotated[int, Field(ge=0, description="Number of successes observed.")],
    trials: Annotated[int, Field(gt=0, description="Number of independent trials.")],
    probability: Annotated[
        float, Field(ge=0, le=1, description="Success probability under the null hypothesis.")
    ] = 0.5,
    alternative: Alternative = "two-sided",
    alpha: Alpha = 0.05,
) -> dict[str, Any]:
    """Run an exact binomial test."""
    return H.run_binomial_test(successes, trials, probability, alternative, alpha)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Correct a family of p-values for multiple testing and return them in the original "
        "order. Use a family-wise method (bonferroni, sidak, holm, holm-sidak) to control any "
        "false positive, or a false-discovery-rate method (fdr_bh, fdr_by) when some are "
        "tolerable. This does not rerun the tests."
    ),
)
def adjust_p_values(
    p_values: Annotated[
        list[float], Field(description="The uncorrected p-values of one family of tests.")
    ],
    method: Method,
    alpha: Alpha = 0.05,
) -> dict[str, Any]:
    """Apply a multiple-testing correction."""
    return H.adjust_p_values(p_values, method, alpha)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Sample size and statistical power, for planning an experiment before it runs. "
        "Give any three of effect size, sample size (n), alpha and power, and the fourth is "
        "solved for — most often n, to answer 'how many do I need?'. For two_proportions you "
        "can pass the two rates you care about (e.g. 0.10 and 0.12) instead of a standardized "
        "effect size; for the t designs, pass the difference you care about and the standard "
        "deviation you expect. This plans an experiment; it does not test data."
    ),
)
def analyze_power(
    design: Design,
    effect_size: Annotated[
        float | None,
        Field(description="Standardized effect (Cohen's d, h, f or w). Omit to solve for it."),
    ] = None,
    n: Annotated[
        float | None,
        Field(description="Sample size; see n_is in the result for what it counts."),
    ] = None,
    alpha: Annotated[
        float | None, Field(description="Significance level. Omit to solve for it.")
    ] = 0.05,
    power: Annotated[
        float | None,
        Field(description="Probability of detecting the effect; 0.8 is conventional."),
    ] = None,
    ratio: Annotated[
        float, Field(description="Second group size divided by the first; two-group designs.")
    ] = 1.0,
    groups: Annotated[
        int | None,
        Field(description="Groups (one_way_anova) or categories (chi_square)."),
    ] = None,
    proportions: Annotated[
        list[float] | None,
        Field(description="two_proportions: the two rates, e.g. [0.10, 0.12]."),
    ] = None,
    difference: Annotated[
        float | None, Field(description="t designs: the difference worth detecting.")
    ] = None,
    std_dev: Annotated[
        float | None, Field(description="t designs: the standard deviation you expect.")
    ] = None,
) -> dict[str, Any]:
    """Solve a power or sample-size question."""
    return H.analyze_power(
        design, effect_size, n, alpha, power, ratio, groups, proportions, difference, std_dev
    )


def main() -> None:
    """Serve over stdio. Protocol frames go to stdout; anything else must go to stderr."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
