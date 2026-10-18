"""Tests for release configuration and workflow invariants.

The workflow is read as text because each required property is a literal; parsing it would
add a YAML dependency used only by these tests.
"""

from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text())


def config() -> dict:
    return pyproject()["tool"]["semantic_release"]


def workflow() -> str:
    return (ROOT / ".gitea/workflows/release.yml").read_text()


def hooks() -> str:
    return (ROOT / ".pre-commit-config.yaml").read_text()


# -- one tool writes the version -------------------------------------------


def test_only_semantic_release_can_write_a_version() -> None:
    """No second tool may update versions or tags."""
    assert config()["commit_parser"] == "conventional"
    assert config()["version_toml"] == ["pyproject.toml:project.version"]
    assert "commitizen" not in (ROOT / "pyproject.toml").read_text()


def test_the_version_lives_in_exactly_one_place() -> None:
    assert isinstance(pyproject()["project"]["version"], str)
    assert "dynamic" not in pyproject()["project"]


def test_commit_subjects_are_checked_at_the_commit_msg_stage() -> None:
    """Declaring the hook is insufficient unless prek installs the commit-msg stage."""
    text = hooks()
    declared = text.split("default_install_hook_types:")[1].split("\n")[0]
    assert "commit-msg" in declared
    assert "conventional-pre-commit" in text
    assert "stages: [commit-msg]" in text


# -- what a release is, and is not -----------------------------------------


def test_releases_target_this_forgejo_over_http() -> None:
    assert config()["remote"] == {
        "type": "gitea",
        "domain": "http://localhost:3000",
        "api_domain": {"env": "GITEA_SERVER_URL"},
        "token": {"env": "GITEA_TOKEN"},
        "insecure": True,
        "ignore_token_for_push": True,
    }


def test_releases_push_through_the_checkouts_authenticated_remote() -> None:
    """A token push URL is built from `domain`, which the job container cannot reach."""
    assert config()["remote"]["ignore_token_for_push"] is True
    assert "persist-credentials: false" not in workflow()


def test_a_release_publishes_nothing() -> None:
    """Releases create a tag, changelog entry, and Forgejo release, but no artifacts."""
    assert "uv build" not in config()["build_command"]
    assert config()["upload_to_vcs_release"] is False


def test_the_release_commit_keeps_the_lockfile_in_step() -> None:
    """The lockfile records the project's version; a stale one fails the uv-lock hook."""
    assert config()["build_command"] == "uv lock && git add uv.lock"


def test_below_one_point_zero_a_breaking_change_stays_minor() -> None:
    assert config()["allow_zero_version"] is True
    assert config()["major_on_zero"] is False


def test_the_release_commit_cannot_release_anything() -> None:
    """The generated commit must not trigger another release."""
    assert config()["commit_message"] == "chore(release): v{version}"
    excluded = config()["changelog"]["exclude_commit_patterns"]
    assert any(pattern.startswith("^chore") for pattern in excluded)


def test_the_release_commit_passes_our_own_commit_hook(tmp_path: Path) -> None:
    """The generated subject must pass the commit-msg hook."""
    subject = config()["commit_message"].format(version="1.2.3")
    # Not under .git: that path is a file, not a directory, in a linked worktree.
    message = tmp_path / "ASKANCE_RELEASE_SUBJECT_CHECK"
    message.write_text(subject + "\n")
    try:
        result = subprocess.run(
            ["uvx", "--quiet", "conventional-pre-commit", str(message)],
            capture_output=True,
            text=True,
        )
    except OSError:  # pragma: no cover - uvx missing
        pytest.skip("uvx is unavailable")
    if result.returncode not in (0, 1):  # pragma: no cover - uvx could not fetch the hook
        pytest.skip("conventional-pre-commit could not run")
    assert result.returncode == 0, f"{subject!r} would be rejected by our own commit hook"


# -- the workflow ----------------------------------------------------------


def test_releases_happen_only_on_main() -> None:
    text = workflow()
    assert "branches: [main]" in text
    assert "pull_request" not in text
    assert config()["branches"]["main"]["match"] == "main"


def test_the_workflow_can_see_previous_versions() -> None:
    """semantic-release needs prior tags to calculate the next version."""
    assert "fetch-depth: 0" in workflow()


def test_the_workflow_does_not_answer_itself_forever() -> None:
    text = workflow()
    assert '"chore(release): "*' in text
    assert "steps.guard.outputs.run == 'true'" in text


def test_the_suite_gates_the_release() -> None:
    text = workflow()
    assert "uvx nox -s lint skills tests" in text
    # Match the step name; the workflow itself is also named "Release".
    assert text.index("- name: Check") < text.index("- name: Release")


def test_the_workflow_uses_the_runners_short_lived_token() -> None:
    text = workflow()
    assert "${{ forgejo.token }}" in text
    # The word may appear in prose; only a secrets.* expression would reference storage.
    assert "${{ secrets." not in text


def test_the_workflow_speaks_forgejo_not_github() -> None:
    """Use Forgejo variables instead of the GitHub Actions compatibility aliases."""
    text = workflow()
    assert "FORGEJO_OUTPUT" in text and "FORGEJO_PATH" in text
    assert "GITHUB_OUTPUT" not in text and "GITHUB_PATH" not in text


def test_nox_is_invoked_as_a_tool_not_a_dependency() -> None:
    """nox is run with uvx because it is a tool, not a project dependency."""
    assert "uvx nox" in workflow()
    assert "nox" not in str(pyproject()["project"]["optional-dependencies"]["dev"])


# -- a starting point ------------------------------------------------------


def test_a_baseline_tag_exists() -> None:
    """The first automated release needs a baseline tag."""
    found = subprocess.run(
        ["git", "tag", "--list", "v0.2.0"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.split()
    if not found:  # pragma: no cover - a shallow or tagless checkout
        pytest.skip("no tags in this checkout")
    assert found == ["v0.2.0"]
