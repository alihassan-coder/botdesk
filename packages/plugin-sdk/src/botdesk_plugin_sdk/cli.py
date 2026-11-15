"""`python -m botdesk_plugin_sdk`: the commands a plugin author (and BotDesk's CI) runs.

    python -m botdesk_plugin_sdk manifest plugins/weather            # write manifest.json
    python -m botdesk_plugin_sdk manifest --check plugins/*/         # fail if one is stale
    python -m botdesk_plugin_sdk check-imports plugins/*/ packages/plugin-sdk

Each takes one or more project folders (the folder with `pyproject.toml`). Exit code 0 when
everything is fine, 1 when something needs fixing; the reasons go to stderr.
"""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from botdesk_plugin_sdk.manifest import manifest_json
from botdesk_plugin_sdk.project import import_problems, load_plugin

MANIFEST_FILE = "manifest.json"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m botdesk_plugin_sdk", description="BotDesk plugin author tools.")
    commands = parser.add_subparsers(dest="command", required=True)
    manifest = commands.add_parser("manifest", help=f"write each plugin's {MANIFEST_FILE} from its code")
    manifest.add_argument("--check", action="store_true", help=f"don't write; fail if {MANIFEST_FILE} is out of date")
    manifest.add_argument("projects", nargs="+", type=Path, metavar="PROJECT")
    imports = commands.add_parser("check-imports", help="fail on imports outside the stdlib, the package and its deps")
    imports.add_argument("projects", nargs="+", type=Path, metavar="PROJECT")
    args = parser.parse_args(argv)

    if args.command == "manifest":
        results = [write_manifest(project, check=args.check) for project in args.projects]
    else:
        results = [check_imports(project) for project in args.projects]
    return 0 if all(results) else 1


def write_manifest(project: Path, *, check: bool) -> bool:
    try:
        text = manifest_json(load_plugin(project))
    except Exception as error:
        print(f"{project}: {type(error).__name__}: {error}", file=sys.stderr)
        return False
    path = project / MANIFEST_FILE
    current = path.read_text(encoding="utf-8") if path.exists() else None
    if current == text:
        return True
    if check:
        print(f"{path} is out of date: run `python -m botdesk_plugin_sdk manifest {project}`", file=sys.stderr)
        return False
    path.write_text(text, encoding="utf-8")
    print(f"wrote {path}")
    return True


def check_imports(project: Path) -> bool:
    problems = import_problems(project)
    for problem in problems:
        print(f"{project}/{problem}", file=sys.stderr)
    return not problems
