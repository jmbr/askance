# Compatibility

What was actually run against this release, and how. Anything not listed here is untested,
not unsupported: nobody has checked it.

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
| Power analysis (v0.2.0) | `analyze_power` sized a 10% -> 12% A/B test at 3,835 per arm, matching a direct `NormalIndPower` call |

A project-level `.mcp.json` is also supported, but Copilot CLI only loads it after the folder
is trusted. If the server does not appear, trust the folder or use the user-level
configuration above.

### Pi

Pi has no built-in MCP support. It was tested with the `pi-mcp-adapter` extension
(`pi install npm:pi-mcp-adapter`) reading a project `.mcp.json`.

| Check | Result |
|---|---|
| Discovery | `askance` reported with 5 tools |
| Tool call | Same `p_value` as Copilot CLI and SciPy, to the last digit |
| Invalid call | `Error executing tool test_samples: paired_t is paired, ...` |

The adapter exposes tools through its proxy by default and prefixes their names, so
`test_samples` is called as `askance_test_samples`. That is the adapter's naming, not
Askance's. The adapter's default `legacy` protocol negotiation was used.

The adapter's `directTools` mode was not tested.

## Not tested

Copilot cloud agent, Copilot code review, the Copilot SDK, VS Code, Streamable HTTP
deployment, and Windows or macOS. The server uses only the tools-only subset of MCP and
writes protocol frames to stdout alone, so nothing there is expected to be a problem, but
expectation is not a test result.
