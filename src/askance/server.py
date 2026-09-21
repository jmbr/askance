"""MCP tools that delegate to `askance.hypothesis`."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.types import ToolAnnotations
from pydantic import Field

from askance import hypothesis as H

READ_ONLY = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

# Deriving these types from the catalogs keeps the MCP schemas in sync with dispatch.
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
        "Hypothesis testing and power analysis backed by SciPy and statsmodels. Call "
        "`list_tests` before choosing a test or power design. Pass raw observations, not "
        "summaries, and handle missing values before calling. `fail_to_reject` means the "
        "data were not decisive; it does not establish the null hypothesis. Use "
        "`adjust_p_values` for a family of related tests."
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
    return H.run_binomial_test(successes, trials, probability, alternative, alpha)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Correct a family of p-values for multiple testing and return them in the original "
        "order. Family-wise methods (bonferroni, sidak, holm, holm-sidak) control the chance "
        "of one or more false rejections. False-discovery-rate methods (fdr_bh, fdr_by) "
        "control the expected proportion of false discoveries. This tool does not rerun the "
        "tests."
    ),
)
def adjust_p_values(
    p_values: Annotated[
        list[float], Field(description="The uncorrected p-values of one family of tests.")
    ],
    method: Method,
    alpha: Alpha = 0.05,
) -> dict[str, Any]:
    return H.adjust_p_values(p_values, method, alpha)


@mcp.tool(
    annotations=READ_ONLY,
    description=(
        "Plan sample size or statistical power before collecting data. Leave one of effect "
        "size, n, alpha, or power unspecified; Askance solves for it. For two_proportions, "
        "you may pass two rates instead of Cohen's h. For t-test designs, you may pass a "
        "difference and expected standard deviation instead of Cohen's d. This tool does "
        "not test observed data."
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
        Field(description="Probability of detecting the effect; 0.8 is a common target."),
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
    return H.analyze_power(
        design, effect_size, n, alpha, power, ratio, groups, proportions, difference, std_dev
    )


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
