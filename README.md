# safedata

Proof of principle for a small shared dataset. The records are a CSV file in a git repository. Staff edit them through an Excel sheet with validation, and their analysis workbooks read them through Power Query. No analysis workbook writes to the records.

## Why the records are kept out of the analysis workbook

In the current setup the records and the analysis are in the same Excel file. Filtering a sheet and pasting into it can change records, and the file keeps no record of who changed what or when.

## Records, editing and analysis are separate

| Part | Who works on it | Where and how |
|---|---|---|
| Records | changed only through submit (or by the maintainer) | `data/records.csv` and `data/schema.yaml` in git; every change is a commit with author, date and the list of changed values |
| Editing | staff | **edit** exports the records to an Excel sheet; **submit** checks the sheet and records the changes |
| Analysis | staff | each person's own workbook loads the records with Power Query; **Data > Refresh All** reloads them and keeps that person's filters and sort order |

Staff use three double-click launchers and Excel. They do not run git or Python commands and do not open the CSV.

## Daily use: update, edit, submit

Each person has a copy of this folder. The launchers are in `launchers/`: the `.cmd` files for Windows, the `.command` files for Mac.

- **update** downloads the latest records. Afterwards, click *Data > Refresh All* in the analysis workbook.
- **edit** opens the records in an editable workbook. To change a value, type over it. To add a record, fill an empty row at the bottom and leave `id` blank. To delete a record, choose `delete` in its `_action` column. Sorting and filtering the sheet does not affect what gets submitted. Save and close the file when done.
- **submit** checks the edits against the schema, lists every change, and asks for confirmation before recording them. If a check fails, nothing is recorded and the message lists each problem by row and column.

Setting up an analysis workbook is a one-time step, described in [docs/EXCEL_SETUP.md](docs/EXCEL_SETUP.md).

## Checks applied to every change

- **Schema validation.** `data/schema.yaml` gives each column a type, allowed values, limits, and whether it is required or unique. Submit, the git pre-commit hook and CI (`.github/workflows/validate.yml`) all run the same check.
- **Canonical file format.** A git clean filter rewrites `records.csv` whenever it is staged: rows sorted by `id`, dates as `YYYY-MM-DD`, booleans as `true`/`false`, one number format. Diffs then contain only changed values, and a commit is never rejected because of row order or formatting.
- **Concurrent edits.** The editing workbook stores the commit it was exported from. On submit, a change is applied only if the value in the shared records still equals the value at export time. `git pull` uses a merge driver that applies the same rule record by record and field by field:
  - edits to different records, or to different fields of one record, are combined;
  - records added by two people at the same time are both kept, and the second one gets the next free `id`;
  - two different values written to the same field stop the merge. Nothing is overwritten, and the report names the record, the field and both values.
- **Deletion only on request.** A row missing from the editing workbook is not deleted, because a filter may be hiding it. Only `_action = delete` deletes a record.
- **Record history.** `uv run safedata history` lists who changed which field, from which value to which value, and on what date. `--id 42` limits the list to record 42.

## Maintainer commands

Each machine needs [git](https://git-scm.com) and [uv](https://docs.astral.sh/uv/). On first run, uv installs Python and the dependencies.

```sh
git clone <shared-repo> records && cd records
uv run safedata install      # clean filter, merge driver, pre-commit hook (the launchers also run this)
uv run safedata validate     # check the records against the schema
uv run safedata history      # record-level change history
uv run safedata powerquery   # Power Query code for Excel, generated from the schema
uv run pytest                # tests
```

The shared repository can be on any git host: a private GitHub or GitLab repository, a self-hosted Forgejo server, or a bare repository on a network drive.

## Resolving a conflict

When update, edit or submit reports a conflict, the pull has been cancelled and the local copy is unchanged. To resolve it, run `git pull`, read `MERGE_CONFLICTS.txt`, set the listed fields in `data/records.csv` to the correct values (the file holds the local values), then run `git add data/records.csv && git commit`.

## Changing the schema

Edit `data/schema.yaml`. If you add a column, add it to `records.csv` as well, and commit both files together. Then ask the analysts to paste the new output of `safedata powerquery` into their query.

## Writing rules for docs, comments and docstrings

`tools/style/rules.txt` lists phrasing that is not allowed in this repository. `tools/style/check.py` enforces it.

- **Hard rules** always fail. Examples: filler openers, marketing vocabulary, and headings that do not say what the section contains.
- **Soft rules** cover phrases that also have ordinary literal uses, such as `pay for`. The command line prints them as warnings. Put `style: allow` on the line to accept a literal use.
- **Markdown** paragraphs and list items must each be on a single line.

The check reads markdown text outside code blocks. In Python it reads comments, docstrings and string literals, not code. It runs in four places:

- in CI;
- with `python3 tools/style/check.py` (add `--changed` for uncommitted files only, or `--strict` to fail on soft matches too);
- as a Claude Code hook before every file write (`.claude/settings.json`);
- as a Claude Code check at the end of each turn, which catches files written through the shell.

## Repository layout

```
data/records.csv        the records (canonical CSV)
data/schema.yaml        column definitions and rules
src/safedata/           schema, store, changeset, merge, excel_edit, gitops, cli
launchers/              double-click wrappers for edit / submit / update
docs/EXCEL_SETUP.md     connecting an analysis workbook
tools/style/            writing rules and their checker
tests/
```

## Adding a web form or another editing tool

An editing tool only has to produce a `Changeset` relative to the commit it started from. Applying it (`changeset.apply`), validation, and the git steps in `cli.cmd_submit` work the same for any editing tool.
