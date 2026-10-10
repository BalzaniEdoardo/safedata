# safedata

Tools for a small table of records kept as a CSV file in a git repository: a local web editor that validates edits and writes the file, and git add-ons that keep the file sorted, merge it record by record and check it before each commit.

This repository contains only the code. The records live in their own repository, which describes its columns in a `schema.yaml`. To start one, copy [template-records](https://github.com/BalzaniEdoardo/template-records); its README covers setup, editing, conflicts and the schema format.

## What the tool does and does not do

Each part has one job:

| Part | Job | Does not |
|---|---|---|
| `safedata edit` | shows the records as a table, validates edits against the schema, writes the records file | pull, commit, push or keep any history |
| git add-ons | sort the records file when staged, merge it record by record, mark changed cells in word diffs, reject invalid commits | replace any git command |
| git, with any git client | pull, diff, commit, push, history | |

Everything that involves history (reviewing, committing, merging, browsing past versions) is done with git, so any git client works.

## Installing

Requires [git](https://git-scm.com) and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/BalzaniEdoardo/safedata
```

This puts a `safedata` command on the PATH, in an environment of its own. For development, install from a local clone instead; `--editable` makes code changes take effect without reinstalling:

```sh
uv tool install --editable ~/Code/safedata
```

## Commands

Every command works on the dataset containing the current folder: the nearest folder upwards with a `safedata.toml`, the way git finds `.git`. Outside a dataset folder, commands stop with an error.

| Command | What it does |
|---|---|
| `safedata edit` | opens the editor in the default browser; stop it with Ctrl+C |
| `safedata install` | configures the git add-ons in this clone (also run by `edit`) |
| `safedata validate` | checks the records file against the schema (`--staged` checks the version staged for commit) |
| `safedata powerquery` | prints Power Query code for loading the records in Excel, generated from the schema |
| `safedata normalize` | the git clean filter: reads the file on stdin, writes it sorted and normalized |
| `safedata merge-driver` | the git merge driver |

The last two are called by git, not by people.

## A dataset folder

```
safedata.toml       records = "data/records.csv"
                    schema = "data/schema.yaml"
data/records.csv
data/schema.yaml
.gitattributes      data/records.csv  filter=safedata merge=safedata diff=safedata text eol=lf
```

`safedata.toml` marks the folder and gives the two paths relative to it. `.gitattributes` assigns the add-ons to the records file. `safedata install` defines what the add-on names mean, in the clone's `.git/config`, which git does not copy between clones:

```ini
[filter "safedata"]
    clean = "<tool python>" -m safedata normalize
[merge "safedata"]
    driver = "<tool python>" -m safedata merge-driver %O %A %B %L %P
[diff "safedata"]
    wordRegex = [^,]+
```

It also adds `safedata validate --staged` to `.git/hooks/pre-commit`, inside a block marked `# >>> safedata >>>` / `# <<< safedata <<<`. Running `install` again replaces only that block, and the rest of an existing hook is kept. In an existing shell hook the block goes right after the first line, so it runs even if the hook ends with `exec`. A hook in another language is left unchanged, and `install` prints the line to add to it. In a clone without these settings, git ignores the attributes and treats the records file as plain text.

## How the git add-ons behave

- **Clean filter.** When the records file is staged, rows are sorted by the key column and every value is written in one form: dates as `YYYY-MM-DD`, booleans as `true`/`false`, one number format, UTF-8, LF line endings. A diff then contains only changed values, whichever program last wrote the file. A file that cannot be read, or that contains conflict markers, passes through unchanged and is left to validation.
- **Merge driver.** Merges by record and by column. Changes to different records, or to different columns of one record, are combined. Records added on both sides are both kept, and the incoming one is renumbered if its number is taken. A column changed differently on both sides, or a record edited on one side and deleted on the other, is written as a standard git conflict block containing the two versions of that record, and the driver prints which records are affected and how to resolve them.
- **Word diff.** `git diff --word-diff` treats each cell as a word, so changed cells are marked inside a line.
- **Pre-commit hook.** Rejects a staged records file that breaks the schema, is not in normalized form, or still contains conflict markers, and lists the problems.

## The editor

`safedata edit` starts a server on 127.0.0.1 on a free port and opens the page. Requests for data must carry a random token that is only in the page address, so other web pages cannot read or change the records.

- The page builds each column's input from the schema (dropdown, date picker, text) and sends edited cells to the server for checking, so all rules live in `schema.py`.
- **Save** sends the edits as a changeset: the old and new value of each changed cell, plus added and deleted records. The server applies each change only if the file still holds the old value, so edits saved after the file changed on disk (for example after a `git pull`) cannot silently overwrite someone else's change. It then validates the whole table and writes the file.
- If the records file contains conflict markers, the page shows both versions of each conflicting record and writes the file with the chosen ones. Staging the file and committing the merge are left to git.
- The page also shows, read-only, the git branch and which records differ from the last commit.

## Code layout

```
src/safedata/
  schema.py      loading schema.yaml; value normalization; validation; input specs for editors
  store.py       reading and writing the canonical CSV; reading and writing conflict blocks
  changeset.py   changes between two versions of the records; applying them with conflict checks
  merge.py       three-way merge of two versions, used by the merge driver
  dataset.py     finding the dataset folder from safedata.toml
  webapp.py      the editor's HTTP server
  web/           the editor page (HTML, JavaScript, CSS)
  gitops.py      read-only git queries, and the config writes done by install
  cli.py         the commands
tests/
  fixtures/schema.yaml   the schema used by the tests
```

Another editor can reuse the same core: it has to produce a `Changeset` relative to the version it started from, then `changeset.apply`, `schema.validate` and `store.write_file` do the rest.

## Development

```sh
git clone https://github.com/BalzaniEdoardo/safedata
cd safedata
uv run pytest
```

`uv run` creates the project environment on first use. CI runs the same tests (`.github/workflows/tests.yml`).
