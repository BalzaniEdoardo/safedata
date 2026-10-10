"""Command-line entry point: `safedata <command>`.

Staff-facing commands (edit, submit, update) are wrapped by the double-click
launchers. The rest are used by git (normalize, merge-driver, validate) or by
whoever maintains the repository.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import subprocess
import sys
from pathlib import Path

from . import gitops, store
from .changeset import apply, diff
from .excel_edit import changeset_from_edits, export, read_edits
from .merge import conflict_report, merge
from .schema import load_schema, validate

DATA_FILE = "data/records.csv"
SCHEMA_FILE = "data/schema.yaml"
EDIT_FILE = "edits/records_edit.xlsx"
CONFLICT_FILE = "MERGE_CONFLICTS.txt"


class Abort(Exception):
    """Stop with a friendly message (no traceback)."""


# ---------------------------------------------------------------- git plumbing

def cmd_normalize(args) -> int:
    """Clean filter: canonical CSV on stdout. Never fails."""
    data = sys.stdin.buffer.read()
    try:
        schema = load_schema(args.schema)
        text = store.normalize_text(data.decode("utf-8"), schema)
        sys.stdout.buffer.write(text.encode("utf-8"))
    except Exception:
        sys.stdout.buffer.write(data)
    return 0


def cmd_validate(args) -> int:
    root = gitops.repo_root()
    schema = load_schema(root / SCHEMA_FILE)
    if args.staged:
        if not gitops.git("ls-files", "--", DATA_FILE, cwd=root).strip():
            return 0
        text, where = gitops.show(root, "", DATA_FILE), f"{DATA_FILE} (staged)"
    else:
        path = Path(args.file) if args.file else root / DATA_FILE
        text, where = path.read_text(encoding="utf-8"), str(path)
    try:
        header, rows = store.parse(text)
    except ValueError as e:
        print(f"{where}: cannot read the file: {e}", file=sys.stderr)
        return 1
    errors = validate(header, rows, schema)
    if not errors and text != store.to_text(rows, schema):
        errors.append("The file is valid but not sorted/normalized. Run 'safedata install' "
                      "on this machine, then stage the file again.")
    if errors:
        print(f"{where}: {len(errors)} problem(s) found, nothing was committed:", file=sys.stderr)
        for e in errors[:50]:
            print(f"  - {e}", file=sys.stderr)
        if len(errors) > 50:
            print(f"  ... and {len(errors) - 50} more", file=sys.stderr)
        return 1
    print(f"{where}: OK ({len(rows)} records)")
    return 0


def cmd_merge_driver(args) -> int:
    """git merge driver: %O (base) %A (ours, receives the result) %B (theirs) %P (path)."""
    schema = load_schema(Path.cwd() / SCHEMA_FILE)
    try:
        base, ours, theirs = (store.read_file(p, schema) for p in (args.base, args.ours, args.theirs))
    except (ValueError, OSError) as e:
        print(f"safedata: cannot merge {args.path} automatically ({e})", file=sys.stderr)
        return 1
    result = merge(base, ours, theirs, schema)
    store.write_file(args.ours, result.rows, schema)
    for note in result.notes:
        print(f"safedata: {note}", file=sys.stderr)
    if result.conflicts:
        report = conflict_report(result, args.path)
        Path(CONFLICT_FILE).write_text(report, encoding="utf-8")
        print(report, file=sys.stderr)
        return 1
    return 0


def cmd_install(args) -> int:
    root = gitops.repo_root()
    install(root, verbose=True)
    return 0


def install(root: Path, verbose: bool = False) -> None:
    py = Path(sys.executable).as_posix()
    gitops.set_config(root, "filter.safedata.clean", f'"{py}" -m safedata normalize')
    gitops.set_config(root, "merge.safedata.name", "safedata record-level merge")
    gitops.set_config(root, "merge.safedata.driver", f'"{py}" -m safedata merge-driver %O %A %B %P')
    hooks = root / gitops.git("rev-parse", "--git-path", "hooks", cwd=root).strip()
    hooks.mkdir(parents=True, exist_ok=True)
    hook = hooks / "pre-commit"
    hook.write_text(f'#!/bin/sh\nexec "{py}" -m safedata validate --staged\n', encoding="utf-8", newline="\n")
    hook.chmod(0o755)
    if verbose:
        print("Installed the safedata clean filter, merge driver and pre-commit check for this copy.")


def ensure_installed(root: Path) -> None:
    configured = gitops.git("config", "--get", "merge.safedata.driver", cwd=root, check=False).strip()
    if Path(sys.executable).as_posix() not in configured:
        install(root)


# ---------------------------------------------------------------- staff commands

def cmd_edit(args) -> int:
    root = _prepare()
    edit_path = root / EDIT_FILE
    if edit_path.exists():
        print(f"You already have edits in progress: {edit_path}")
        print("Submit them first (double-click 'submit'), or delete that file to start over.")
        _open(edit_path)
        return 0
    _sync(root)
    schema = load_schema(root / SCHEMA_FILE)
    rows = store.read_file(root / DATA_FILE, schema)
    export(rows, schema, gitops.head(root), edit_path)
    print(f"Opening {edit_path} ({len(rows)} records).")
    print("Make your changes, save and close the file, then double-click 'submit'.")
    _open(edit_path)
    return 0


def cmd_submit(args) -> int:
    root = _prepare()
    edit_path = Path(args.file) if args.file else root / EDIT_FILE
    if not edit_path.exists():
        raise Abort(f"There is nothing to submit: {edit_path} does not exist. Double-click 'edit' first.")
    schema = load_schema(root / SCHEMA_FILE)

    sheet = read_edits(edit_path, schema)
    base = store.read_text(gitops.show(root, sheet.base_commit, DATA_FILE), schema)
    cs, errors = changeset_from_edits(base, sheet, schema)
    if errors:
        _fail("Your edits were not submitted. Please fix these problems in the workbook:", errors)
    if cs.is_empty():
        print("You made no changes, so there is nothing to submit.")
        _archive(edit_path, "unchanged")
        return 0

    _sync(root)
    current = store.read_file(root / DATA_FILE, schema)
    result = apply(current, cs, schema)
    if result.conflicts:
        _fail("Someone else changed the same values since you started editing. "
              "Nothing was submitted. Please check these with your colleagues:",
              [c.describe() for c in result.conflicts])
    errors = validate(schema.names, result.rows, schema)
    if errors:
        _fail("Your edits were not submitted. Please fix these problems in the workbook:", errors)

    for i, key in result.assigned.items():
        cs.adds[i] = {**cs.adds[i], schema.key: key}
    lines = cs.describe(schema) + [f"note: {n}" for n in result.notes]
    print(f"Your changes: {cs.counts()}")
    for line in lines[:100]:
        print(f"  {line}")
    if len(lines) > 100:
        print(f"  ... and {len(lines) - 100} more")
    if not args.yes and input("\nSubmit these changes? Type y and press Enter: ").strip().lower() not in ("y", "yes"):
        print("Not submitted. Your workbook is untouched; you can keep editing it.")
        return 1

    store.write_file(root / DATA_FILE, result.rows, schema)
    name = gitops.user_name(root)
    gitops.commit(root, [DATA_FILE], f"{cs.counts()} (by {name})\n\n" + "\n".join(lines))
    _publish(root)
    _archive(edit_path, "submitted")
    print("Done. Your changes are saved in the shared history.")
    return 0


def cmd_update(args) -> int:
    root = _prepare()
    _sync(root)
    revs = gitops.log_revisions(root, DATA_FILE)
    if revs:
        _, author, date, _ = revs[-1]
        print(f"The records are up to date (last change {date} by {author}).")
    print("In your analysis workbook, click Data > Refresh All to load them.")
    return 0


def cmd_history(args) -> int:
    root = gitops.repo_root()
    schema = load_schema(root / SCHEMA_FILE)
    prev: list = []
    for rev, author, date, subject in gitops.log_revisions(root, DATA_FILE):
        try:
            rows = store.read_text(gitops.show(root, rev, DATA_FILE), schema)
        except ValueError:
            print(f"{date} {author}: (file unreadable in this version) {subject}")
            continue
        cs = diff(prev, rows, schema)
        prev = rows
        if args.id:
            lines = [ln for ln in cs.describe(schema) if f"record {args.id}:" in ln or f"record {args.id}," in ln
                     or ln == f"- record {args.id} deleted"]
        elif len(cs.adds) > 20 and not cs.updates and not cs.deletes:
            lines = [f"+ {len(cs.adds)} records added"]
        else:
            lines = cs.describe(schema)
        if lines:
            print(f"{date}  {author}  [{rev[:8]}]")
            for line in lines:
                print(f"    {line}")
    return 0


def cmd_powerquery(args) -> int:
    root = gitops.repo_root()
    schema = load_schema(root / SCHEMA_FILE)
    m_types = {"int": "Int64.Type", "float": "type number", "date": "type date",
               "bool": "type logical", "choice": "type text", "string": "type text"}
    types = ",\n        ".join(f'{{"{c.name}", {m_types[c.type]}}}' for c in schema.columns)
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
    print(f"\n// DataPath for this copy: {(root / DATA_FILE)}", file=sys.stderr)
    return 0


# ---------------------------------------------------------------- helpers

def _prepare() -> Path:
    try:
        root = gitops.repo_root()
    except gitops.GitError:
        raise Abort("This folder is not a copy of the records repository.")
    ensure_installed(root)
    if gitops.is_modified(root, DATA_FILE):
        raise Abort(f"{DATA_FILE} has been changed directly on this computer and not saved to the history.\n"
                    "Please ask the maintainer to look at it before editing.")
    return root


def _sync(root: Path) -> None:
    ok, message = gitops.pull(root)
    if not ok:
        raise Abort("Could not combine your copy with the shared records:\n\n" + message +
                    "\nNothing was changed. Please send this message to the maintainer.")


def _publish(root: Path) -> None:
    for _ in range(3):
        ok, message = gitops.push(root)
        if ok:
            return
        _sync(root)  # someone pushed meanwhile: merge their changes, then retry
    raise Abort("Your change is saved on this computer but could not be sent to the shared repository:\n"
                f"{message}\nIt will be sent next time you run update, edit or submit.")


def _archive(path: Path, label: str) -> None:
    dest = path.parent / "archive" / f"{path.stem}-{label}-{dt.datetime.now():%Y%m%d-%H%M%S}{path.suffix}"
    dest.parent.mkdir(parents=True, exist_ok=True)
    path.replace(dest)


def _fail(header: str, problems: list[str]) -> None:
    raise Abort(header + "\n" + "\n".join(f"  - {p}" for p in problems[:50]))


def _open(path: Path) -> None:
    if os.environ.get("SAFEDATA_NO_OPEN"):
        return
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except OSError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="safedata", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("edit", help="open the records in an editable workbook").set_defaults(func=cmd_edit)
    p = sub.add_parser("submit", help="validate and save the edits from the workbook")
    p.add_argument("--file", help=f"workbook to submit (default: {EDIT_FILE})")
    p.add_argument("--yes", action="store_true", help="do not ask for confirmation")
    p.set_defaults(func=cmd_submit)
    sub.add_parser("update", help="get the latest records").set_defaults(func=cmd_update)
    p = sub.add_parser("history", help="record-level change history")
    p.add_argument("--id", help="only show changes to this record")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("validate", help="check the records against the schema")
    p.add_argument("--staged", action="store_true", help="check the version staged for commit")
    p.add_argument("--file", help="check this CSV file instead")
    p.set_defaults(func=cmd_validate)
    p = sub.add_parser("normalize", help="git clean filter (stdin -> stdout)")
    p.add_argument("--schema", default=SCHEMA_FILE)
    p.set_defaults(func=cmd_normalize)
    p = sub.add_parser("merge-driver", help="git merge driver")
    for name in ("base", "ours", "theirs", "path"):
        p.add_argument(name)
    p.set_defaults(func=cmd_merge_driver)
    sub.add_parser("install", help="set up git integration for this copy").set_defaults(func=cmd_install)
    sub.add_parser("powerquery", help="print the Power Query (M) code for Excel").set_defaults(func=cmd_powerquery)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Abort as e:
        print(f"\n{e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
