"""A plugin project on disk: the folder with its `pyproject.toml`, its code and its tests.

This is what the author tooling works on (`python -m botdesk_plugin_sdk`, run in CI):

- `load_plugin` finds the plugin through the project's own `botdesk.plugins` entry point, the
  same declaration BotDesk reads, and builds its manifest. The package doesn't have to be
  installed: a `src/` folder next to `pyproject.toml` is put on the import path first.
- `import_problems` checks the import rule: a plugin imports only the standard library, its
  own package, and what its `pyproject.toml` declares. Never the BotDesk app (`src.`), never
  another plugin it doesn't depend on. The SDK keeps the same rule.
"""

import ast
import importlib
import re
import sys
import tomllib
from collections.abc import Iterable, Iterator
from functools import cache
from importlib.metadata import packages_distributions
from pathlib import Path
from typing import Any

from botdesk_plugin_sdk.manifest import ENTRY_POINT_GROUP, PluginManifest
from botdesk_plugin_sdk.validation import PluginError, validate_manifest

# The BotDesk API's import root (`from src.core.config import ...`). Named in the error message.
APP_PACKAGE = "src"

# Folders that hold no source of the project's own.
SKIPPED_DIRS = {".venv", "venv", "build", "dist", "node_modules", "__pycache__"}


def read_pyproject(project_dir: Path) -> dict[str, Any]:
    with (project_dir / "pyproject.toml").open("rb") as file:
        return tomllib.load(file)


def load_plugin(project_dir: Path) -> PluginManifest:
    """Build the plugin's manifest the way BotDesk would, and check it.

    Raises `PluginError` when the project declares no plugin (or more than one), when the
    entry-point name isn't the plugin id, or when the manifest fails `validate_manifest`.
    """
    entry_points = read_pyproject(project_dir).get("project", {}).get("entry-points", {}).get(ENTRY_POINT_GROUP, {})
    if len(entry_points) != 1:
        found = "no" if not entry_points else f"{len(entry_points)} entries in"
        raise PluginError(
            "?", [f'{project_dir} has {found} [project.entry-points."{ENTRY_POINT_GROUP}"]; it needs one']
        )
    ((entry_id, target),) = entry_points.items()

    source_dir = project_dir / "src"
    if source_dir.is_dir() and str(source_dir) not in sys.path:
        sys.path.insert(0, str(source_dir))
    module_name, colon, function_name = target.partition(":")
    if not colon or not function_name.isidentifier():
        raise PluginError(entry_id, [f"entry point {entry_id!r} must look like 'package:function', got {target!r}"])
    build = getattr(importlib.import_module(module_name), function_name)
    manifest = validate_manifest(build())
    if manifest.id != entry_id:
        raise PluginError(manifest.id, [f"entry point {entry_id!r} must match the plugin id {manifest.id!r}"])
    return manifest


def import_problems(project_dir: Path) -> list[str]:
    """Every import in the project that breaks the import rule, as `path:line: why`.

    Allowed everywhere: the standard library, the project's own packages (folders and modules
    under `src/`) and the import names of its `[project] dependencies`. Tests (files under
    `tests/`) may also use the `[dependency-groups]` (pytest and friends). Relative imports
    are always fine: they stay inside the package.
    """
    pyproject = read_pyproject(project_dir)
    project = pyproject.get("project", {})
    own = {path.stem for path in (project_dir / "src").glob("*") if path.is_dir() or path.suffix == ".py"}
    own |= import_names([project.get("name", "")])  # a flat layout (no src/) imports itself by its name
    allowed = own | set(sys.stdlib_module_names) | import_names(project.get("dependencies", []))
    test_only = {"tests"} | {path.stem for path in (project_dir / "tests").glob("*.py")}
    for group in pyproject.get("dependency-groups", {}).values():
        test_only |= import_names(entry for entry in group if isinstance(entry, str))

    problems: list[str] = []
    for path in python_files(project_dir):
        relative = path.relative_to(project_dir)
        permitted = allowed | test_only if relative.parts[0] == "tests" else allowed
        for line, name in top_level_imports(path):
            if name == APP_PACKAGE:
                problems.append(
                    f"{relative.as_posix()}:{line}: imports {name!r}, the BotDesk app; "
                    "plugins and the SDK never import the app"
                )
            elif name not in permitted:
                problems.append(
                    f"{relative.as_posix()}:{line}: imports {name!r}, which is not the standard library, "
                    "this package or a dependency declared in pyproject.toml"
                )
    return problems


def import_names(requirements: Iterable[str]) -> set[str]:
    """The names a list of requirements (`"pydantic[email]>=2.11"`) can be imported as.

    Uses the installed distributions' file lists when they're there (`beautifulsoup4` is
    imported as `bs4`), and otherwise the usual convention (`botdesk-plugin-sdk` is
    `botdesk_plugin_sdk`), which also covers workspace packages installed in editable mode.
    """
    installed = installed_import_names()
    names: set[str] = set()
    for requirement in requirements:
        match = re.match(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)", requirement)
        if match:
            distribution = normalize(match.group(1))
            names |= installed.get(distribution, frozenset()) | {distribution.replace("-", "_")}
    return names


@cache
def installed_import_names() -> dict[str, frozenset[str]]:
    """Installed distribution (normalized) -> its top-level import names. Slow, so read once."""
    found: dict[str, set[str]] = {}
    for module, distributions in packages_distributions().items():
        for distribution in distributions:
            found.setdefault(normalize(distribution), set()).add(module)
    return {distribution: frozenset(modules) for distribution, modules in found.items()}


def normalize(distribution: str) -> str:
    """PEP 503: `Pydantic_Settings` and `pydantic-settings` are the same distribution."""
    return re.sub(r"[-_.]+", "-", distribution).lower()


def python_files(project_dir: Path) -> Iterator[Path]:
    for path in sorted(project_dir.rglob("*.py")):
        parts = path.relative_to(project_dir).parts[:-1]
        if not any(part in SKIPPED_DIRS or part.startswith(".") for part in parts):
            yield path


def top_level_imports(path: Path) -> Iterator[tuple[int, str]]:
    """(line, first name) for each absolute import: `from a.b import c` gives `a`."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"), filename=str(path))):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name.partition(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            yield node.lineno, node.module.partition(".")[0]
