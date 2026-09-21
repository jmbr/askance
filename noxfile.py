"""Automated sessions: `nox` runs everything, `nox -s tests` or `nox -s lint` runs one.

The hooks in .pre-commit-config.yaml call these same sessions, so each check is defined
once here rather than once for nox and again for the hooks.

The tests session installs the built wheel rather than the source tree, so a packaging
mistake fails here instead of at the agent that tries to start the server.
"""

from pathlib import Path

import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["tests", "lint", "skills"]

RUFF = "ruff>=0.8"
SKILLS_REF = "skills-ref @ git+https://github.com/agentskills/agentskills#subdirectory=skills-ref"


@nox.session(python=["3.12", "3.13"])
def tests(session: nox.Session) -> None:
    """Run the test suite against an installed copy of the package."""
    session.install(".", "pytest>=8.0")
    session.run("pytest", *session.posargs)


@nox.session
def lint(session: nox.Session) -> None:
    """Report style and formatting problems without changing anything."""
    session.install(RUFF)
    session.run("ruff", "check", ".", *session.posargs)
    session.run("ruff", "format", "--check", ".")


@nox.session
def format(session: nox.Session) -> None:
    """Fix what lint reports, and report whatever is left."""
    session.install(RUFF)
    session.run("ruff", "check", "--fix", ".", *session.posargs)
    session.run("ruff", "format", ".")


@nox.session
def skills(session: nox.Session) -> None:
    """Validate every Agent Skill under skills/."""
    directories = sorted(path for path in Path("skills").glob("*") if path.is_dir())
    if not directories:
        session.skip("no skills to validate")
    session.install(SKILLS_REF)
    for directory in directories:
        session.run("skills-ref", "validate", str(directory))
