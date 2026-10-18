---
name: askance
description: >
  Use Askance whenever a user needs to know whether an observed difference is
  larger than random variation. Trigger for A/B tests, experiments,
  before-and-after comparisons, benchmarks, latency, conversion or error
  rates, surveys, and comparisons between groups — even when the user asks
  only whether something improved, helped, became faster, or could be chance.
  Also use it to correct a family of p-values or size a planned experiment.
  Do not use it for summary statistics, plotting, a single reading against a
  threshold, or prose that merely cites numbers.
license: MIT
compatibility: Requires the askance MCP server (https://git.superadditive.com/jmbr/askance) configured in the client.
---

# Run a statistical comparison

Call the Askance MCP server. Never supply a p-value from inspection or memory.

Askance delegates calculations to SciPy and statsmodels and reports the backend
function used. Choose the test from the study design, prepare the data, and
report the result with its limitations.

## Workflow

1. **State the comparison** in one line: which groups, which measurement, what
   would count as a difference. Do this before looking at any p-value.
2. **Choose the test** from the shape of the data (table below). If unsure,
   call `list_tests` — it reports what each test assumes.
3. **Run it.** Pass raw observations, never summaries.
4. **Correct if you ran several.** Any family of related comparisons needs
   `adjust_p_values`.
5. **Report** the p-value, the decision, and what it does not mean.

## Choosing a test

| The data you have | Test |
|---|---|
| One group, compared with a target number | `one_sample_t` |
| Two independent groups | `independent_t` |
| Two independent groups with ordinal or strongly skewed data | `mann_whitney_u` |
| The same subjects measured twice | `paired_t` |
| The same subjects twice, skewed or ordinal | `wilcoxon_signed_rank` |
| Three or more independent groups | `one_way_anova` |
| Three or more groups with ordinal or strongly skewed data | `kruskal_wallis` |
| Two numeric variables, straight-line relationship | `pearson_correlation` |
| Two numeric variables with a monotonic or ordinal relationship | `spearman_correlation` |
| Counts in a category table | `chi_square_independence` |
| A 2x2 table with small counts | `fisher_exact` |
| Successes out of trials, against a known rate | `binomial_exact` |

Use a paired test when measurements are linked, such as the same server before
and after a change or the same user under two conditions. Treating paired data
as independent discards information and can reduce statistical power.

`independent_t` defaults to Welch's test, which does not assume equal
variances. Keep that default unless you have a specific reason.

## Before the experiment: how many do I need?

`analyze_power` answers the question that comes *before* a test. Give any three
of effect size, sample size, alpha and power; the fourth is solved for.

When the user provides an effect in original units rather than a standardized
effect size, pass those quantities directly:

| They said | Pass |
|---|---|
| "we convert at 10%, we want to catch 12%" | `design: two_proportions`, `proportions: [0.10, 0.12]` |
| "we care about a 20ms improvement, spread is about 40ms" | `design: independent_t`, `difference: 20`, `std_dev: 40` |

Designs: `one_sample_t`, `paired_t`, `independent_t`, `two_proportions`,
`one_way_anova` (needs `groups`) and `chi_square` (needs the table's `rows`
and `columns`).

Read `n_is` in the result before quoting the number. For the two-group designs
`n` counts the **first group** and `n_second_group` the second; add them for
the total. Sample sizes are rounded up, because rounding down under-powers the
study.

`two_proportions` sizes the 2x2 chi-square test without Yates' correction. With
the default correction, or with `fisher_exact`, the same n gives less power;
say so when reporting the plan.

For example, detecting a change from 10% to 12% conversion needs about 3,800
observations per arm. Report the required sample size directly.

## Reporting the result

Give the p-value, the decision, and the test used. Include these qualifications:

- **`fail_to_reject` does not mean "no difference."** It means the data were
  not decisive. Limited sample size is one possible reason.
- **A p-value is not an effect size.** With enough data, a difference too small
  to matter still gets a tiny p-value. Quote the group means alongside it, and
  say whether the difference is big enough to act on.
- **`decision: null`** means the backend could not define a p-value, usually
  from constant input. Report that, do not fill the gap.
- **Assumptions are never checked for you.** Askance reports what a test
  assumes; state whether the study design appears to satisfy them.

## Gotchas

- **Askance cannot read files.** It takes inline numbers only. Read the CSV or
  log yourself, extract the values, then pass them.
- **`samples` is always a list of lists**, even for one group: `[[1.2, 3.4]]`.
- **Clients rename the tools.** Copilot exposes `askance-test_samples`; Pi's
  adapter exposes `askance_test_samples`. Both names refer to the same tool.
- **Paired tests need matching order.** Element *i* of each sample must be the
  same subject. Never sort one side.
- **Missing and non-finite values are refused by design.** Decide what to do
  with them, do it explicitly, and say what you did in the report.
- **Never run several tests and quote the smallest p-value.** Choosing a test
  after seeing its result introduces selection bias. Choose the test in step 2,
  before inspecting the result.
- **Unsupported analyses:** Askance has no equivalence tests (TOST), does not
  report effect sizes for test results, and has no power solver for
  `binomial_exact`, rank-based tests, correlations, or one-sided tests. Do not
  approximate these analyses.
- **Counts are integers**, not percentages or rates.

## Worked example

Deploy latency, 8 servers before and after, same machines:

```text
askance-test_samples
  test: "paired_t"
  samples: [[212, 198, 225, 240, 201, 233, 219, 208],
            [190, 185, 201, 219, 188, 207, 196, 191]]
```

Report: paired t-test, t = 11.31, p = 0.0000094, mean reduction 19.9 ms. At
alpha 0.05, reject the null hypothesis of zero mean change. Use a paired test
because the same servers were measured twice.
