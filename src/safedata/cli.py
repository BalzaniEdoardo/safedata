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

from . import clonecheck, dataset, gitops, hooks, store
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


def cmd_check(args) -> int:
    ds = dataset.find()
    if not _in_git(ds):
        raise dataset.DatasetError(f"{ds.root} is not inside a git repository")
    root = gitops.repo_root(ds.root)
    records = ds.records_path.relative_to(root).as_posix()
    hook = gitops.hooks_dir(root) / "pre-commit"
    problems = clonecheck.clone_problems(
        records,
        config=gitops.safedata_config(root),
        hook_text=hook.read_text(encoding="utf-8") if hook.is_file() else None,
        attrs=gitops.attributes(root, records, list(clonecheck.ATTRIBUTES)),
    )
    if not problems:
        print(f"This clone ({root}) is set up: the git add-ons are configured for {records}.")
        return 0
    print(f"This clone ({root}) is not fully set up:", file=sys.stderr)
    for p in problems:
        print(f"  - {p.message}", file=sys.stderr)
    if any(p.fixed_by_install for p in problems):
        print("Run `safedata install` in this folder to set up the git add-ons.", file=sys.stderr)
    if not all(p.fixed_by_install for p in problems):
        print(f"Add this line to .gitattributes and commit it:\n"
              f"  {records}  filter=safedata merge=safedata diff=safedata text eol=lf", file=sys.stderr)
    return 1


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
    hooks_dir = gitops.hooks_dir(root)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    hook = hooks_dir / "pre-commit"
    existing = hook.read_text(encoding="utf-8") if hook.is_file() else None
    try:
        updated = hooks.update_pre_commit(existing, py)
    except hooks.ForeignHook as e:
        print(f"safedata: {e}", file=sys.stderr)
        return
    if updated != existing:
        hook.write_text(updated, encoding="utf-8", newline="\n")
    hook.chmod(hook.stat().st_mode | 0o111)  # keep existing permissions, ensure it can run


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

M_TYPES = {"int": "Int64.Type", "float": "type number", "date": "type date",
           "bool": "type logical", "choice": "type text", "string": "type text"}


def power_query(ds: dataset.Dataset) -> str:
    """Power Query (M) code that loads the records file of this clone into Excel.

    The path is written into the query: Excel for Mac asks for a data gateway when
    the path comes from a cell instead. Options: UTF-8, quoted values may contain
    commas, numbers read with "." as decimal separator whatever the computer's region.
    """
    schema = ds.load_schema()
    m_string = lambda s: '"' + s.replace('"', '""') + '"'  # M doubles quotes inside strings
    types = ",\n        ".join(f"{{{m_string(c.name)}, {M_TYPES[c.type]}}}" for c in schema.columns)
    return f"""let
    Source = Csv.Document(File.Contents({m_string(str(ds.records_path))}), [Delimiter=",", Encoding=65001, QuoteStyle=QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars=true]),
    Typed = Table.TransformColumnTypes(Promoted, {{
        {types}
    }}, "en-US")
in
    Typed
"""


def cmd_powerquery(args) -> int:
    sys.stdout.write(power_query(dataset.find()))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="safedata",
        description="Edit and check a table of records kept in a git repository.",
        epilog="Commands work on the dataset that contains the current folder: the nearest folder\n"
               "upwards with a safedata.toml. None of them pulls, commits or pushes; that is left\n"
               "to git. Run `safedata <command> --help` for details on a command.",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True, metavar="<command>")

    def command(name, func, summary, description):
        p = sub.add_parser(name, help=summary, description=description,
                           formatter_class=argparse.RawDescriptionHelpFormatter)
        p.set_defaults(func=func)
        return p

    p = command("edit", cmd_edit, "open the records editor in the browser", """\
Start the records editor for the dataset containing the current folder and open
it in the default browser. Saving in the editor validates the edits against the
schema and writes the records file; committing it is left to git.
The editor runs until you press Ctrl+C.""")
    p.add_argument("--port", type=int, default=0, help="port to listen on (default: any free port)")
    p.add_argument("--no-browser", action="store_true", help="print the editor's address without opening a browser")

    command("install", cmd_install, "set up the git add-ons in this clone", """\
Configure this clone of the dataset repository to use the safedata add-ons for
the records file: the clean filter, the merge driver, the word-diff setting
(written to .git/config) and the check in .git/hooks/pre-commit. Settings
in .git/ are not copied between clones, so every clone needs this once;
`safedata edit` runs it automatically. Running it again is harmless.""")

    command("check", cmd_check, "check that this clone is set up for the git add-ons", """\
Report whether this clone of the dataset repository is set up: the git settings
written by `safedata install` are present and point to an installed tool, the
pre-commit hook runs the safedata check, and .gitattributes assigns the add-ons
to the records file. Changes nothing. Exits with status 1 if anything is
missing, and says how to fix it.""")

    p = command("validate", cmd_validate, "check the records against the schema", """\
Check the records file against the schema and list every problem. Exits with
status 1 if there are problems, 0 otherwise.""")
    p.add_argument("--staged", action="store_true",
                   help="check the version staged for commit instead of the file on disk "
                        "(used by the pre-commit hook; passes when there is nothing to check)")
    p.add_argument("--file", metavar="CSV", help="check this CSV file instead of the dataset's records file")

    command("powerquery", cmd_powerquery, "print Power Query code for Excel", """\
Print the Power Query (M) code that loads this clone's records file into an
Excel table, with the column types from the schema. The file's path is written
into the query, so each person generates it in their own clone. To get a file
to copy from:  safedata powerquery > query.txt
See the dataset's docs/EXCEL_SETUP.md for where to paste it.""")

    command("normalize", cmd_normalize, "git clean filter (called by git)", """\
Called by git when the records file is staged, not by people. Reads the file on
standard input and writes it to standard output sorted by the key column, with
every value in its standard form. Input that cannot be read (wrong columns,
merge conflict markers) is written back unchanged and left to `validate`.""")

    p = command("merge-driver", cmd_merge_driver, "git merge driver (called by git)", """\
Called by git, not by people, when a merge or pull changed the records file on
both sides. Git passes the arguments configured in .git/config:
    merge-driver %O %A %B %L %P
Changes to different records, or to different columns of a record, are combined
and written to LOCAL. Records changed differently on both sides are written as
git conflict blocks, one record per block, and the command exits with status 1
so git reports a conflict.""")
    p.add_argument("base", metavar="BASE", help="%%O: temporary file with the common ancestor's version")
    p.add_argument("ours", metavar="LOCAL", help="%%A: temporary file with this branch's version; receives the result")
    p.add_argument("theirs", metavar="INCOMING", help="%%B: temporary file with the version being merged in")
    p.add_argument("marker_size", metavar="MARKER_SIZE", type=int, help="%%L: length of the conflict markers (7 by default)")
    p.add_argument("path", metavar="PATH", help="%%P: path of the records file in the repository, used in messages")

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
