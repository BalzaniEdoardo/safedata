# safedata

A proof of principle for keeping a small shared dataset safe, while it stays easy to edit and analyse in Excel.

**The problem:** the records and the analysis live in the same Excel file. One filter-then-paste can quietly corrupt the records, and nobody can tell what changed or when.

**The idea:** split the work into three parts that never touch each other.

| Part | Who | How |
|---|---|---|
| **Store** | nobody edits it directly | `data/records.csv` + `data/schema.yaml` in git: every change is recorded with who, when and what |
| **Edit** | staff | double-click **edit**, change things in a normal Excel sheet, then double-click **submit** |
| **Analyse** | staff | their own workbook pulls the records via Power Query; **Data > Refresh All** gets the latest data and keeps their filters and sort |

Staff never see git, Python or the CSV.

## For staff

Each person has a copy of this folder. In `launchers/`, double-click the `.cmd` files on Windows or the `.command` files on Mac:

- **update**: gets the latest records. Then click *Refresh All* in your analysis workbook.
- **edit**: opens the records as an editable workbook. Change values, add rows at the bottom (leave `id` blank), or choose `delete` in the `_action` column. Sorting and filtering in this workbook is fine. Save and close the file when you're done.
- **submit**: checks your edits, shows a summary, and asks you to confirm. It then saves them to the shared history. If something is wrong, nothing is saved, and you get a plain explanation of what to fix.

To set up your analysis workbook once, follow [docs/EXCEL_SETUP.md](docs/EXCEL_SETUP.md).

## How it stays safe

- **Validation:** `data/schema.yaml` defines each column's type, allowed values, limits, and whether it is required or unique. Every path into the data is checked against it: submit, the pre-commit hook, and CI (`.github/workflows/validate.yml`).
- **Canonical file:** a git *clean filter* sorts the records by `id` and normalizes values (ISO dates, `true`/`false`, consistent numbers) whenever the file is staged. Diffs show only real changes, and nobody's commit gets blocked because the order or formatting differs.
- **Concurrent edits:** an edit remembers the version it started from. On submit, each change is applied only if that value hasn't been changed by someone else in the meantime. The same applies to `git pull`, which uses a record-level *merge driver*. Edits to different records, or to different fields of one record, combine automatically. When two people add records at once, both are kept (one is renumbered). Two different edits of the same field are a **conflict**: nothing is overwritten, and a readable report says which record and field, and what each side wrote.
- **Deleting is explicit:** a row missing from the editing workbook is *not* deleted, because it may have been filtered out. Only `_action = delete` removes a record.
- **History:** `uv run safedata history` (or `--id 42`) prints a record-level changelog: who changed which field, from what to what, and when.

## For the maintainer

Requirements on each machine: [git](https://git-scm.com) and [uv](https://docs.astral.sh/uv/). uv installs Python and the dependencies automatically on first run.

```sh
git clone <shared-repo> records && cd records
uv run safedata install      # clean filter, merge driver, pre-commit hook (the launchers do this too)
uv run safedata validate     # check the records
uv run safedata history      # who changed what
uv run safedata powerquery   # Power Query code for Excel, generated from the schema
uv run pytest                # tests
```

The shared repository can be any git host: a private GitHub/GitLab repository, a self-hosted Forgejo, or even a bare repository on a network drive.

**Resolving a conflict:** if `update`/`edit`/`submit` report a conflict, the pull was aborted and nothing changed. Run `git pull`, read `MERGE_CONFLICTS.txt`, fix the listed values in `data/records.csv` (it contains the local values), then `git add data/records.csv && git commit`.

**Changing the schema:** edit `data/schema.yaml` (and `records.csv`, if you add a column), commit both together, and tell the analysts to re-paste the `safedata powerquery` code.

## Layout

```
data/records.csv        the records (canonical CSV)
data/schema.yaml        column definitions and rules
src/safedata/           schema, store, changeset, merge, excel_edit, gitops, cli
launchers/              double-click wrappers for edit / submit / update
docs/EXCEL_SETUP.md     connecting an analysis workbook
tests/
```

**Adding another editing front-end** (e.g. a small web form): it only needs to produce a `Changeset` relative to a base commit. `changeset.apply`, validation and the git steps in `cli.cmd_submit` stay the same.
