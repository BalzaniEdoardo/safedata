"""Local web editor for the records.

Serves a page on 127.0.0.1 where the records can be edited as a table. The
page builds its inputs from the schema and asks the server to check edited
cells, so all rules live in schema.py. Saving validates the changes and writes
data/records.csv. It does nothing else: the
file then shows up in git as changed, and committing it is up to the user.

The page also resolves merge conflicts left in records.csv by `git pull`,
by choosing one version per record, and shows (read-only) which records
differ from the last commit.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import gitops, store
from .changeset import Changeset, apply, diff
from .schema import Schema, canon, check_value, input_spec, load_schema, validate

DATA_FILE = "data/records.csv"
SCHEMA_FILE = "data/schema.yaml"
WEB_DIR = Path(__file__).with_name("web")
STATIC = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
          "/style.css": ("style.css", "text/css")}

_lock = threading.Lock()


class Refused(Exception):
    """The request was valid but cannot be carried out; the message is for the user."""

    def __init__(self, message: str, problems: list[str] | None = None):
        super().__init__(message)
        self.problems = problems or []


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_state(root: Path) -> dict:
    schema = load_schema(root / SCHEMA_FILE)
    text = (root / DATA_FILE).read_text(encoding="utf-8")
    state = {
        "file": DATA_FILE,
        "schema": {"key": schema.key,
                   "columns": [{**asdict(c), "input": input_spec(c)} for c in schema.columns]},
        "version": _digest(text),
        "rows": [],
        "conflicts": None,
        "uncommitted": None,
        "git": None,
    }
    if store.has_conflicts(text):
        rows, pairs = store.parse_conflicted(text, schema)
        state["rows"] = rows
        state["conflicts"] = [{"key": k, "local": o, "incoming": t}
                              for k, (o, t) in sorted(pairs.items(), key=lambda p: schema.sort_key(p[0]))]
    else:
        state["rows"] = store.read_text(text, schema)
        state["uncommitted"] = _uncommitted(root, schema, state["rows"])
    try:
        state["git"] = gitops.status(root)
    except (gitops.GitError, OSError):
        pass
    return state


def _uncommitted(root: Path, schema: Schema, rows: store.Rows) -> list[str] | None:
    """Record-level differences between the working file and the last commit."""
    try:
        committed = store.read_text(gitops.show(root, "HEAD", DATA_FILE), schema)
    except (gitops.GitError, ValueError, OSError):
        return None
    return diff(committed, rows, schema).describe(schema)


def check(root: Path, payload: dict) -> dict:
    """Problems per cell for rows being edited: {row id: {column: message}}."""
    schema = load_schema(root / SCHEMA_FILE)
    out = {}
    for uid, values in payload.get("rows", {}).items():
        problems = {c.name: p for c in schema.columns if c.name != schema.key
                    and (p := check_value(values.get(c.name, ""), c))}
        out[uid] = problems
    return {"problems": out}


def save(root: Path, payload: dict) -> dict:
    """Apply the edits sent by the page and write records.csv."""
    schema = load_schema(root / SCHEMA_FILE)
    with _lock:
        path = root / DATA_FILE
        text = path.read_text(encoding="utf-8")
        if store.has_conflicts(text):
            raise Refused("records.csv has unresolved merge conflicts. Resolve them first.")
        current = store.read_text(text, schema)
        cs = _changeset(payload, schema)
        if cs.is_empty():
            raise Refused("There are no changes to save.")
        # If the file changed on disk since the page loaded (for example after a
        # git pull), each edit is checked against the current value.
        result = apply(current, cs, schema)
        if result.conflicts:
            raise Refused("records.csv was changed on disk since this page was loaded, and some of "
                          "your edits clash with that. Nothing was saved.",
                          [c.describe() for c in result.conflicts])
        errors = validate(schema.names, result.rows, schema)
        if errors:
            raise Refused("Nothing was saved. Please fix these problems:", errors)
        store.write_file(path, result.rows, schema)
    for i, key in result.assigned.items():
        cs.adds[i] = {**cs.adds[i], schema.key: key}
    return {"saved": cs.describe(schema) + result.notes, "state": get_state(root)}


def _changeset(payload: dict, schema: Schema) -> Changeset:
    def row(values: dict) -> dict:
        return {c.name: canon(values.get(c.name, ""), c) for c in schema.columns}

    return Changeset(
        adds=[{**row(r), schema.key: ""} for r in payload.get("adds", [])],
        updates={str(k): {col: (canon(old, schema.column(col)), canon(new, schema.column(col)))
                          for col, (old, new) in cols.items()}
                 for k, cols in payload.get("updates", {}).items()},
        deletes={str(k): row(r) for k, r in payload.get("deletes", {}).items()},
    )


def resolve(root: Path, payload: dict) -> dict:
    """Write records.csv with one chosen version ("local" or "incoming") per conflicting record."""
    schema = load_schema(root / SCHEMA_FILE)
    with _lock:
        path = root / DATA_FILE
        text = path.read_text(encoding="utf-8")
        if _digest(text) != payload.get("version"):
            raise Refused("records.csv changed on disk since this page was loaded. Reload the page.")
        rows, pairs = store.parse_conflicted(text, schema)
        choices = payload.get("choices", {})
        missing = [k for k in pairs if choices.get(k) not in ("local", "incoming")]
        if missing:
            raise Refused("Choose a version for every record in conflict.", [f"record {k}" for k in missing])
        for key, (local, incoming) in pairs.items():
            chosen = local if choices[key] == "local" else incoming
            if chosen is not None:
                rows.append(chosen)
        errors = validate(schema.names, store.canonical_rows(rows, schema), schema)
        if errors:
            raise Refused("The chosen versions do not pass the checks:", errors)
        store.write_file(path, rows, schema)
    return {"state": get_state(root)}


# ---------------------------------------------------------------- HTTP server

def make_handler(root: Path, token: str):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the terminal quiet
            pass

        def _send(self, status: int, body: bytes, content_type: str):
            self.send_response(status)
            self.send_header("Content-Type", f"{content_type}; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, obj: dict):
            self._send(status, json.dumps(obj).encode("utf-8"), "application/json")

        def _authorized(self) -> bool:
            if self.headers.get("X-Token") == token:
                return True
            self._json(403, {"error": "Not allowed."})
            return False

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in STATIC:
                name, ctype = STATIC[path]
                self._send(200, (WEB_DIR / name).read_bytes(), ctype)
            elif path == "/api/state" and self._authorized():
                self._run(lambda: get_state(root))
            elif not path.startswith("/api/"):
                self._send(404, b"Not found", "text/plain")

        def do_POST(self):
            if not self._authorized():
                return
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"{}")
            actions = {"/api/check": check, "/api/save": save, "/api/resolve": resolve}
            if self.path in actions:
                self._run(lambda: actions[self.path](root, payload))
            else:
                self._json(404, {"error": "Not found"})

        def _run(self, fn):
            try:
                self._json(200, fn())
            except Refused as e:
                self._json(409, {"error": str(e), "problems": e.problems})
            except (ValueError, OSError) as e:
                self._json(500, {"error": f"Could not read or write the records: {e}"})

    return Handler


def serve(root: Path, port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    """Start the server on 127.0.0.1 and return it with the page URL."""
    token = secrets.token_urlsafe(16)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(root, token))
    url = f"http://127.0.0.1:{server.server_address[1]}/#{token}"
    return server, url
