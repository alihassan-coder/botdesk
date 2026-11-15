"""Author tooling: the generated manifest.json, loading a plugin from its project folder, the
import rules, and the `python -m botdesk_plugin_sdk` command that CI runs."""

import json
import textwrap
from pathlib import Path

import pytest
from pydantic import BaseModel, Field

from botdesk_plugin_sdk import NoArgs, PluginError, PluginManifest, ToolContext, ToolResult, ToolSpec, manifest_json
from botdesk_plugin_sdk.cli import main
from botdesk_plugin_sdk.project import import_problems, load_plugin


class LookupArgs(BaseModel):
    query: str = Field(description="What to look for")


async def handler(_args: BaseModel, _ctx: ToolContext) -> ToolResult:
    return {}


def tool(name: str, args_model: type[BaseModel] = NoArgs) -> ToolSpec:
    return ToolSpec(
        name=name,
        title=name.title(),
        description=f"The {name} tool.",
        args_model=args_model,
        risk="read",
        handler=handler,
    )


def manifest(*tools: ToolSpec) -> PluginManifest:
    return PluginManifest(id="hello", name="Hello", version="1.2.3", description="Says hi.", tools=tools)


def test_manifest_json_is_the_same_whatever_order_tools_are_declared_in() -> None:
    first = manifest_json(manifest(tool("beta"), tool("alpha", LookupArgs)))
    second = manifest_json(manifest(tool("alpha", LookupArgs), tool("beta")))
    assert first == second
    assert first.endswith("}\n")


def test_manifest_json_has_sorted_keys_and_each_tools_args_schema() -> None:
    data = json.loads(manifest_json(manifest(tool("beta"), tool("alpha", LookupArgs))))
    assert list(data) == ["description", "id", "manifestVersion", "name", "runtime", "tools", "version"]
    assert [t["name"] for t in data["tools"]] == ["alpha", "beta"]
    alpha = data["tools"][0]
    assert list(alpha) == sorted(alpha)
    assert alpha["risk"] == "read"
    assert alpha["inputSchema"]["required"] == ["query"]
    assert alpha["inputSchema"]["properties"]["query"]["description"] == "What to look for"


PLUGIN_SOURCE = """
from botdesk_plugin_sdk import NoArgs, PluginManifest, ToolContext, ToolResult, ToolSpec


async def ping(_args: NoArgs, _ctx: ToolContext) -> ToolResult:
    return {"pong": True}


def make() -> PluginManifest:
    return PluginManifest(
        id="{plugin_id}",
        name="Ping",
        version="0.1.0",
        description="Answers pings.",
        tools=(ToolSpec(name="ping", title="Ping", description="Ping.", args_model=NoArgs, risk="read", handler=ping),),
    )
"""


def write_project(
    root: Path,
    package: str,
    *,
    entry_id: str = "ping",
    plugin_id: str = "ping",
    dependencies: str = '"botdesk-plugin-sdk"',
) -> Path:
    """A plugin project on disk, laid out like plugins/demo, with its code under src/."""
    (root / "src" / package).mkdir(parents=True)
    (root / "src" / package / "__init__.py").write_text(PLUGIN_SOURCE.replace("{plugin_id}", plugin_id))
    (root / "pyproject.toml").write_text(
        textwrap.dedent(f"""
            [project]
            name = "botdesk-plugin-{package}"
            version = "0.1.0"
            dependencies = [{dependencies}]

            [project.entry-points."botdesk.plugins"]
            {entry_id} = "{package}:make"

            [dependency-groups]
            dev = ["pytest>=9"]
        """)
    )
    return root


def test_load_plugin_finds_the_manifest_through_the_projects_entry_point(tmp_path: Path) -> None:
    loaded = load_plugin(write_project(tmp_path, "ping_loads"))
    assert loaded.id == "ping"
    assert [t.name for t in loaded.tools] == ["ping"]


def test_load_plugin_refuses_an_entry_point_name_that_is_not_the_plugin_id(tmp_path: Path) -> None:
    with pytest.raises(PluginError, match="entry point 'pong' must match the plugin id 'ping'"):
        load_plugin(write_project(tmp_path, "ping_mismatch", entry_id="pong"))


def test_load_plugin_refuses_a_project_without_a_botdesk_entry_point(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text('[project]\nname = "not-a-plugin"\n')
    with pytest.raises(PluginError, match=r'no \[project.entry-points."botdesk.plugins"\]'):
        load_plugin(tmp_path)


def add_module(project: Path, relative: str, source: str) -> None:
    path = project / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(source))


def test_a_plugin_that_imports_the_sdk_the_stdlib_and_itself_passes(tmp_path: Path) -> None:
    project = write_project(tmp_path, "ping_clean")
    add_module(
        project, "src/ping_clean/extra.py", "import json\nfrom . import make\nfrom ping_clean import make as again\n"
    )
    assert import_problems(project) == []


def test_importing_the_botdesk_app_is_refused_with_the_line(tmp_path: Path) -> None:
    project = write_project(tmp_path, "ping_app")
    add_module(project, "src/ping_app/bad.py", "import os\n\ndef f():\n    from src.core.config import settings\n")
    assert import_problems(project) == [
        "src/ping_app/bad.py:4: imports 'src', the BotDesk app; plugins and the SDK never import the app"
    ]


def test_a_library_must_be_declared_before_it_is_imported(tmp_path: Path) -> None:
    undeclared = write_project(tmp_path / "a", "ping_undeclared")
    add_module(undeclared, "src/ping_undeclared/web.py", "import pydantic.fields\n")
    assert import_problems(undeclared) == [
        "src/ping_undeclared/web.py:1: imports 'pydantic', which is not the standard library, "
        "this package or a dependency declared in pyproject.toml"
    ]
    declared = write_project(
        tmp_path / "b", "ping_declared", dependencies='"botdesk-plugin-sdk", "pydantic[email]>=2.11"'
    )
    add_module(declared, "src/ping_declared/web.py", "import pydantic.fields\n")
    assert import_problems(declared) == []


def test_tests_may_use_the_dev_group_but_plugin_code_may_not(tmp_path: Path) -> None:
    project = write_project(tmp_path, "ping_dev")
    add_module(project, "tests/test_ping.py", "import pytest\nfrom ping_dev import make\n")
    assert import_problems(project) == []
    add_module(project, "src/ping_dev/oops.py", "import pytest\n")
    assert [p.split(":")[0] for p in import_problems(project)] == ["src/ping_dev/oops.py"]


def test_the_manifest_command_writes_manifest_json_and_check_passes_after(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = write_project(tmp_path, "ping_cli_write")
    assert main(["manifest", str(project)]) == 0
    written = json.loads((project / "manifest.json").read_text())
    assert written["id"] == "ping"
    assert [t["name"] for t in written["tools"]] == ["ping"]
    assert main(["manifest", "--check", str(project)]) == 0
    capsys.readouterr()


def test_check_fails_with_the_fix_when_manifest_json_is_stale_or_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = write_project(tmp_path, "ping_cli_stale")
    assert main(["manifest", "--check", str(project)]) == 1
    (project / "manifest.json").write_text("{}\n")
    assert main(["manifest", "--check", str(project)]) == 1
    assert (project / "manifest.json").read_text() == "{}\n"  # --check never writes
    err = capsys.readouterr().err
    assert f"{project / 'manifest.json'} is out of date: run `python -m botdesk_plugin_sdk manifest {project}`" in err


def test_a_broken_plugin_is_a_message_not_a_traceback(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    project = write_project(tmp_path, "ping_cli_broken", entry_id="pong")
    assert main(["manifest", str(project)]) == 1
    assert "must match the plugin id" in capsys.readouterr().err


def test_check_imports_lists_every_problem_and_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clean = write_project(tmp_path / "clean", "ping_cli_clean")
    assert main(["check-imports", str(clean)]) == 0
    bad = write_project(tmp_path / "bad", "ping_cli_bad")
    add_module(bad, "src/ping_cli_bad/app.py", "import src.main\n")
    assert main(["check-imports", str(clean), str(bad)]) == 1
    assert f"{bad}/src/ping_cli_bad/app.py:1: imports 'src'" in capsys.readouterr().err


def test_load_plugin_explains_an_entry_point_without_a_function(tmp_path: Path) -> None:
    project = write_project(tmp_path, "ping_no_function")
    pyproject = project / "pyproject.toml"
    pyproject.write_text(pyproject.read_text().replace('"ping_no_function:make"', '"ping_no_function"'))
    with pytest.raises(PluginError, match="must look like 'package:function'"):
        load_plugin(project)
