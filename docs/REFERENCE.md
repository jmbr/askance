# Askance reference

This page describes Askance's six tools: the tests, corrections, and power designs they
accept, how to read a result, and which inputs they refuse. The [README](../README.md)
covers installation and client setup.

## Tools

| Tool | What it does |
|---|---|
| `list_tests` | Every test, correction, and power design, with its inputs and assumptions |
| `test_samples` | Tests on raw observations |
| `test_contingency` | Tests on a table of counts |
| `test_binomial` | Exact test on a count of successes |
| `adjust_p_values` | Multiple-testing correction for a family of p-values |
| `analyze_power` | Sample size and power, for planning an experiment before it runs |

All six are read-only and compute from their arguments alone.

### Tests

Samples are always a list of lists, so a one-sample test takes `[[...]]`.

| Test id | Question | Input |
|---|---|---|
| `one_sample_t` | Does a mean differ from a reference value? | one sample + `reference` |
| `independent_t` | Do two independent groups differ in mean? | two samples |
| `paired_t` | Is the mean paired difference non-zero? | two equal-length samples |
| `mann_whitney_u` | Do two independent samples share a distribution? | two samples |
| `wilcoxon_signed_rank` | Are paired differences centered on zero? | two equal-length samples |
| `one_way_anova` | Do several groups share a mean? | two or more samples |
| `kruskal_wallis` | Do several groups share a distribution? | two or more samples |
| `pearson_correlation` | Is there a linear association? | two equal-length samples |
| `spearman_correlation` | Is there a monotonic association? | two equal-length samples |
| `chi_square_independence` | Are row and column variables independent? | an r x c table |
| `fisher_exact` | Is a 2x2 table consistent with odds ratio 1? | a 2x2 table |
| `binomial_exact` | Does a success rate differ from a reference? | successes and trials |

`independent_t` uses Welch's test by default. Pass `equal_var: true` for Student's pooled
test, which additionally assumes equal variances.

`one_sample_t`, `independent_t`, `paired_t`, `mann_whitney_u`, `wilcoxon_signed_rank`,
`pearson_correlation`, `spearman_correlation`, `fisher_exact`, and `binomial_exact` accept
`alternative` as `two-sided` (the default), `less`, or `greater`. The omnibus tests
`one_way_anova`, `kruskal_wallis`, and `chi_square_independence` are two-sided only.

### Corrections

Run a family of tests and some will look significant by chance. `adjust_p_values` corrects
for that; it does not rerun anything.

| Method | Controls | Dependence between tests |
|---|---|---|
| `bonferroni` | Family-wise error rate, single step | Any |
| `sidak` | Family-wise error rate, single step | Independent or positively dependent |
| `holm` | Family-wise error rate, step-down | Any |
| `holm-sidak` | Family-wise error rate, step-down | Independent or positively dependent |
| `fdr_bh` | False discovery rate (Benjamini-Hochberg) | Independent or positively dependent |
| `fdr_by` | False discovery rate (Benjamini-Yekutieli) | Any |

## Planning an experiment

Use `analyze_power` before collecting data. Provide any three of effect size, `n`, `alpha`,
and `power`; Askance solves for the fourth.

Supported designs are `one_sample_t`, `paired_t`, `independent_t`, `two_proportions`,
`one_way_anova`, and `chi_square`. `one_way_anova` also needs `groups`; `chi_square` sizes
`chi_square_independence` and needs the `rows` and `columns` of its table.

```json
{"design": "two_proportions", "proportions": [0.10, 0.12], "power": 0.8}
```

```json
{
  "design": "two_proportions",
  "solved_for": "n",
  "n": 3835,
  "n_exact": 3834.595739884031,
  "n_second_group": 3835,
  "n_is": "observations in the first group",
  "effect_size": 0.06398210298605855,
  "effect_size_metric": "Cohen's h",
  "power": 0.8,
  "alpha": 0.05
}
```

If you do not know the standardized effect size, pass the underlying quantities: two
`proportions` for rates, or a `difference` and expected `std_dev` for a t-test design. For
`paired_t`, both describe the paired differences.

Read `n_is` before quoting the number. For two-group designs, `n` counts the first group and
`n_second_group` the second. Sample sizes are rounded up, since rounding down under-powers the
study; `one_way_anova` rounds its total up to a multiple of `groups`, so the groups can be
equal.

The t-test designs and `two_proportions` size two-sided tests. `two_proportions` sizes the
uncorrected comparison, which is `chi_square_independence` on a 2x2 table with
`correction: false`. Yates' correction (the default) and `fisher_exact` are more conservative,
so the same `n` gives them less power.

## Reading a result

- `decision` is `reject_null` when `p_value < alpha`, otherwise `fail_to_reject`.
  **`fail_to_reject` is not evidence that the null hypothesis is true.** It means the data
  were not decisive; limited sample size is one possible reason.
- A p-value is not an effect size. A tiny p-value from a large sample can accompany a
  difference too small to care about. Look at the data, not only the verdict.
- `alpha` is a threshold you chose, not a property of the data.
- `decision` is `null` when the backend could not define a p-value, typically from constant
  input. `warnings` explains why the result is undefined.
- A statistic JSON cannot represent, such as the infinite odds ratio of a table with a zero
  cell, is reported as `null`, and `warnings` gives the backend's value.
- `degrees_of_freedom` appears only when the backend reports it: for the t-tests and
  `chi_square_independence`.
- For `binomial_exact`, the confidence interval is Clopper-Pearson. It does not invert SciPy's
  two-sided p-value, so near `alpha` the two can disagree; `warnings` says when they do.
- The assumptions in `list_tests` are never checked for you. Askance reports what a test
  assumes; deciding whether that holds is your job.
- Choosing among tests after comparing their p-values introduces selection bias. Choose the
  test from the study design and question before inspecting its result.

## Input rules

- Pass raw observations, not means or summaries.
- Missing, `NaN`, and infinite values are refused. Decide how to handle them before calling;
  dropping them silently would change the analysis without saying so.
- Contingency tables take non-negative integer counts, not proportions. A test of association
  needs at least two rows and two columns, and every row and column needs at least one count.
- Booleans and numbers sent as strings are refused where a number is expected, and counts must
  be integers: `8`, not `8.0`.
