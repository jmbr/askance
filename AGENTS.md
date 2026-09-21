# AGENTS.md

Askance is an MCP server that runs hypothesis tests through SciPy and statsmodels. It
exists because a number that looks like a statistic but was never computed will be
believed. So the rule behind every other rule here is: **report what a backend computed,
and nothing it did not.**

## Layout

| Path | What lives there |
|---|---|
| `src/askance/hypothesis.py` | The statistical core: the `TESTS` catalog, validation, dispatch, result shape |
| `src/askance/server.py` | MCP translation only. No statistical logic, no second copy of the catalog |
| `tests/test_askance.py` | The whole pytest suite, including the real-subprocess install test |
| `tests/skill_trigger_eval.sh` | Does the skill fire on the right prompts? Drives an agent CLI, so pytest does not run it |
| `skills/askance/SKILL.md` | The Agent Skill that routes statistics questions to the server |
| `noxfile.py` | Every check, defined once |

## Checks

```bash
uvx nox                            # tests on 3.12 and 3.13, lint, skill validation
uvx nox -s format                  # fix whatever ruff can fix
uvx nox -s tests -- -k binomial    # arguments after -- go to pytest
```

`prek install` wires those same sessions to git hooks: formatting, skill validation and
secret scanning on commit, the full suite on push.

Do not add a check to `.pre-commit-config.yaml` that could be a nox session. Define it in
`noxfile.py` and have the hook call it, so a hook and a local `nox` run cannot disagree.
Hooks for things nox cannot own (file hygiene, `uv.lock`, the betterleaks Go binary) stay
upstream and pinned.

## Invariants

Breaking any of these defeats the point of the project.

- **Never compute, estimate, or hardcode a statistic.** Every number comes from SciPy or
  statsmodels, and `method.function` names the call that produced it.
- **Never choose a test for the caller.** `list_tests` describes the options; the caller
  decides. Nothing may rank tests or pick a default "best" one.
- **Assumptions are reported, never checked.** Do not add code that claims an assumption
  holds.
- **An undefined p-value is reported, not filled in.** `decision` becomes `null` and a
  warning says why. Never substitute a fallback value.
- **`fail_to_reject` never means "no difference."** Keep that claim out of code, prose,
  tool descriptions, and the skill.
- **Refuse bad input instead of repairing it.** Missing, infinite, and non-numeric values
  raise `AskanceError`; booleans are not numbers; counts are integers. Silently dropping
  a value changes the answer without telling anyone.
- **stdout belongs to the MCP protocol.** Diagnostics go to stderr or they corrupt the
  stream.
- **One catalog.** `server.py` derives its `Literal` types from `H.TESTS`, so a test
  cannot be advertised without being callable. Never restate the catalog.

## Adding a test

1. Add an entry to `TESTS` in `hypothesis.py`: `tool`, `summary`, `null_hypothesis`, the
   input shape (`samples` is `1`, `2`, or `"2+"`), any flags (`directional`,
   `needs_reference`, `paired`, `accepts_equal_var`), the `backend` dotted path, and
   honest `assumptions`.
2. Add a branch to the matching `run_*_test` dispatch that calls exactly the backend
   named in `backend`, and passes warnings through rather than swallowing them.
3. Leave `server.py` alone unless the tool gains a new argument: the schemas follow the
   catalog.
4. Add a fixture branch to `_expected()` in the test suite. The parity tests are
   parametrized over `H.TESTS`, so a new entry enrolls itself and fails until a direct
   backend call proves it matches.
5. Document the id in the README table. `test_readme_documents_exactly_the_supported_ids`
   fails when the README omits an id, and when it cites one that no longer exists.

## Conventions

- Tests are named as sentences that state the claim
  (`test_undefined_p_value_is_reported_rather_than_invented`). A test asserts one claim.
- Comments explain why, not what. Most of this codebase is documented by naming things
  properly instead.
- ruff with `line-length = 100` decides formatting. Do not hand-format around it.
- Commit messages are conventional commits, lowercase, describing the change and its
  reason: `test: compare against the backends and the real transport`. A `commit-msg` hook
  rejects anything else, because the version is computed from these subjects.
- The README is executable documentation here, not decoration. A test reads it.

## Releases

python-semantic-release reads the commit history on every push to `main` and decides
everything. **The version, the tag and `CHANGELOG.md` are generated; never edit them by
hand.**

| Subject | Effect |
|---|---|
| `feat:` | minor bump |
| `fix:` | patch bump |
| `feat!:`, or a `BREAKING CHANGE:` footer | minor bump while below 1.0, not major |
| `docs:` `test:` `build:` `ci:` `refactor:` `perf:` `style:` `chore:` | no release |

Below 1.0 a breaking change stays minor: going to 2.0 on the first `!` would claim a
stability askance has not offered. Revisit at 1.0.

Only the subject is constrained. The body is unconstrained and remains the valuable part.

To see what your commits would release, without releasing it:

```bash
uv run semantic-release --noop version --print
```

Releases happen on `main` and nowhere else; a branch is refused outright. The release
commit itself is `chore(release): vX.Y.Z`, which releases nothing, so the workflow it
triggers stops there.
