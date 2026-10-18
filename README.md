# Askance — hypothesis testing for coding agents

Askance is an MCP server for common statistical tests. SciPy and statsmodels perform the
calculations; Askance validates the inputs and reports the backend, options, and versions used.

Askance does not choose a test, claim that assumptions hold, or treat a large p-value as
evidence that the null hypothesis is true.

## Install

Requires Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), and git.

```bash
uv tool install git+https://git.superadditive.com/jmbr/askance
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

The server exposes statistical operations. The skill in this repository teaches an agent when
to use them, so a question such as "did the change help?" calls Askance instead of relying on
visual inspection.

The installed package does not include the skill. Run these commands from a clone
(`git clone https://git.superadditive.com/jmbr/askance`), and keep the clone: the links point
into it.

```bash
mkdir -p ~/.agents/skills ~/.pi/agent/skills
ln -s "$PWD/skills/askance" ~/.agents/skills/askance        # Copilot CLI
ln -s ../../../.agents/skills/askance ~/.pi/agent/skills/   # Pi, through the link above
```

The skill follows the [Agent Skills spec](https://agentskills.io/specification).

## Tools

Six read-only tools cover t-tests, rank-based tests, one-way ANOVA, correlation, contingency
tables, the exact binomial test, multiple-testing corrections, and sample-size and power
analysis. [docs/REFERENCE.md](docs/REFERENCE.md) lists every tool and test with its inputs,
and explains how to read a result.

## Example

Call `test_samples`:

```json
{"test": "independent_t", "samples": [[2.1, 3.4, 1.9, 5.6, 4.2], [4.5, 5.1, 3.9, 6.2, 5.8]]}
```

Selected result fields:

```json
{
  "test": "independent_t",
  "null_hypothesis": "The two population means are equal.",
  "statistic": -2.065981019092757,
  "p_value": 0.08001624746364379,
  "alpha": 0.05,
  "decision": "fail_to_reject",
  "alternative": "two-sided",
  "sample_sizes": [5, 5],
  "degrees_of_freedom": 6.61351768277725,
  "method": {
    "function": "scipy.stats.ttest_ind",
    "options": {"equal_var": false, "alternative": "two-sided"}
  },
  "warnings": []
}
```

Every result identifies the backend function and options that produced it.

## Not included

Proportion z-tests, equivalence/TOST, effect sizes for the tests, post-hoc pairwise
comparisons, normality and variance diagnostics, permutation and bootstrap methods,
regression and model diagnostics, and survival analysis. Power analysis covers only the designs
listed in [docs/REFERENCE.md](docs/REFERENCE.md#planning-an-experiment). There is none for
`binomial_exact`, the rank-based tests, or the correlations, and none for one-sided tests.
Askance does not approximate unsupported power analyses. Open an issue if you need something
here.

## Development

[AGENTS.md](AGENTS.md) covers the checks, the invariants every change must preserve, and the
release process.

## Compatibility

Askance has been tested with GitHub Copilot CLI and with Pi through pi-mcp-adapter. In both
clients the same call returns the same p-value as a direct SciPy call, to the last digit.
[docs/COMPATIBILITY.md](docs/COMPATIBILITY.md) lists the versions, what was run, and what
was not tested.

## License

MIT; see [LICENSE](LICENSE).
