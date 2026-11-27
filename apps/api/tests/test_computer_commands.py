"""`computer.inspect` runs only commands that read (ADR 0020 §4): a strict allowlist, with the
tricky ways a "read" could still write a file or run something else refused."""

import pytest

from src.computers.commands import GIT_SAFE_CONFIG, USE_RUN, check, hardened


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "ls -la ~/app",
        "cat package.json",
        "head -n 50 src/main.py",
        "tail -n 100 /var/log/syslog",
        "grep -rn 'TODO' src",
        "grep -E 'a|b' notes.txt",
        "rg --line-number 'def main' .",
        "find . -name '*.py' -not -path './node_modules/*'",
        "find ./src -type f -newer package.json",
        "wc -l src/app.py src/db.py",
        "du -sh .",
        "df -h",
        "ps aux | grep node",
        "ss -tlnp",
        "git status",
        "git -C ~/app status --short",
        "git --no-pager log --oneline -n 20",
        "git diff HEAD~1 -- src/app.py",
        "git show HEAD:package.json",
        "git branch -a",
        "git branch --list 'feature/*'",
        "git branch --contains abc123",
        "git remote -v",
        "git remote get-url origin",
        "git ls-files | wc -l",
        "git rev-parse --abbrev-ref HEAD",
        "git blame -L 10,20 src/app.py",
        "cat src/*.ts",
        "ls ./*.py",
        "cat package.json | jq '.scripts'",
        "sort names.txt | uniq -c | sort -rn | head",
        "echo 'cost: $5'",
        "printf '%s\\n' hello",
        "date +%Y-%m-%d",
        "date -d yesterday +%A",
        "hostname -I",
        "node --version",
        "python3 -V",
        "npm --version",
        "uname -a",
        "which node",
        "tree -L 2",
        "diff a.txt b.txt",
        "stat -c %s report.pdf",
        "base64 -d blob.b64 | head -c 100",
    ],
)
def test_reading_commands_run(command: str) -> None:
    assert check(command) is None, check(command)


@pytest.mark.parametrize(
    ("command", "why"),
    [
        ("rm -rf ~/app", "isn't one of the programs that only read"),
        ("ls; rm -rf /", "no ;, && or &"),
        ("ls && rm x", "no ;, && or &"),
        ("ls || rm x", "no ||"),
        ("sleep 100 &", "no ;, && or &"),
        ("cat a > b", "Redirection"),
        ("cat < /etc/passwd", "Redirection"),
        ("echo $(rm -rf ~)", "$ expands"),
        ('echo "$(whoami)"', "$ expands"),
        ("echo ${HOME}", "$ expands"),
        ("echo $OPENAI_API_KEY", "$ expands"),
        ("echo `rm -rf ~`", "Backticks"),
        ("cat <(rm x)", "Redirection"),
        ("(rm x)", "Subshells"),
        ("ls\nrm x", "one line"),
        ("ls \\\nrm", "one line"),
        ("find . -name x -exec rm {} \\;", "find -exec"),
        ("find . -delete", "find -delete"),
        ("find . -fprint out.txt", "find -fprint"),
        ("find . -okdir rm {} +", "find -okdir"),
        ("sort -o out.txt in.txt", "sort -o"),
        ("sort -uo out.txt in.txt", "sort -uo"),
        ("sort --output=out.txt in.txt", "sort --output"),
        ("sort --out=x in.txt", "sort --out"),
        ("sort --compress-program=sh in.txt", "sort --compress-program"),
        ("tail -f app.log", "tail -f"),
        ("tail --follow=name app.log", "tail --follow"),
        ("rg --pre ./evil.sh x", "rg --pre"),
        ("tree -o out.txt", "tree -o"),
        ("file -C -m magic", "file -C"),
        ("ss -K dst 1.2.3.4", "ss -K"),
        ("uniq in.txt out.txt", "uniq with two names"),
        ("date -s '2030-01-01'", "date -s"),
        ("date 010100002030", "sets the clock"),
        ("hostname evil", "hostname with a name"),
        ("git push", "git push isn't allowed"),
        ("git commit -m x", "git commit isn't allowed"),
        ("git checkout main", "git checkout isn't allowed"),
        ("git -c core.pager='rm -rf ~' log", "git -c"),
        ("git --exec-path=/tmp status", "git --exec-path"),
        ("git diff --output=patch.txt", "git diff --output"),
        ("git log --out=x", "git log --out"),
        ("git diff --ext-diff", "git diff --ext-diff"),
        ("git branch new-feature", "makes a branch"),
        ("git branch -D main", "git branch -D"),
        ("git branch --delete main", "git branch --delete"),
        ("git branch -m old new", "git branch -m"),
        ("git remote add evil https://x", "git remote only lists"),
        ("git remote set-url origin https://x", "git remote only lists"),
        ("/bin/rm -rf x", "not by path"),
        ("./script.sh", "not by path"),
        ("FOO=bar ls", "Setting variables"),
        ("env", "isn't one of the programs"),
        ("printenv", "isn't one of the programs"),
        ("xargs rm < list", "Redirection"),
        ("ls | xargs rm", "xargs isn't one of the programs"),
        ("curl https://example.com", "curl isn't one of the programs"),
        ("python3 -c 'import os'", "only shows its version"),
        ("node -e 'process.exit()'", "only shows its version"),
        ("awk '{system(\"rm x\")}' f", "awk isn't one of the programs"),
        ("sed -i s/a/b/ f", "sed isn't one of the programs"),
        ("sort *", "A pattern can't start a word"),
        ("sort ''*", "A pattern can't start a word"),
        ("sort -* in.txt", "A pattern can't start a word"),
        ("grep -r x --include=*.py .", "A pattern can't start a word"),
        ("sort {-o,out.txt} in.txt", "Braces"),
        ("ls |", "both sides"),
        ("| ls", "both sides"),
        ("cat 'unclosed", "quote isn't closed"),
        ("", "no command"),
        # Programs that would run other code first, and `version` that changes package.json.
        ("go version", "isn't one of the programs"),
        ("yarn --version", "isn't one of the programs"),
        ("pnpm --version", "isn't one of the programs"),
        ("cargo --version", "isn't one of the programs"),
        ("npm version", "only shows its version"),
        ("npm version patch", "only shows its version"),
        # rg flags that run other programs.
        ("rg --pre ./x.sh foo", "rg --pre"),
        ("rg --pre-glob '*.pdf' --pre ./x.sh foo", "rg --pre-glob"),
        ("rg --hostname-bin=./evil foo", "rg --hostname-bin"),
        ("rg --hostname-b=./evil foo", "rg --hostname-b"),
        ("rg -z foo", "rg -z"),
        ("rg --search-zip foo", "rg --search-zip"),
        ("git log --show-signature", "git log --show-signature"),
    ],
)
def test_anything_else_is_refused_saying_why(command: str, why: str) -> None:
    refusal = check(command)
    assert refusal is not None, f"{command!r} should be refused"
    assert why.lower() in refusal.lower(), refusal
    if why not in ("both sides", "no command"):
        assert USE_RUN in refusal  # the bot is pointed at the tool that asks


def test_quotes_keep_operators_literal() -> None:
    assert check("grep ';' notes.txt") is None
    assert check("grep '&&' notes.txt") is None
    assert check("grep '>' notes.txt") is None
    assert check("grep 'a|b' notes.txt | wc -l") is None
    assert check('grep "x > y" notes.txt') is None
    assert check("grep \\; notes.txt") is None


SAFE = " ".join(GIT_SAFE_CONFIG)


def test_every_git_runs_with_botdesks_own_config_and_options_first() -> None:
    """A repository's config (written by an upload, or cloned) can't make a read run a program:
    no fsmonitor, no hooks, no external diff, textconv or signature program."""
    assert SAFE == ("-c core.fsmonitor=false -c core.hooksPath=/dev/null -c diff.external= -c log.showSignature=false")
    assert hardened("git status") == f"git {SAFE} status"
    assert hardened("git -C ~/p status --short") == f"git {SAFE} -C ~/p status --short"
    assert hardened("git --no-pager diff HEAD -- src | wc -l") == (
        f"git {SAFE} --no-pager diff --no-ext-diff --no-textconv HEAD -- src | wc -l"
    )
    assert hardened("git show HEAD:package.json") == f"git {SAFE} show --no-ext-diff --no-textconv HEAD:package.json"
    assert hardened("git log --oneline -n 5") == f"git {SAFE} log --no-ext-diff --no-textconv --oneline -n 5"
    assert hardened("git blame src/app.py") == f"git {SAFE} blame --no-textconv src/app.py"
    assert hardened("git log --format='%h %s'") == f"git {SAFE} log --no-ext-diff --no-textconv '--format=%h %s'"


def test_other_commands_are_sent_as_written() -> None:
    for command in ("ls ./*.py | wc -l", "grep -rn 'a|b' src", "cat package.json | jq '.scripts'"):
        assert hardened(command) == command
