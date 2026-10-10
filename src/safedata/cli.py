"""Command-line entry point: `safedata <command>`.

  edit          open the records editor in the browser (writes data/records.csv)
  install       set up the git add-ons for this copy of the repository
  validate      check records.csv against the schema (also run by the pre-commit hook)
  powerquery    print the Power Query code for Excel analysis workbooks
  normalize     git clean filter (stdin to stdout)
  merge-driver  git merge driver

None of these commands pulls, commits or pushes; that is left to git.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import gitops, store
from .merge import merge
from .schema import load_schema, validate
from .webapp import DATA_FILE, SCHEMA_FILE, serve


def find_root() -> Path:
    """Repository root, or the current folder if it is not in a git repository."""
    try:
        return gitops.repo_root()
    except (gitops.GitError, OSError):
        return Path.cwd()


# ---------------------------------------------------------------- editor

def cmd_edit(args) -> int:
    root = find_root()
    if not (root / DATA_FILE).exists():
        print(f"{root / DATA_FILE} not found. Run this from the records folder.", file=sys.stderr)
        return 1
    if (root / ".git").exists():
        ensure_installed(root)
    server, url = serve(root, args.port)
    print(f"Records editor: {url}")
    print("Keep this window open while editing. Close it (or press Ctrl+C) when you are done.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


# ---------------------------------------------------------------- git add-ons

def cmd_install(args) -> int:
    install(gitops.repo_root())
    print("Set up for this copy: clean filter (sorts records.csv when staged), merge driver "
          "(merges record by record), word diff for records.csv, and the pre-commit check.")
    return 0


def install(root: Path) -> None:
    py = Path(sys.executable).as_posix()
    gitops.set_config(root, "filter.safedata.clean", f'"{py}" -m safedata normalize')
    gitops.set_config(root, "merge.safedata.name", "safedata record-level merge")
    gitops.set_config(root, "merge.safedata.driver", f'"{py}" -m safedata merge-driver %O %A %B %L %P')
    gitops.set_config(root, "diff.safedata.wordRegex", "[^,]+")
    hooks = root / gitops.git("rev-parse", "--git-path", "hooks", cwd=root).strip()
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text(f'#!/bin/sh\nexec "{py}" -m safedata validate --staged\n', encoding="utf-8", newline="\n")
    hook.chmod(0o755)


def ensure_installed(root: Path) -> None:
    configured = gitops.git("config", "--get", "merge.safedata.driver", cwd=root, check=False)
    if Path(sys.executable).as_posix() not in configured:
        install(root)


def cmd_normalize(args) -> int:
    """Clean filter: canonical CSV on stdout. Never fails; unreadable input passes through."""
    data = sys.stdin.buffer.read()
    try:
        text = store.normalize_text(data.decode("utf-8"), load_schema(args.schema))
        sys.stdout.buffer.write(text.encode("utf-8"))
    except Exception:
        sys.stdout.buffer.write(data)
    return 0


def cmd_merge_driver(args) -> int:
    """Merge driver: %O (base) %A (local; receives the result) %B (incoming) %L (marker size) %P (path)."""
    schema = load_schema(Path.cwd() / SCHEMA_FILE)
    try:
        base, ours, theirs = (store.read_file(p, schema) for p in (args.base, args.ours, args.theirs))
    except (ValueError, OSError) as e:
        print(f"safedata: cannot merge {args.path} record by record ({e})", file=sys.stderr)
        return 1
    result = merge(base, ours, theirs, schema)
    for note in result.notes:
        print(f"safedata: {note}", file=sys.stderr)
    if result.conflicts:
        text = store.to_text_with_conflicts(result.rows, result.conflicts, schema, size=args.marker_size)
        Path(args.ours).write_text(text, encoding="utf-8", newline="")
        print(f"safedata: {len(result.conflicts)} record(s) in conflict in {args.path}", file=sys.stderr)
        return 1
    store.write_file(args.ours, result.rows, schema)
    return 0


def cmd_validate(args) -> int:
    root = find_root()
    schema = load_schema(root / SCHEMA_FILE)
    if args.staged:
        if not gitops.git("ls-files", "--", DATA_FILE, cwd=root).strip():
            return 0
        text, where = gitops.show(root, "", DATA_FILE), f"{DATA_FILE} (staged)"
    else:
        path = Path(args.file) if args.file else root / DATA_FILE
        text, where = path.read_text(encoding="utf-8"), str(path)

    rows: list = []
    if store.has_conflicts(text):
        errors = ["The file still contains merge conflicts (lines starting with <<<<<<<). "
                  "Resolve them in the records editor or in your git tool."]
    else:
        try:
            header, rows = store.parse(text)
        except ValueError as e:
            errors = [f"cannot read the file: {e}"]
        else:
            errors = validate(header, rows, schema)
            if not errors and text != store.to_text(rows, schema):
                errors.append("The file is valid but not sorted/normalized: run 'safedata install' "
                              "in this copy, then stage the file again.")
    if errors:
        print(f"{where}: {len(errors)} problem(s):", file=sys.stderr)
        for e in errors[:50]:
            print(f"  - {e}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more", file=sys.stderr)
        return 1
    print(f"{where}: OK ({len(rows)} records)")
    return 0


# ---------------------------------------------------------------- analysis

def cmd_powerquery(args) -> int:
    root = find_root()
    schema = load_schema(root / SCHEMA_FILE)
    m_types = {"int": "Int64.Type", "float": "type number", "date": "type date",
               "bool": "type logical", "choice": "type text", "string": "type text"}
    types = ",\n        ".join(f'{{"{c.name}", {m_types[c.type]}}}' for c in schema.columns)
    print(f"// DataPath for this copy: {root / DATA_FILE}")
    print(f"""let
    // Path to records.csv, read from the cell named DataPath in this workbook
    Path = Excel.CurrentWorkbook(){{[Name="DataPath"]}}[Content]{{0}}[Column1],
    Source = Csv.Document(File.Contents(Path), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {{
        {types}
    }}, "en-US")
in
    Typed""")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="safedata", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("edit", help="open the records editor in the browser")
    p.add_argument("--port", type=int, default=0, help="port to listen on (default: any free port)")
    p.add_argument("--no-browser", action="store_true", help="print the address without opening a browser")
    p.set_defaults(func=cmd_edit)
    sub.add_parser("install", help="set up the git add-ons for this copy").set_defaults(func=cmd_install)
    p = sub.add_parser("validate", help="check records.csv against the schema")
    p.add_argument("--staged", action="store_true", help="check the version staged for commit")
    p.add_argument("--file", help="check this CSV file instead")
    p.set_defaults(func=cmd_validate)
    sub.add_parser("powerquery", help="print the Power Query code for Excel").set_defaults(func=cmd_powerquery)
    p = sub.add_parser("normalize", help="git clean filter (stdin to stdout)")
    p.add_argument("--schema", default=SCHEMA_FILE)
    p.set_defaults(func=cmd_normalize)
    p = sub.add_parser("merge-driver", help="git merge driver")
    p.add_argument("base")
    p.add_argument("ours")
    p.add_argument("theirs")
    p.add_argument("marker_size", type=int)
    p.add_argument("path")
    p.set_defaults(func=cmd_merge_driver)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
