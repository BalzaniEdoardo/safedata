# safedata

safedata is part of a workflow for keeping a table of records safe: the records are a CSV file in a git repository, described by a schema. safedata provides an editor that checks every change against the schema and writes the file, and sets up git to check, standardize and merge the records whenever changes are recorded or combined. Git keeps the history, and Excel or any other program can analyse the records without being able to change them.

**Documentation: [balzaniedoardo.github.io/safedata](https://balzaniedoardo.github.io/safedata/)**, which explains the workflow, why it is built this way, and how to set it up and use it. To start a new dataset, use the template [template-records](https://github.com/BalzaniEdoardo/template-records).

## Installing

The only requirement is [git](https://git-scm.com).

macOS and Linux:

```sh
curl -LsSf https://raw.githubusercontent.com/BalzaniEdoardo/safedata/main/install.sh | sh
```

Windows (PowerShell):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://raw.githubusercontent.com/BalzaniEdoardo/safedata/main/install.ps1 | iex"
```

The installer ([install.sh](install.sh), [install.ps1](install.ps1)) installs [uv](https://docs.astral.sh/uv/) if it is missing, then safedata as a command, without administrator rights. Running it again updates safedata. The next steps, getting a copy of a dataset and setting it up, are described in [Setting up](https://balzaniedoardo.github.io/safedata/setup/).

Run `safedata --help` for the list of commands, and `safedata <command> --help` for each one.

## Development

```sh
git clone https://github.com/BalzaniEdoardo/safedata
cd safedata
uv run pytest                                 # tests
uv run --group docs mkdocs serve              # documentation preview at http://127.0.0.1:8000
uv tool install --editable .                  # the safedata command, running this copy of the code
```

`tests/test_git_e2e.py` checks the editor and the git add-ons end to end: it creates a bare repository and two clones in a temporary folder, and commits, merges and pushes in them, with an empty home folder and no global git config so that personal settings do not interfere. These tests are marked `git`; to skip them, run `uv run pytest -m "not git"`.

CI (`.github/workflows/ci.yml`) runs the tests on Linux, macOS and Windows, runs the installers on clean machines, and builds the documentation. On `main`, the documentation is then published on GitHub Pages, once all of these have passed.

### Code layout

```
src/safedata/
  schema.py      loading schema.yaml; value normalization; validation; input specs for editors
  store.py       reading and writing the records CSV in standard form; conflict blocks
  changeset.py   changes between two versions of the records; applying them with conflict checks
  merge.py       three-way merge of two versions, used by the merge driver
  dataset.py     finding the dataset folder from safedata.toml
  webapp.py      the editor's HTTP server
  web/           the editor page (HTML, JavaScript, CSS)
  hooks.py       the safedata block in a clone's pre-commit hook
  clonecheck.py  what `safedata check` reports
  gitops.py      read-only git queries, and the config writes done by install
  cli.py         the commands
docs/            the documentation (MkDocs)
tests/
  fixtures/schema.yaml   the schema used by the tests
```

Another editor can reuse the same core: it has to produce a `Changeset` relative to the version it started from, and `changeset.apply`, `schema.validate` and `store.write_file` do the rest.
