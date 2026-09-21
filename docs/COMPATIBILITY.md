# Compatibility

This file records the client and dependency versions tested with each Askance release.
Features not listed here may work, but have not been tested.

## v0.2.0

| Component | Version |
|---|---|
| Python | 3.13.5 |
| MCP Python SDK (`mcp`) | 2.2.0 |
| SciPy | 1.18.1 |
| statsmodels | 0.15.0 |
| NumPy | 2.5.3 |
| GitHub Copilot CLI | 1.0.84-1 |
| Pi | 0.85.1 |
| pi-mcp-adapter | 2.34.0 |

Askance was installed with `uv tool install`, and both clients were pointed at the resulting
absolute path (`~/.local/bin/askance`). Nothing was added to `PATH` and no virtualenv was
activated.

### GitHub Copilot CLI

Registered with the documented command:

```bash
copilot mcp add askance -- /home/you/.local/bin/askance
```

| Check | Result |
|---|---|
| Server registered and enabled | `copilot mcp get askance` reports Status: Enabled |
| Tool call | `test_samples` / `independent_t` returned `p_value` 0.08001624746364379 |
| Matches the backend | Identical to `scipy.stats.ttest_ind(..., equal_var=False)` |
| Invalid call | `paired_t is paired, so every sample must have the same length, got [3, 2]` |
| Power analysis | `analyze_power` sized a 10% to 12% A/B test at 3,835 per arm, matching a direct `NormalIndPower` call |

A project-level `.mcp.json` is also supported, but Copilot CLI only loads it after the folder
is trusted. If the server does not appear, trust the folder or use the user-level
configuration above.

### Pi

Pi has no built-in MCP support. It was tested with the `pi-mcp-adapter` extension
(`pi install npm:pi-mcp-adapter`) reading a project `.mcp.json`.

| Check | Result |
|---|---|
| Discovery | `askance` reported with 6 tools |
| Tool call | Same `p_value` as Copilot CLI and SciPy, to the last digit |
| Invalid call | `Error executing tool test_samples: paired_t is paired, ...` |
| Power analysis | `analyze_power` sized a 10% to 12% A/B test at 3,835 observations per arm |

The adapter exposes tools through its proxy by default and prefixes each name with the
server name, so `test_samples` becomes `askance_test_samples`. The adapter's default
`legacy` protocol negotiation was used.

The adapter's `directTools` mode was not tested.

## Not tested

Copilot cloud agent, Copilot code review, the Copilot SDK, VS Code, Streamable HTTP,
Windows, and macOS. Askance exposes MCP tools only and writes protocol frames to stdout,
but those properties do not replace client-specific testing.
