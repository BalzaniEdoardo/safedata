"""Command-line entry point: `safedata <command>`.

  edit          open the records editor in the browser (writes the records file)
  install       set up the git add-ons for this copy of the dataset repository
  validate      check the records against the schema (also run by the pre-commit hook)
  powerquery    print the Power Query code for Excel analysis workbooks
  normalize     git clean filter (stdin to stdout)
  merge-driver  git merge driver

Commands work on the dataset that contains the current folder (the nearest
folder upwards with a safedata.toml). None of them pulls, commits or pushes;
that is left to git.
"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path

from . import dataset, gitops, store
from .merge import merge
from .schema import validate
from .webapp import serve


# ---------------------------------------------------------------- editor

def cmd_edit(args) -> int:
    ds = dataset.find()
    if not ds.records_path.exists():
        print(f"{ds.records_path} not found (set in {dataset.MARKER}).", file=sys.stderr)
        return 1
    if _in_git(ds):
        ensure_installed(gitops.repo_root(ds.root))
    server, url = serve(ds, args.port)
    print(f"Dataset folder: {ds.root}")
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
    ds = dataset.find()
    install(gitops.repo_root(ds.root))
    print(f"Set up for this copy: clean filter (sorts {ds.records} when staged), merge driver "
          f"(merges record by record), word diff, and the pre-commit check.")
    return 0


def _in_git(ds: dataset.Dataset) -> bool:
    try:
        gitops.repo_root(ds.root)
        return True
    except (gitops.GitError, OSError):
        return False


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
        text = store.normalize_text(data.decode("utf-8"), dataset.find().load_schema())
        sys.stdout.buffer.write(text.encode("utf-8"))
    except Exception:
        sys.stdout.buffer.write(data)
    return 0


def conflict_steps(ds: dataset.Dataset, path: str) -> str:
    """How to finish a merge that left conflicts in the records file. `path` is as git shows it."""
    return (f"To resolve, in the dataset folder {ds.root}:\n"
            "  1. keep one version of each record: in your git tool's conflict view, in a text editor\n"
            "     (keep one line per block and delete the marker lines), or with `safedata edit`;\n"
            f"  2. review the result and stage it:  git add {path}\n"
            "  3. finish the merge:                 git commit\n"
            "To cancel the merge instead:  git merge --abort\n")


def _record_list(keys) -> str:
    keys = sorted(keys, key=lambda k: (len(k), k))
    return ("record " if len(keys) == 1 else "records ") + ", ".join(keys)


def cmd_merge_driver(args) -> int:
    """Merge driver: %O (base) %A (local; receives the result) %B (incoming) %L (marker size) %P (path)."""
    ds = dataset.find()
    schema = ds.load_schema()
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
        print(f"safedata: {_record_list(result.conflicts)} in {args.path} changed differently on both sides.\n"
              "Each is marked with git conflict markers (<<<<<<< ======= >>>>>>>), one record per block.\n"
              + conflict_steps(ds, args.path), file=sys.stderr)
        return 1
    store.write_file(args.ours, result.rows, schema)
    return 0


def cmd_validate(args) -> int:
    if args.staged:
        # Run by the pre-commit hook: block only a commit that stages an invalid records
        # file. Outside a dataset, or when the records file is not in the index (never
        # added, or being deleted), there is nothing to check.
        try:
            ds = dataset.find()
        except dataset.DatasetNotFound:
            return 0
        if not gitops.git("ls-files", "--", ds.records, cwd=ds.root).strip():
            return 0
        text, where = gitops.show(ds.root, "", f"./{ds.records}"), f"{ds.records} (staged)"
    else:
        ds = dataset.find()
        path = Path(args.file) if args.file else ds.records_path
        if not path.is_file():
            raise dataset.DatasetError(f"the records file {path} does not exist")
        text, where = path.read_text(encoding="utf-8"), str(path)
    schema = ds.load_schema()

    rows: list = []
    if store.has_conflicts(text):  # checked first: a conflicted file does not parse as CSV
        try:
            _, pairs = store.parse_conflicted(text, schema)
            which = _record_list(pairs)
        except ValueError:
            which = "some records"
        print(f"{where}: still contains merge conflicts ({which}), so it cannot be committed.\n"
              + conflict_steps(ds, ds.records), file=sys.stderr)
        return 1
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
    ds = dataset.find()
    schema = ds.load_schema()
    m_types = {"int": "Int64.Type", "float": "type number", "date": "type date",
               "bool": "type logical", "choice": "type text", "string": "type text"}
    types = ",\n        ".join(f'{{"{c.name}", {m_types[c.type]}}}' for c in schema.columns)
    print(f"// DataPath for this copy: {ds.records_path}")
    print(f"""let
    // Path to the records file, read from the cell named DataPath in this workbook
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
    p = sub.add_parser("validate", help="check the records against the schema")
    p.add_argument("--staged", action="store_true", help="check the version staged for commit")
    p.add_argument("--file", help="check this CSV file instead")
    p.set_defaults(func=cmd_validate)
    sub.add_parser("powerquery", help="print the Power Query code for Excel").set_defaults(func=cmd_powerquery)
    sub.add_parser("normalize", help="git clean filter (stdin to stdout)").set_defaults(func=cmd_normalize)
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
    except dataset.DatasetNotFound as e:
        print(f"safedata: not inside a dataset folder ({e}).\n"
              "cd into your records folder and run the command again.", file=sys.stderr)
        return 1
    except dataset.DatasetError as e:
        print(f"safedata: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
