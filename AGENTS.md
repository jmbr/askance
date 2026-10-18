# AGENTS.md

Askance is an MCP server that runs hypothesis tests through SciPy and statsmodels. Every
reported statistic must come from one of those backends.

## Layout

| Path | What lives there |
|---|---|
| `src/askance/hypothesis.py` | The statistical core: the `TESTS` catalog, validation, dispatch, result shape |
| `src/askance/server.py` | MCP translation only. No statistical logic, no second copy of the catalog |
| `tests/test_askance.py` | The pytest suite, including the subprocess install test |
| `tests/skill_trigger_eval.sh` | Does the skill fire on the right prompts? Drives an agent CLI, so pytest does not run it |
| `skills/askance/SKILL.md` | The Agent Skill that routes statistics questions to the server |
| `docs/REFERENCE.md` | The user-facing reference: every tool, test, correction, and power design |
| `noxfile.py` | Every check, defined once |

## Checks

```bash
uvx nox                            # tests on 3.12 and 3.13, lint, skill validation
uvx nox -s tests                   # just the tests
uvx nox -s lint                    # ruff check and ruff format --check
uvx nox -s format                  # fix whatever ruff can fix
uvx nox -s skills                  # validate skills/ with skills-ref
uvx nox -s tests -- -k binomial    # arguments after -- go to pytest
```

Or work in the checkout directly:

```bash
uv sync --extra dev
uv run pytest
uv run ruff check
```

The suite compares every test against a direct SciPy or statsmodels call, and starts the
installed executable from an unrelated directory with no virtualenv, which is how an agent
starts it. Under nox that executable comes from a freshly built wheel, so a packaging
mistake fails the suite.

After changing the source, reinstall the tool with `uv tool install . --reinstall`. Plain
`--force` replaces the executable but reuses a wheel cached against the unchanged version,
so an agent keeps talking to the old server.

[prek](https://github.com/j178/prek) wires those same sessions to git hooks: formatting, skill
validation and secret scanning with [betterleaks](https://github.com/betterleaks/betterleaks) on
commit, the full suite on push.

```bash
prek install          # once per clone
prek run --all-files  # check everything now
```

Do not add a check to `.pre-commit-config.yaml` if it can be a nox session. Define it in
`noxfile.py`, then call that session from the hook.
Checks without a nox equivalent (file hygiene, `uv.lock`, and betterleaks) stay upstream
and pinned.

## Invariants

Preserve these constraints:

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
- **Tool arguments use strict types.** In lax mode pydantic turns `true` into 1 and `"7"`
  into 7 before the core can refuse them.
- **Backend calls run inside `_backend()`.** `warnings.catch_warnings` is process-global and
  the SDK runs each tool call on a worker thread; the lock keeps one call's warnings out of
  another's result. `_backend()` also turns a backend's `ValueError` into an `AskanceError`,
  because the SDK hides the message of any other exception.
- **One catalog.** `server.py` derives its `Literal` types from `H.TESTS`, so a test
  cannot be advertised without being callable. Never restate the catalog.

## Adding a test

1. Add an entry to `TESTS` in `hypothesis.py`: `tool`, `summary`, `null_hypothesis`, the
   input shape (`samples` is `1`, `2`, or `"2+"`), any flags (`directional`,
   `needs_reference`, `paired`, `accepts_equal_var`), the `backend` dotted path, and
   accurate `assumptions`.
2. Add a branch to the matching `run_*_test` dispatch, inside its `_backend()` block, that
   calls exactly the backend named in `backend`, and passes warnings through rather than
   swallowing them.
3. Leave `server.py` alone unless the tool gains a new argument: the schemas follow the
   catalog.
4. Add a fixture branch to `_expected()` in the test suite. The parity tests are
   parametrized over `H.TESTS`, so a new entry enrolls itself and fails until a direct
   backend call proves it matches.
5. Document the id in the matching table in `docs/REFERENCE.md`.
   `test_reference_documents_exactly_the_supported_ids` fails when the reference omits an id,
   and when it cites one that no longer exists.

## Conventions

- Tests are named as sentences that state the claim
  (`test_undefined_p_value_is_reported_rather_than_invented`). A test asserts one claim.
- Comments explain why, not what. Delete comments that only restate the code.
- ruff with `line-length = 100` decides formatting. Do not hand-format around it.
- Commit messages are conventional commits, lowercase, describing the change and its
  reason: `test: compare against the backends and the real transport`. A `commit-msg` hook
  rejects anything else, because the version is computed from these subjects.
- Tests compare the IDs in `docs/REFERENCE.md` with the runtime catalog.

## Releases

On every push to `main`, python-semantic-release derives the next version from the commit
history. **It generates the version, tag, and `CHANGELOG.md`; never edit them by hand.**

| Subject | Effect |
|---|---|
| `feat:` | minor bump |
| `fix:` | patch bump |
| `feat!:`, or a `BREAKING CHANGE:` footer | minor bump while below 1.0, not major |
| `docs:` `test:` `build:` `ci:` `refactor:` `perf:` `style:` `chore:` | no release |

Below 1.0, a breaking change produces a minor bump. Revisit this rule at 1.0.

Only the subject format is constrained. The body is free-form.

To see what your commits would release, without releasing it:

```bash
uv run semantic-release --noop version --print
```

The release workflow runs only on `main`, and semantic-release ignores other branches. Its
generated commit is `chore(release): vX.Y.Z`; because `chore:` is non-releasing, the
workflow triggered by that commit exits without creating another release.
