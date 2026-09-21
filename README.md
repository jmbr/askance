# Askance — hypothesis testing for coding agents

An MCP server that runs common statistical tests. SciPy and statsmodels do the arithmetic;
Askance checks the inputs, reports what was actually run, and tells the agent what the result
does and does not mean.

It will not choose a test for you, will not claim an assumption holds, and will not report a
large p-value as evidence that nothing is going on.

## Install

Requires Python 3.12 or newer.

```bash
uv tool install git+http://localhost:3000/jmbr/askance
command -v askance      # the absolute path used below
```

From a clone, `uv tool install .` works the same way.

## Connect an agent

Both clients below read the same file. Use the absolute path from `command -v askance`, so the
server starts without an activated virtualenv and from any directory.

```json
{
  "mcpServers": {
    "askance": {
      "command": "/home/you/.local/bin/askance",
      "args": []
    }
  }
}
```

| Client | Where the file goes |
|---|---|
| GitHub Copilot CLI | `.mcp.json` in the project, or `~/.copilot/mcp-config.json` |
| Pi | `.mcp.json` in the project, or `~/.config/mcp/mcp.json` |

Copilot CLI can write the entry for you, which avoids a trust prompt for project files:

```bash
copilot mcp add askance -- /home/you/.local/bin/askance
```

Pi has no built-in MCP support; it needs the [pi-mcp-adapter](https://github.com/nicobailon/pi-mcp-adapter)
extension (`pi install npm:pi-mcp-adapter`), which reads the same file and prefixes the tool
names with the server name.

## Optional: the skill

The server gives an agent the tests. The bundled skill teaches it *when* to reach for them,
so "did the change help?" runs a real test instead of getting an eyeballed answer.

```bash
ln -s "$PWD/skills/askance" ~/.agents/skills/askance        # Copilot CLI
ln -s ../../../.agents/skills/askance ~/.pi/agent/skills/   # Pi
```

It follows the [Agent Skills spec](https://agentskills.io/specification), so
`skills-ref validate skills/askance` checks it. `tests/skill_trigger_eval.sh` checks the part
that actually matters: that it fires on real questions and stays quiet on near misses.

## Tools

| Tool | What it does |
|---|---|
| `list_tests` | Every test and correction, with its question, null hypothesis, input, and assumptions |
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

| Method | Controls |
|---|---|
| `bonferroni` | Family-wise error rate, single step |
| `sidak` | Family-wise error rate, single step |
| `holm` | Family-wise error rate, step down |
| `holm-sidak` | Family-wise error rate, step down |
| `fdr_bh` | False discovery rate (Benjamini-Hochberg) |
| `fdr_by` | False discovery rate under dependence (Benjamini-Yekutieli) |

## Example

Call `test_samples`:

```json
{"test": "independent_t", "samples": [[2.1, 3.4, 1.9, 5.6, 4.2], [4.5, 5.1, 3.9, 6.2, 5.8]]}
```

Result:

```json
{
  "test": "independent_t",
  "null_hypothesis": "The two population means are equal.",
  "statistic": -2.6607,
  "p_value": 0.0298,
  "alpha": 0.05,
  "decision": "reject_null",
  "alternative": "two-sided",
  "sample_sizes": [5, 5],
  "degrees_of_freedom": 7.7238,
  "method": {
    "function": "scipy.stats.ttest_ind",
    "options": {"equal_var": false, "alternative": "two-sided"}
  },
  "versions": {"askance": "0.2.0", "scipy": "1.18.1"},
  "warnings": []
}
```

Every result carries the backend function and options it used, so a number can be traced back
to the call that produced it.

## Planning an experiment

`analyze_power` answers the question that comes before a test. Give any three of effect
size, `n`, `alpha` and `power`; the fourth is solved for.

```json
{"design": "two_proportions", "proportions": [0.10, 0.12], "power": 0.8}
```

```json
{"design": "two_proportions", "solved_for": "n", "n": 3835, "n_exact": 3834.59,
 "n_is": "observations in the first group", "effect_size": 0.0639,
 "effect_size_metric": "Cohen's h", "power": 0.8, "alpha": 0.05}
```

You rarely know a standardized effect size, so pass what you actually mean: two
`proportions` for rates, or a `difference` and the `std_dev` you expect for the t designs.

Read `n_is` before quoting the number — for two-group designs it counts *one* group.
Sample sizes are rounded up, since rounding down under-powers the study.

## Reading a result

- `decision` is `reject_null` when `p_value < alpha`, otherwise `fail_to_reject`.
  **`fail_to_reject` is not evidence that the null hypothesis is true.** It means the data
  were not decisive, which is also what a small sample looks like.
- A p-value is not an effect size. A tiny p-value from a large sample can accompany a
  difference too small to care about. Look at the data, not only the verdict.
- `alpha` is a threshold you chose, not a property of the data.
- `decision` is `null` when the backend could not define a p-value, typically from constant
  input. `warnings` says so rather than inventing an answer.
- The assumptions in `list_tests` are never checked for you. Askance reports what a test
  assumes; deciding whether that holds is your job.
- Choosing a test after seeing which one gives the smallest p-value invalidates the p-value.
  Pick the test from the question you are asking.

## Input rules

- Pass raw observations, not means or summaries.
- Missing, `NaN`, and infinite values are refused. Decide how to handle them before calling;
  dropping them silently would change the analysis without saying so.
- Contingency tables take non-negative integer counts, not proportions.
- Booleans are refused where a number is expected.

## Not included

Proportion z-tests, equivalence/TOST, effect sizes for the tests, post-hoc pairwise
comparisons, normality and variance diagnostics, permutation and bootstrap methods,
regression and model diagnostics, and survival analysis. Power analysis covers the
parametric designs only — there is none for the rank-based tests or the correlations,
because statsmodels has no solver for them and approximating one would be inventing
statistics. Open an issue if you need something here.

## Development

`nox` runs the whole thing on every supported Python:

```bash
uvx nox              # tests on 3.12 and 3.13, then lint and skill validation
uvx nox -s tests     # just the tests
uvx nox -s lint      # ruff check and ruff format --check
uvx nox -s format    # the same, fixing what ruff can fix
uvx nox -s skills    # validate skills/ with skills-ref
uvx nox -s tests -- -k binomial   # arguments after -- go to pytest
```

Or work in the checkout directly:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check
```

After changing the source, reinstall the tool with `uv tool install . --reinstall`. Plain
`--force` replaces the executable but reuses a wheel cached against the unchanged version,
so an agent keeps talking to the old server.

Versions are not set by hand. python-semantic-release reads the commit history on each push
to `main`: `feat:` is a minor bump, `fix:` a patch one, and everything else releases
nothing. `CHANGELOG.md`, the tag and `project.version` are generated output. See
[AGENTS.md](AGENTS.md#releases).

[prek](https://github.com/j178/prek) runs those same nox sessions as git hooks, so the
hooks and `nox` cannot disagree: formatting and skill validation on every commit, the
test suite on every push. It also scans staged changes for secrets with
[betterleaks](https://github.com/betterleaks/betterleaks).

```bash
prek install          # once per clone
prek run --all-files  # check everything now
```

The suite compares every test against a direct SciPy or statsmodels call, and starts the
installed executable from an unrelated directory with no virtualenv, which is how an agent
starts it. Under nox that executable comes from a freshly built wheel, so a packaging
mistake fails the suite.

## Tested against

| Component | Version |
|---|---|
| Python | 3.13.5 |
| MCP Python SDK | 2.2.0 |
| SciPy | 1.18.1 |
| statsmodels | 0.15.0 |
| GitHub Copilot CLI | 1.0.84-1 |
| Pi + pi-mcp-adapter | 0.85.1 + 2.34.0 |

In both clients the same call returns the same p-value as a direct SciPy call, to the last
digit. See [docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) for what was run and what was not.

## License

MIT; see [LICENSE](LICENSE).
