---
name: askance
description: >
  Run a real statistical test instead of eyeballing numbers or recalling a
  plausible p-value. Use whenever a question turns on whether an observed
  difference is real rather than noise: A/B or experiment results,
  before-and-after comparisons, benchmark and latency numbers, conversion or
  error rates, survey answers, or two groups of measurements — including when
  the user never says "statistics", "significance", or "p-value" and only asks
  whether something improved, whether a change helped, whether one option is
  faster or better, or whether a difference could be chance. Also use when
  several comparisons need their p-values corrected, or to size an experiment
  before running it — "how many users do I need to detect this?". Skip it when
  nothing is being compared or planned: summary statistics, plotting, a lone
  reading against a threshold, or writing prose that merely cites numbers.
license: MIT
compatibility: Requires the askance MCP server (https://github.com/jmbr/askance) configured in the client.
---

# Decide whether a difference is real

Call the askance MCP server. Do not compute, estimate, or recall a p-value
yourself: a number that looks like a statistic but was never computed is worse
than no number, because it will be believed.

Askance runs the test through SciPy and statsmodels and reports which function
it called. Your job is choosing the right test, getting the data into it, and
reporting the result honestly.

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
| Two independent groups, skewed or ordinal or small | `mann_whitney_u` |
| The same subjects measured twice | `paired_t` |
| The same subjects twice, skewed or ordinal | `wilcoxon_signed_rank` |
| Three or more independent groups | `one_way_anova` |
| Three or more groups, skewed or ordinal | `kruskal_wallis` |
| Two numeric variables, straight-line relationship | `pearson_correlation` |
| Two numeric variables, ranks or a curve | `spearman_correlation` |
| Counts in a category table | `chi_square_independence` |
| A 2x2 table with small counts | `fisher_exact` |
| Successes out of trials, against a known rate | `binomial_exact` |

Paired beats independent whenever the measurements are genuinely linked — the
same server before and after a change, the same user under two conditions.
Treating paired data as independent throws away the pairing and usually hides a
real effect.

`independent_t` defaults to Welch's test, which does not assume equal
variances. Keep that default unless you have a specific reason.

## Before the experiment: how many do I need?

`analyze_power` answers the question that comes *before* a test. Give any three
of effect size, sample size, alpha and power; the fourth is solved for.

Callers almost never know a standardized effect size, so pass what they
actually said instead:

| They said | Pass |
|---|---|
| "we convert at 10%, we want to catch 12%" | `design: two_proportions`, `proportions: [0.10, 0.12]` |
| "we care about a 20ms improvement, spread is about 40ms" | `design: independent_t`, `difference: 20`, `std_dev: 40` |

Designs: `one_sample_t`, `paired_t`, `independent_t`, `two_proportions`,
`one_way_anova` and `chi_square` (the last two need `groups`).

Read `n_is` in the result before quoting the number. For the two-group designs
it counts **one group**, so the study needs roughly twice that in total.
Sample sizes are rounded up, because rounding down under-powers the study.

Expect the honest answer to be uncomfortable: detecting a 10% to 12% shift
needs about 3,800 per arm. Report that plainly rather than softening it — a
study too small to see the effect is the thing this call exists to prevent.

## Reporting the result

Give the p-value, the decision, and the test you used. Then the honest part:

- **`fail_to_reject` does not mean "no difference."** It means the data were
  not decisive. A small sample looks exactly like this. Say so, rather than
  reporting "no effect."
- **A p-value is not an effect size.** With enough data, a difference too small
  to matter still gets a tiny p-value. Quote the group means alongside it, and
  say whether the difference is big enough to act on.
- **`decision: null`** means the backend could not define a p-value, usually
  from constant input. Report that, do not fill the gap.
- **Assumptions are never checked for you.** Askance reports what a test
  assumes; whether it holds is a judgment you have to state.

## Gotchas

- **Askance cannot read files.** It takes inline numbers only. Read the CSV or
  log yourself, extract the values, then pass them.
- **`samples` is always a list of lists**, even for one group: `[[1.2, 3.4]]`.
- **Clients rename the tools.** Copilot exposes `askance-test_samples`; Pi's
  adapter exposes `askance_test_samples`. Same tool.
- **Paired tests need matching order.** Element *i* of each sample must be the
  same subject. Never sort one side.
- **Missing and non-finite values are refused by design.** Decide what to do
  with them, do it explicitly, and say what you did in the report.
- **Never run several tests and quote the smallest p-value.** Choosing a test
  after seeing its result invalidates it. Pick from the data's shape, in step 2,
  before you look.
- **Askance has no equivalence tests (TOST)** and reports no effect sizes for
  the tests themselves, and there is no power analysis for the rank-based tests
  or the correlations. Say so plainly rather than improvising a calculation.
- Counts must be whole numbers, not percentages or rates.

## Worked example

Deploy latency, 8 servers before and after, same machines:

```text
askance-test_samples
  test: "paired_t"
  samples: [[212, 198, 225, 240, 201, 233, 219, 208],
            [190, 185, 201, 219, 188, 207, 196, 191]]
```

Reported as: paired t-test, t = 11.31, p = 0.0000094 — the latency drop of
about 19.9 ms is very unlikely to be chance. Paired because the same servers
were measured twice.
