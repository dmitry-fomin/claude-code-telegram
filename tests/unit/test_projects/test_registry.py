"""Tests for YAML project registry loading."""

from pathlib import Path

import pytest

from src.projects.registry import load_project_registry


def test_load_project_registry_valid(tmp_path: Path) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app_one").mkdir()
    (approved / "app_two").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: app1\n"
        "    name: App One\n"
        "    path: app_one\n"
        "  - slug: app2\n"
        "    name: App Two\n"
        "    path: app_two\n"
        "    enabled: false\n",
        encoding="utf-8",
    )

    registry = load_project_registry(config_file, approved)

    assert len(registry.projects) == 2
    enabled = registry.list_enabled()
    assert len(enabled) == 1
    assert enabled[0].slug == "app1"


def test_load_project_registry_rejects_duplicate_slug(tmp_path: Path) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app_one").mkdir()
    (approved / "app_two").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: app\n"
        "    name: App One\n"
        "    path: app_one\n"
        "  - slug: app\n"
        "    name: App Two\n"
        "    path: app_two\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        load_project_registry(config_file, approved)

    assert "Duplicate project slug" in str(exc_info.value)


def test_load_project_registry_with_cli_and_model(tmp_path: Path) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app_claude").mkdir()
    (approved / "app_gemini").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: claude-app\n"
        "    name: Claude App\n"
        "    path: app_claude\n"
        "    cli: claude\n"
        "    model: claude-opus-4-7\n"
        "  - slug: gemini-app\n"
        "    name: Gemini App\n"
        "    path: app_gemini\n"
        "    cli: gemini\n"
        "    model: gemini-2.5-pro\n",
        encoding="utf-8",
    )

    registry = load_project_registry(config_file, approved)

    claude_proj = registry.get_by_slug("claude-app")
    assert claude_proj is not None
    assert claude_proj.cli == "claude"
    assert claude_proj.model == "claude-opus-4-7"

    gemini_proj = registry.get_by_slug("gemini-app")
    assert gemini_proj is not None
    assert gemini_proj.cli == "gemini"
    assert gemini_proj.model == "gemini-2.5-pro"


def test_load_project_registry_defaults_cli_to_claude(tmp_path: Path) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: app\n"
        "    name: App\n"
        "    path: app\n",
        encoding="utf-8",
    )

    registry = load_project_registry(config_file, approved)
    proj = registry.get_by_slug("app")
    assert proj is not None
    assert proj.cli == "claude"
    assert proj.model is None


def test_load_project_registry_rejects_invalid_cli(tmp_path: Path) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()
    (approved / "app").mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n"
        "  - slug: app\n"
        "    name: App\n"
        "    path: app\n"
        "    cli: openai\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        load_project_registry(config_file, approved)

    assert "cli must be 'claude' or 'gemini'" in str(exc_info.value)


def test_load_project_registry_rejects_outside_approved_dir(tmp_path: Path) -> None:
    approved = tmp_path / "projects"
    approved.mkdir()

    config_file = tmp_path / "projects.yaml"
    config_file.write_text(
        "projects:\n" "  - slug: app\n" "    name: App\n" "    path: ../outside\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        load_project_registry(config_file, approved)

    assert "outside approved directory" in str(exc_info.value)
