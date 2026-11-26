# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0
"""Revisioned documents with an explicit, synchronous unit of work.

SQL transactions serialize on a durable gate row. File transactions journal
complete replacements before publishing any file; readers share the same gate.
Never await inside a transaction: run a complete synchronous command in a thread.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from pathlib import Path

from orchestrate.persistence.errors import (
    StorageConflictError,
    StorageCorruptionError,
    StorageUnavailableError,
    StorageValidationError,
)

_ACTIVE_FILE = ContextVar("file_document_transaction", default=None)
_ACTIVE_SQL = ContextVar("sql_document_transaction", default=None)
_FILE_STATES = {}
_STATES_LOCK = threading.Lock()
_LOCATIONS = {
    "preflows": "workflow_storage/preflow",
    "psops": "workflow_storage/psop",
    "executions": "workflow_storage/execution_records",
    "solution_packages": "solution_packages",
    "sandbox_reports": "workflow_storage/sandbox/reports",
    "sandbox_templates": "workflow_storage/sandbox/templates",
}


def data_root(conf=None):
    from common.util.config_util import get_root_path

    if conf is None:
        from common.util.config_util import get_conf

        conf = get_conf()
    return Path(os.environ.get("ORCH_DATA_DIR") or conf.get("data_dir") or Path(get_root_path()) / "data").resolve()


def _validate(namespace, key=None):
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", namespace):
        raise StorageValidationError("Invalid document namespace")
    if key is not None and (
        not isinstance(key, str)
        or not key
        or len(key) > 180
        or any(c in key for c in '/\\<>:"|?*')
        or key in (".", "..")
        or key.split(".")[0].upper()
        in ({"CON", "PRN", "AUX", "NUL"} | {f"COM{i}" for i in range(1, 10)} | {f"LPT{i}" for i in range(1, 10)})
        or key.endswith((".", " "))
        or any(ord(c) < 32 for c in key)
    ):
        raise StorageValidationError("Invalid document key")


def _encode(value):
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise StorageValidationError("Document must be valid JSON") from exc


def _atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
        if os.name != "nt":
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class _FileState:
    def __init__(self, root):
        self.root = root
        self.lock = threading.RLock()
        self.journal = root / ".store" / "committed.json"
        self.faulted = False
        self.handle = None

    def acquire_process_lock(self):
        if self.handle is not None:
            return
        self.journal.parent.mkdir(parents=True, exist_ok=True)
        lock_directory = Path(tempfile.gettempdir()) / "openan-storage-locks"
        lock_directory.mkdir(parents=True, exist_ok=True)
        lock_name = hashlib.sha256(str(self.root).casefold().encode()).hexdigest() + ".lock"
        handle = (lock_directory / lock_name).open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                if not handle.read(1):
                    handle.write(b"0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise StorageUnavailableError("File storage already has a writer") from exc
        self.handle = handle

    def apply(self, operations):
        for relative, content in operations.items():
            target = (self.root / relative).resolve()
            if not target.is_relative_to(self.root):
                raise StorageCorruptionError("Invalid journal path")
            if content is None:
                target.unlink(missing_ok=True)
            else:
                _atomic(target, content)

    def recover(self):
        self.acquire_process_lock()
        if self.journal.exists():
            try:
                payload = json.loads(self.journal.read_text(encoding="utf-8"))
                operations = payload["operations"]
                if hashlib.sha256(_encode(operations).encode()).hexdigest() != payload["sha256"]:
                    raise ValueError("Invalid checksum")
                self.apply(operations)
                self.journal.unlink()
                self.faulted = False
            except Exception as exc:
                self.faulted = True
                raise StorageUnavailableError("File transaction needs recovery") from exc
        elif self.faulted:
            raise StorageUnavailableError("File storage is unavailable")


class FileDocuments:
    def __init__(self, root, locations=None):
        self.root = Path(root).resolve()
        self.locations = {**_LOCATIONS, **(locations or {})}
        with _STATES_LOCK:
            self._state = _FILE_STATES.setdefault(str(self.root), _FileState(self.root))

    def _relative(self, namespace, key):
        _validate(namespace, key)
        directory = self.locations.get(namespace, "runtime/" + namespace)
        return f"{directory}/{key}.json"

    def _metadata(self, namespace, key):
        digest = hashlib.sha256((namespace + ":" + key).encode()).hexdigest()
        return f".store/revisions/{digest}.json"

    def _read(self, relative):
        active = _ACTIVE_FILE.get()
        if active is not None and active[0] is self._state and relative in active[1]:
            content = active[1][relative]
            return None if content is None else json.loads(content)
        path = self.root / relative
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            raise StorageCorruptionError("Unreadable stored document") from exc

    @contextmanager
    def transaction(self):
        active = _ACTIVE_FILE.get()
        if active is not None:
            if active[0] is not self._state or active[3] != threading.get_ident():
                raise StorageValidationError("Cannot mix storage roots or threads in a transaction")
            try:
                yield self
            except BaseException:
                active[2]["rollback"] = True
                raise
            return
        with self._state.lock:
            self._state.recover()
            staged = {}
            token = _ACTIVE_FILE.set((self._state, staged, {"rollback": False}, threading.get_ident()))
            try:
                yield self
                if _ACTIVE_FILE.get()[2]["rollback"]:
                    raise StorageUnavailableError("File transaction was rolled back")
                if staged:
                    journal = {"operations": staged, "sha256": hashlib.sha256(_encode(staged).encode()).hexdigest()}
                    _atomic(self._state.journal, _encode(journal))
                    try:
                        self._state.apply(staged)
                        self._state.journal.unlink()
                    except Exception as exc:
                        self._state.faulted = True
                        raise StorageUnavailableError("File transaction needs recovery") from exc
            finally:
                _ACTIVE_FILE.reset(token)

    def get(self, namespace, key):
        with self.transaction():
            return copy.deepcopy(self._read(self._relative(namespace, key)))

    def revision(self, namespace, key):
        with self.transaction():
            meta = self._read(self._metadata(namespace, key))
            if meta is not None:
                return int(meta["revision"])
            return 1 if self._read(self._relative(namespace, key)) is not None else 0

    def save(self, namespace, key, payload, expected_revision=None):
        if not isinstance(payload, dict):
            raise StorageValidationError("Document must be an object")
        with self.transaction():
            old = self.revision(namespace, key)
            if expected_revision is not None and old != expected_revision:
                raise StorageConflictError("Document revision changed")
            staged = _ACTIVE_FILE.get()[1]
            staged[self._relative(namespace, key)] = _encode(payload)
            staged[self._metadata(namespace, key)] = _encode({"revision": old + 1})
            return old + 1

    def delete(self, namespace, key, expected_revision=None):
        with self.transaction():
            if expected_revision is not None and self.revision(namespace, key) != expected_revision:
                raise StorageConflictError("Document revision changed")
            if self.get(namespace, key) is None:
                return False
            staged = _ACTIVE_FILE.get()[1]
            staged[self._relative(namespace, key)] = None
            staged[self._metadata(namespace, key)] = _encode({"revision": self.revision(namespace, key) + 1})
            return True

    def list(self, namespace):
        _validate(namespace)
        with self.transaction():
            directory = self.locations.get(namespace, "runtime/" + namespace)
            keys = {p.stem for p in (self.root / directory).glob("*.json")}
            for relative in _ACTIVE_FILE.get()[1]:
                if relative.startswith(directory + "/"):
                    keys.add(Path(relative).stem)
            return [value for key in sorted(keys) if (value := self.get(namespace, key)) is not None]

    def now(self):
        return time.time()


class SqlDocuments:
    def __init__(self, provider):
        self.provider = provider
        self._initialized = False
        self._init_lock = threading.Lock()

    def _connection(self):
        try:
            return self.provider.connection()
        except Exception as exc:
            raise StorageUnavailableError("Document storage unavailable") from exc

    def initialize(self):
        if self._initialized:
            return
        with self._init_lock:
            if self._initialized:
                return
            conn = self._connection()
            try:
                with conn.cursor() as cur:
                    text = "LONGTEXT" if self.provider.mode == "mysql" else "TEXT"
                    cur.execute(
                        f"CREATE TABLE IF NOT EXISTS orchestration_documents ("
                        f"namespace VARCHAR(64) NOT NULL, document_key VARCHAR(180) NOT NULL, "
                        f"payload {text} NOT NULL, revision BIGINT NOT NULL, "
                        f"PRIMARY KEY(namespace, document_key))"
                        + (
                            " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin"
                            if self.provider.mode == "mysql"
                            else ""
                        )
                    )
                    cur.execute("CREATE TABLE IF NOT EXISTS orchestration_uow_gate (id INTEGER PRIMARY KEY)")
                    if self.provider.mode == "mysql":
                        cur.execute("INSERT IGNORE INTO orchestration_uow_gate(id) VALUES(1)")
                    else:
                        cur.execute("INSERT INTO orchestration_uow_gate(id) VALUES(1) ON CONFLICT DO NOTHING")
                conn.commit()
                self._initialized = True
            except Exception as exc:
                conn.rollback()
                raise StorageUnavailableError("Cannot initialize document storage") from exc
            finally:
                conn.close()

    def check_ready(self):
        conn = self._connection()
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM orchestration_uow_gate WHERE id=1")
                if cur.fetchone() is None:
                    raise StorageUnavailableError("Missing storage transaction gate")
                cur.execute("SELECT namespace,document_key,payload,revision FROM orchestration_documents WHERE 1=0")
            self._initialized = True
        except Exception as exc:
            raise StorageUnavailableError("Run the storage migration before cluster startup") from exc
        finally:
            conn.rollback()
            conn.close()

    @contextmanager
    def transaction(self):
        active = _ACTIVE_SQL.get()
        if active is not None:
            if active[0] is not self.provider:
                raise StorageValidationError("Cannot mix SQL backends in a transaction")
            try:
                yield self
            except BaseException:
                active[3]["rollback"] = True
                raise
            return
        self.initialize()
        conn = self._connection()
        token = None
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT id FROM orchestration_uow_gate WHERE id=1 FOR UPDATE")
                if cur.fetchone() is None:
                    raise StorageCorruptionError("Missing transaction gate")
            token = _ACTIVE_SQL.set((self.provider, conn, threading.get_ident(), {"rollback": False}))
            from database.utils.connection_provider import connection_scope

            with connection_scope(self.provider):
                yield self
            if _ACTIVE_SQL.get()[3]["rollback"]:
                raise StorageUnavailableError("SQL transaction was rolled back")
            conn.commit()
        except BaseException as exc:
            with suppress(Exception):
                conn.rollback()
            import psycopg2
            import pymysql

            if isinstance(exc, (psycopg2.Error, pymysql.MySQLError)):
                from database.utils.storage_errors import raise_storage_error

                raise_storage_error(exc, "Document transaction failed")
            raise
        finally:
            if token is not None:
                _ACTIVE_SQL.reset(token)
            with suppress(Exception):
                conn.close()

    def _cursor(self):
        active = _ACTIVE_SQL.get()
        if active[2] != threading.get_ident():
            raise StorageValidationError("SQL transaction crossed a thread boundary")
        return active[1].cursor()

    def get(self, namespace, key):
        _validate(namespace, key)
        with self.transaction(), self._cursor() as cur:
            cur.execute(
                "SELECT payload FROM orchestration_documents WHERE namespace=%s AND document_key=%s", (namespace, key)
            )
            row = cur.fetchone()
            if row is None:
                return None
            try:
                return json.loads(row[0])
            except (TypeError, ValueError) as exc:
                raise StorageCorruptionError("Unreadable stored document") from exc

    def revision(self, namespace, key):
        _validate(namespace, key)
        with self.transaction(), self._cursor() as cur:
            cur.execute(
                "SELECT revision FROM orchestration_documents WHERE namespace=%s AND document_key=%s", (namespace, key)
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def save(self, namespace, key, payload, expected_revision=None):
        if not isinstance(payload, dict):
            raise StorageValidationError("Document must be an object")
        _validate(namespace, key)
        content = _encode(payload)
        with self.transaction(), self._cursor() as cur:
            old = self.revision(namespace, key)
            if expected_revision is not None and old != expected_revision:
                raise StorageConflictError("Document revision changed")
            if old:
                cur.execute(
                    "UPDATE orchestration_documents SET payload=%s, revision=%s WHERE namespace=%s AND document_key=%s",
                    (content, old + 1, namespace, key),
                )
            else:
                cur.execute(
                    "INSERT INTO orchestration_documents(namespace,document_key,payload,revision) VALUES(%s,%s,%s,%s)",
                    (namespace, key, content, 1),
                )
            return old + 1

    def delete(self, namespace, key, expected_revision=None):
        _validate(namespace, key)
        with self.transaction(), self._cursor() as cur:
            old = self.revision(namespace, key)
            if expected_revision is not None and old != expected_revision:
                raise StorageConflictError("Document revision changed")
            if self.get(namespace, key) is None:
                return False
            cur.execute(
                "UPDATE orchestration_documents SET payload=%s,revision=%s WHERE namespace=%s AND document_key=%s",
                ("null", old + 1, namespace, key),
            )
            return True

    def list(self, namespace):
        _validate(namespace)
        with self.transaction(), self._cursor() as cur:
            cur.execute(
                "SELECT payload FROM orchestration_documents WHERE namespace=%s ORDER BY document_key", (namespace,)
            )
            try:
                return [value for row in cur.fetchall() if (value := json.loads(row[0])) is not None]
            except (TypeError, ValueError) as exc:
                raise StorageCorruptionError("Unreadable stored document") from exc

    def now(self):
        with self.transaction(), self._cursor() as cur:
            expression = (
                "UNIX_TIMESTAMP(CURRENT_TIMESTAMP(6))"
                if self.provider.mode == "mysql"
                else "EXTRACT(EPOCH FROM clock_timestamp())"
            )
            cur.execute("SELECT " + expression)
            return float(cur.fetchone()[0])


def bound_sql_connection(provider):
    active = _ACTIVE_SQL.get()
    if active is None:
        return None
    if active[0] is not provider or active[2] != threading.get_ident():
        raise StorageValidationError("SQL transaction used by a different backend/thread")
    return _TransactionConnection(active[1])


class _TransactionConnection:
    """Legacy handlers borrow the transaction; only its owner can commit/close."""

    def __init__(self, connection):
        self._connection = connection

    def cursor(self, *args, **kwargs):
        return self._connection.cursor(*args, **kwargs)

    def commit(self):
        pass

    def close(self):
        pass

    def rollback(self):
        # A legacy handler that swallows its failure must still abort the UoW.
        _ACTIVE_SQL.get()[3]["rollback"] = True

    def __getattr__(self, name):
        return getattr(self._connection, name)
