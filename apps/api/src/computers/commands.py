"""Which shell commands `computer.inspect` runs without asking (ADR 0020 §4): only ones that read.

A strict allowlist, not a guess about what a command does. A command is one or more allowed
programs joined by pipes (`|`), each with flags it allows. Anything else is refused, with a
reason and a pointer at `computer.run` (which a person may be asked to approve):

- no `;`, `&&`, `||`, `&`, newlines, redirection (`>`, `<`), subshells or `$`-expansion outside
  single quotes (`$(…)`, `${…}`, `$VAR`), and no backticks;
- no unquoted braces, and no `*`, `?` or `[` pattern at the start of a word or a flag (a file
  named `--output=x` would become a flag): `./*.py` and `'*.py'` are fine;
- programs by name only (no paths, no `VAR=value` in front);
- per program: flags that write files or run other programs are refused (`sort -o`, `find -exec`,
  `rg --pre`, `git -c`, `git diff --output`…). GNU long options may be shortened (`--out`), so a
  long flag is refused when it is any prefix of a refused one.

`check(command)` returns None when it may run, else why not.
"""

import shlex
from collections.abc import Callable
from dataclasses import dataclass, field

USE_RUN = "Use computer.run for it (a person may be asked to approve it first)."
GLOB_FIRST = (
    "A pattern can't start a word or a flag: a file named like a flag would become one. "
    "Start it with ./ (./*.py) or put it in quotes (--include='*.py')."
)

# Programs that only read, and the flags of theirs that would write, run something or never end.
# (short letters, long names)
_READERS: dict[str, tuple[str, tuple[str, ...]]] = {
    "ls": ("", ()),
    "cat": ("", ()),
    "head": ("", ()),
    "tail": ("fF", ("--follow", "--retry", "--pid")),
    "wc": ("", ()),
    "grep": ("", ()),
    "egrep": ("", ()),
    "fgrep": ("", ()),
    "rg": ("z", ("--pre", "--pre-glob", "--hostname-bin", "--search-zip")),  # these run other programs
    "file": ("C", ("--compile",)),
    "stat": ("", ()),
    "du": ("", ()),
    "df": ("", ()),
    "tree": ("o", ()),
    "pwd": ("", ()),
    "echo": ("", ()),
    "printf": ("v", ()),
    "which": ("", ()),
    "whoami": ("", ()),
    "id": ("", ()),
    "uname": ("", ()),
    "uptime": ("", ()),
    "free": ("", ()),
    "nproc": ("", ()),
    "lscpu": ("", ()),
    "lsblk": ("", ()),
    "ps": ("", ()),
    "lsof": ("", ()),
    "netstat": ("", ()),
    "ss": ("KD", ("--kill", "--diag")),
    "sort": ("oT", ("--output", "--compress-program", "--temporary-directory")),
    "cut": ("", ()),
    "tr": ("", ()),
    "nl": ("", ()),
    "column": ("", ()),
    "diff": ("", ()),
    "cmp": ("", ()),
    "comm": ("", ()),
    "jq": ("", ()),
    "basename": ("", ()),
    "dirname": ("", ()),
    "realpath": ("", ()),
    "readlink": ("", ()),
    "sha256sum": ("", ()),
    "sha1sum": ("", ()),
    "md5sum": ("", ()),
    "base64": ("", ()),
}
# Programs allowed only to say their version (`node --version`). Not those whose project files can
# make them run other code first: yarn (yarnPath), pnpm (packageManager), go (toolchain), cargo and
# rustc (rust-toolchain.toml). And never `version` alone: `npm version` changes package.json.
_VERSION_ONLY = frozenset(
    {
        "python",
        "python3",
        "node",
        "npm",
        "npx",
        "bun",
        "deno",
        "java",
        "javac",
        "pip",
        "pip3",
        "uv",
        "docker",
        "gcc",
        "make",
        "ruby",
    }
)
_VERSION_ARGS = frozenset({"--version", "-V", "-v", "-version"})
_FIND_REFUSED = frozenset({"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"})
_GIT_SUBCOMMANDS = frozenset({"status", "diff", "log", "show", "branch", "ls-files", "rev-parse", "blame", "remote"})
_GIT_OUTPUT = ("--output", "--ext-diff", "--textconv", "--show-signature")
# Every inspect `git` runs with these first, whatever the repository's config says: no fsmonitor
# program, no hooks, no external diff or signature program (`hardened`).
GIT_SAFE_CONFIG = (
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "diff.external=",
    "-c",
    "log.showSignature=false",
)
# ...and these right after the subcommand: no external diff or textconv program for files.
_GIT_SAFE_OPTIONS = {
    "diff": ("--no-ext-diff", "--no-textconv"),
    "show": ("--no-ext-diff", "--no-textconv"),
    "log": ("--no-ext-diff", "--no-textconv"),
    "blame": ("--no-textconv",),
}
# `git branch`: only flags that list. A name without one of the list flags would make a branch.
_BRANCH_LISTS = frozenset(
    {"-a", "--all", "-r", "--remotes", "-l", "--list", "-v", "-vv", "--verbose", "--show-current", "--no-color"}
)
_BRANCH_FILTERS = frozenset({"--contains", "--no-contains", "--merged", "--no-merged", "--points-at"})
_DATE_VALUES = frozenset({"-d", "--date", "-r", "--reference", "-f", "--file"})
_HOSTNAME_FLAGS = frozenset(
    {"-s", "--short", "-f", "--fqdn", "--long", "-d", "--domain", "-i", "--ip-address", "-I", "--all-ip-addresses"}
)


@dataclass
class _Scan:
    """The command split at unquoted pipes, or why it can't run."""

    parts: list[str] = field(default_factory=list)
    refusal: str | None = None


def check(command: str) -> str | None:
    """None when `command` only reads, else why it can't run here."""
    if not command.strip():
        return "There's no command."
    scan = _scan(command)
    if scan.refusal:
        return f"{scan.refusal} {USE_RUN}"
    for part in scan.parts:
        try:
            argv = shlex.split(part, posix=True)
        except ValueError as error:
            return f"The command couldn't be read ({error}). {USE_RUN}"
        if not argv:
            return "A pipe (|) needs a command on both sides."
        refusal = _check_program(argv)
        if refusal:
            return f"{refusal} {USE_RUN}"
    return None


def hardened(command: str) -> str:
    """The command as it is sent, once `check` allowed it: each `git` in it gets BotDesk's own
    config and options first (`GIT_SAFE_CONFIG`), so a repository's config can't make a read run
    a program. Everything else is sent as written."""
    parts = []
    for part in _scan(command).parts:
        argv = shlex.split(part, posix=True)
        parts.append(_hardened_git(argv) if argv[0] == "git" else part.strip())
    return " | ".join(parts)


def _hardened_git(argv: list[str]) -> str:
    rest, before = list(argv[1:]), []
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        before.append(flag)
        if flag == "-C" and rest:
            before.append(rest.pop(0))
    subcommand, options = rest[0], rest[1:]
    words = ["git", *GIT_SAFE_CONFIG, *before, subcommand, *_GIT_SAFE_OPTIONS.get(subcommand, ()), *options]
    return " ".join(_quote(word) for word in words)


def _quote(word: str) -> str:
    """Quoted for the shell, with ~ still meaning the home folder."""
    if word == "~":
        return "~"
    if word.startswith("~/"):
        return "~/" + shlex.quote(word[2:])
    return shlex.quote(word)


def _scan(command: str) -> _Scan:
    """Walk the text as bash would quote it: single quotes keep everything; double quotes still
    expand `$` and backticks; outside quotes, the shell's operators mean something."""
    scan = _Scan()
    start, i, quote = 0, 0, ""
    word = ""  # the current word's literal text so far (what a pattern in it would start with)
    while i < len(command):
        char = command[i]
        if char == "\0":
            return _Scan(refusal="The command has a NUL character.")
        if quote == "'":
            quote = "" if char == "'" else quote
            word += char if quote else ""
        elif char == "\\":
            i += 1  # the next character is taken as it is
            if i < len(command) and command[i] in "\n\r":
                return _Scan(refusal="A command here is one line.")
            word += command[i : i + 1]
        elif char == "$":
            return _Scan(refusal="$ expands (variables, $(…)); put a literal $ inside single quotes.")
        elif char == "`":
            return _Scan(refusal="Backticks run a command inside the command.")
        elif quote == '"':
            quote = "" if char == '"' else quote
            word += char if quote else ""
        elif char in "'\"":
            quote = char
        elif char in " \t":
            word = ""
        elif char in "*?[" and (not word or word.startswith("-")):
            return _Scan(refusal=GLOB_FIRST)
        elif char == "{" and command[i + 1 : i + 2] == "}":
            word += "{}"  # find's {}: an empty pair doesn't expand
            i += 1
        elif char in "{}":
            return _Scan(refusal="Braces expand into other words; put them inside quotes.")
        elif char in "\n\r":
            return _Scan(refusal="A command here is one line: one command, or several joined by pipes (|).")
        elif char in ";&":
            return _Scan(refusal="Only one command, or several joined by pipes (|): no ;, && or &.")
        elif char in "<>":
            return _Scan(refusal="Redirection (< or >) isn't allowed: it can write files.")
        elif char in "()":
            return _Scan(refusal="Subshells and process substitution aren't allowed.")
        elif char == "|":
            if command[i + 1 : i + 2] == "|":
                return _Scan(refusal="Only one command, or several joined by pipes (|): no ||.")
            scan.parts.append(command[start:i])
            start = i + 1
            word = ""
        else:
            word += char
        i += 1
    if quote:
        return _Scan(refusal="A quote isn't closed.")
    scan.parts.append(command[start:])
    return scan


def _check_program(argv: list[str]) -> str | None:
    program, args = argv[0], argv[1:]
    if "/" in program:
        return f"Run programs by name, not by path ({program})."
    if "=" in program:
        return "Setting variables before a command isn't allowed."
    if program in _READERS:
        short, long = _READERS[program]
        return _refused_flag(program, args, short, long)
    if program in _VERSION_ONLY:
        if len(args) == 1 and args[0] in _VERSION_ARGS:
            return None
        return f"{program} only shows its version here ({program} --version)."
    special = _SPECIAL.get(program)
    if special is not None:
        return special(args)
    return f"{program} isn't one of the programs that only read."


def _refused_flag(program: str, args: list[str], short: str, long: tuple[str, ...]) -> str | None:
    for arg in args:
        if arg == "--":
            return None  # what follows are names, not flags
        if arg.startswith("--") and len(arg) > 2:
            name = arg.split("=", 1)[0]
            if any(refused.startswith(name) for refused in long):
                return f"{program} {name} can write files or run other programs."
        elif arg.startswith("-") and len(arg) > 1 and short:
            letters = set(arg[1:])
            if letters & set(short):
                return f"{program} {arg} can write files, run other programs or never end."
    return None


def _find(args: list[str]) -> str | None:
    for arg in args:
        if arg in _FIND_REFUSED:
            return f"find {arg} changes files or runs other programs."
    return None


def _git(args: list[str]) -> str | None:
    rest = list(args)
    while rest and rest[0].startswith("-"):
        flag = rest.pop(0)
        if flag == "-C" and rest:
            rest.pop(0)  # its folder
        elif flag != "--no-pager":
            return f"git {flag} isn't allowed here (only -C <folder> and --no-pager before the subcommand)."
    if not rest:
        return "Name a git subcommand (status, diff, log…)."
    subcommand, options = rest[0], rest[1:]
    if subcommand not in _GIT_SUBCOMMANDS:
        allowed = ", ".join(sorted(_GIT_SUBCOMMANDS))
        return f"git {subcommand} isn't allowed here; these only read: {allowed}."
    refused = _refused_flag(f"git {subcommand}", options, "", _GIT_OUTPUT)
    if refused:
        return refused
    if subcommand == "branch":
        return _git_branch(options)
    if subcommand == "remote":
        return _git_remote(options)
    return None


def _git_branch(options: list[str]) -> str | None:
    names = [option for option in options if not option.startswith("-")]
    flags = [option.split("=", 1)[0] for option in options if option.startswith("-")]
    for flag in flags:
        if flag not in _BRANCH_LISTS | _BRANCH_FILTERS and not flag.startswith(("--sort", "--format", "--color")):
            return f"git branch {flag} changes branches; this only lists them."
    if names and not set(flags) & ({"-l", "--list"} | _BRANCH_FILTERS):
        return "git branch <name> makes a branch; to list matching ones use git branch --list <pattern>."
    return None


def _git_remote(options: list[str]) -> str | None:
    if all(option in ("-v", "--verbose") for option in options):
        return None
    if options and options[0] == "get-url":
        return None
    return "git remote only lists here (git remote -v, git remote get-url <name>)."


def _date(args: list[str]) -> str | None:
    refused = _refused_flag("date", args, "s", ("--set",))
    if refused:
        return refused
    after_flag = False
    for arg in args:
        if arg.startswith("-"):
            after_flag = arg in _DATE_VALUES
            continue
        if not after_flag and not arg.startswith("+"):
            return "date with a time sets the clock; to show a format use date +FORMAT."
        after_flag = False
    return None


def _hostname(args: list[str]) -> str | None:
    if all(arg in _HOSTNAME_FLAGS for arg in args):
        return None
    return "hostname with a name sets it; this only shows it."


def _uniq(args: list[str]) -> str | None:
    names, skip = [], False
    for arg in args:
        if skip:
            skip = False
        elif arg in ("-f", "-s", "-w"):
            skip = True
        elif not arg.startswith("-") or arg == "-":
            names.append(arg)
    if len(names) > 1:
        return "uniq with two names writes the second file."
    return None


_SPECIAL: dict[str, Callable[[list[str]], str | None]] = {
    "find": _find,
    "git": _git,
    "date": _date,
    "hostname": _hostname,
    "uniq": _uniq,
}
