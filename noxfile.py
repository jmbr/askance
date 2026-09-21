"""Nox sessions for tests, linting, formatting, and skill validation.

Git hooks call these sessions instead of defining separate checks. The test session installs
the built package, so packaging errors fail before an agent starts the server.
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
    """Apply Ruff's safe fixes and formatter."""
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
