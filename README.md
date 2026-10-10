# safedata

Proof of principle for a small shared dataset kept as a CSV file in a git repository. A local web editor changes the file, git records the changes, and Excel analysis workbooks read the file through Power Query.

## Why the records are kept out of the analysis workbook

In the current setup the records and the analysis are in the same Excel file. Filtering a sheet and pasting into it can change records, and the file keeps no record of who changed what or when.

## Who does what

Each part has one job.

| Part | Job | Does not |
|---|---|---|
| Editor (`safedata edit`) | shows the records as a table, validates edits, writes `data/records.csv` | pull, commit, push, or keep any history |
| git, with any git client | pull, diff, commit, push, history, merges | |
| git add-ons (`safedata install`) | keep `records.csv` sorted, merge it record by record, check it before each commit | replace any git command |
| Analysis workbooks | read `records.csv` through Power Query | write to the records |

Because the history is plain git, any git client can show it: the command line, GitHub Desktop, VS Code, GitKraken, the web page of the git server, and so on.

## Editing records

1. Get the latest commits (`git pull`, or the client's pull/sync button).
2. Start the editor: double-click `launchers/edit.command` (Mac) or `launchers/edit.cmd` (Windows), or run `uv run safedata edit`. A browser tab opens. Keep the terminal window open while editing.
3. Edit the table. Each column has an input that matches its type: dropdowns for choices and true/false, a date picker for dates. Edited cells are highlighted, and cells with a problem are outlined in red. *Add record* adds a row, and the record number is assigned on save. *Delete* marks a row for deletion until you save.
4. Click **Save to records.csv**. The editor checks every edit against `data/schema.yaml` and writes the file. If a check fails, nothing is written and the problems are listed.

After saving, `data/records.csv` shows as modified in git. Below the table, the editor lists which records differ from the last commit.

## Recording changes in git

The steps are ordinary git; use whichever client you prefer.

```sh
git diff data/records.csv               # review: one changed line per changed record
git diff --word-diff data/records.csv   # the same, with the changed cells marked
git commit -m "Add March samples" data/records.csv
git push
```

When `records.csv` is staged, the git add-ons sort and normalize it, then check it against the schema. A file that fails the check cannot be committed, whichever client is used.

## Viewing the history

```sh
git log -p --word-diff data/records.csv    # every change, cell by cell
git log -L '/^42,/,+1:data/records.csv'    # the history of record 42
git blame data/records.csv                 # last commit to touch each record
```

Graphical clients show the same history in their file-history views.

## The git add-ons

`safedata install` configures them for one copy of the repository. The editor runs it on start, so nobody has to remember. `.gitattributes` applies them to `data/records.csv`.

- **Clean filter**: when the file is staged, it sorts rows by `id` and writes values in one form (dates as `YYYY-MM-DD`, `true`/`false`, one number format, LF line endings). Diffs then contain only changed values, whatever program last wrote the file.
- **Merge driver**: merges by record and by field. Edits to different records, or to different fields of one record, are combined. When two people add records at the same time, both are kept and the second gets the next free `id`. A field changed differently on both sides, or a record edited on one side and deleted on the other, becomes a standard git conflict with one record per conflict block.
- **Word diff**: `git diff --word-diff` and `git log -p --word-diff` mark the changed cells inside a line.
- **Pre-commit hook**: runs `safedata validate --staged`, which rejects schema errors and unresolved conflict markers.

The same validation runs in CI (`.github/workflows/validate.yml`), so a commit made without the hooks is still checked.

## Resolving a merge conflict in records.csv

After a pull or merge that conflicts, `records.csv` contains standard git conflict markers. Each block holds the two versions of one record:

```
<<<<<<< local
12,2020-01-01,North,survey,Maria,7,true,
=======
12,2020-01-01,North,survey,Maria,8,true,
>>>>>>> incoming
```

There are two ways to resolve it:

- in any git client's conflict view, or in a text editor, by keeping one line per block;
- in the records editor, which detects the markers and shows both versions of each record with the differing cells highlighted. Choose one version per record, then click *Write resolved records.csv*.

Then stage `data/records.csv` and commit the merge, as for any git conflict.

## Setting up a copy

Each machine needs [git](https://git-scm.com) and [uv](https://docs.astral.sh/uv/). On first run, uv installs Python and the dependencies.

```sh
git clone <shared-repo> records && cd records
uv run safedata install     # git add-ons for this copy (the editor also runs it)
uv run safedata validate    # check the records against the schema
uv run pytest               # tests
```

The shared repository can be on any git host: a private GitHub or GitLab repository, a self-hosted Forgejo server, or a bare repository on a network drive.

## Analysis in Excel

[docs/EXCEL_SETUP.md](docs/EXCEL_SETUP.md) describes connecting an analysis workbook with Power Query. `uv run safedata powerquery` prints the query code, generated from the schema. Python users can call `safedata.load()` to get a pandas DataFrame with typed columns.

## Changing the schema

Edit `data/schema.yaml`. If you add a column, add it to `records.csv` as well, and commit both files together. Then ask the analysts to paste the new output of `safedata powerquery` into their query.

The editor reads the schema when it loads: it builds each column's input from it and sends edited cells to `schema.py` for checking. A new or changed column needs no change in the editor code.

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
src/safedata/           schema, store, changeset, merge, webapp (editor), cli; web/ holds the page
launchers/              double-click wrappers for the editor
docs/EXCEL_SETUP.md     connecting an analysis workbook
tools/style/            writing rules and their checker
tests/
```

## Adding another editor

An editor has to do one thing: turn a person's edits into a valid `records.csv`. `changeset.apply` applies a list of edits to the current records and reports edits that clash with changes made on disk in the meantime. `schema.validate` checks the result, and `store.write_file` writes it in canonical form.
