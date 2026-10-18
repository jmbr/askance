"""Nox sessions for tests, linting, formatting, and skill validation.

Git hooks call these sessions instead of defining separate checks. Every session installs
exactly what uv.lock pins. The test session also builds and installs the package itself, so
packaging errors fail before an agent starts the server.
"""

from pathlib import Path

import nox

nox.options.default_venv_backend = "uv"
nox.options.sessions = ["tests", "lint", "skills"]


def sync(session: nox.Session, *args: str) -> None:
    """Install the locked versions into this session's environment; a stale lock fails."""
    session.run_install(
        "uv",
        "sync",
        "--locked",
        f"--python={session.virtualenv.location}",
        *args,
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
        external=True,
    )


@nox.session(python=["3.12", "3.13"])
def tests(session: nox.Session) -> None:
    """Run the test suite against an installed copy of the package."""
    sync(session, "--no-editable", "--no-default-groups", "--group=test")
    session.run("pytest", *session.posargs)


@nox.session
def lint(session: nox.Session) -> None:
    """Report style and formatting problems without changing anything."""
    sync(session, "--only-group=lint")
    session.run("ruff", "check", ".", *session.posargs)
    session.run("ruff", "format", "--check", ".")


@nox.session
def format(session: nox.Session) -> None:
    """Apply Ruff's safe fixes and formatter."""
    sync(session, "--only-group=lint")
    session.run("ruff", "check", "--fix", ".", *session.posargs)
    session.run("ruff", "format", ".")


@nox.session
def skills(session: nox.Session) -> None:
    """Validate every Agent Skill under skills/."""
    directories = sorted(path for path in Path("skills").glob("*") if path.is_dir())
    if not directories:
        session.skip("no skills to validate")
    sync(session, "--only-group=skills")
    for directory in directories:
        session.run("skills-ref", "validate", str(directory))
