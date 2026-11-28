# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Immutable PSOP versions and append-only execution observation."""

from contextlib import closing, contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import rfc8785
from loguru import logger

from common.util.config_util import get_conf
from orchestrate.persistence import current_context
from orchestrate.workflow_storage_instance import get_workflow_storage

PREFIX = "dev.openan.workflow."
START = PREFIX + "execution.started.v1"
FINISH = PREFIX + "execution.finished.v1"
GAP = PREFIX + "execution.gap.declared.v1"
WINDOW = 1024


class ObservationConflict(ValueError):
    def __init__(self, code, index=None, **fields):
        super().__init__(code)
        self.code = code
        self.index = index
        self.fields = fields


def encoded(data):
    return rfc8785.dumps(data).decode()


def observation_enabled():
    from common.util.config_util import get_conf
    from orchestrate.server.external_auth import external_auth_mode

    # Account channels are governed by the centre's permission model; until it lands the
    # catalogue is shared, so any authenticated caller may use observation in that mode.
    return (bool(os.environ.get("OPENAN_EXECUTION_HOSTS"))
            or external_auth_mode(get_conf()) in {"user", "custom"})


def _snapshot(psop):
    definition = psop.model_dump(mode="json", exclude={"created_at"})
    if definition.get("workflow_host") is None:
        definition.pop("workflow_host", None)
    for step in definition["steps"]:
        for task in step["subtasks"]:
            task.pop("status", None)
    body = encoded(definition)
    return definition, body, sha256(body.encode()).hexdigest()


def psop_revision(psop):
    return _snapshot(psop)[2]


SCHEMA = (
    """CREATE TABLE IF NOT EXISTS observation_versions (
      psop_id VARCHAR(128) NOT NULL, revision VARCHAR(64) NOT NULL, definition TEXT NOT NULL,
      PRIMARY KEY (psop_id, revision))""",
    """CREATE TABLE IF NOT EXISTS observation_runs (
      id VARCHAR(36) PRIMARY KEY, source VARCHAR(255) NOT NULL, psop_id VARCHAR(128) NOT NULL,
      revision VARCHAR(64) NOT NULL, psop_name TEXT NOT NULL, started_at VARCHAR(40) NOT NULL,
      next_cursor BIGINT NOT NULL, contiguous BIGINT NOT NULL, highest BIGINT NOT NULL,
      last_received_at VARCHAR(40) NOT NULL, terminal_received_at VARCHAR(40),
      terminal_seq BIGINT, gap_count INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS observation_events (
      run_id VARCHAR(36) NOT NULL, seq BIGINT NOT NULL, event_id VARCHAR(36) NOT NULL,
      source VARCHAR(255) NOT NULL, cursor_id BIGINT NOT NULL, body TEXT NOT NULL,
      PRIMARY KEY (run_id, seq), UNIQUE (source, event_id), UNIQUE (run_id, cursor_id))""",
    """CREATE TABLE IF NOT EXISTS observation_task_ids (
      run_id VARCHAR(36) NOT NULL, task_ref VARCHAR(64) NOT NULL, task_id VARCHAR(36) NOT NULL,
      PRIMARY KEY (run_id, task_ref), UNIQUE (run_id, task_id))""",
    """CREATE TABLE IF NOT EXISTS observation_steps (
      run_id VARCHAR(36) NOT NULL, step_ref VARCHAR(64) NOT NULL, first_seq BIGINT NOT NULL,
      PRIMARY KEY (run_id, step_ref))""",
    """CREATE TABLE IF NOT EXISTS observation_attempts (
      run_id VARCHAR(36) NOT NULL, task_id VARCHAR(36) NOT NULL, attempt INTEGER NOT NULL,
      state TEXT NOT NULL, PRIMARY KEY (run_id, task_id, attempt))""",
)


class ExecutionObservationStore:
    def __init__(self, mode, path=None):
        self.mode = mode
        self.path = path

    @contextmanager
    def transaction(self, *, write=False):
        with current_context().backend.operation_scope():
            if self.mode == "file":
                if write:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    conn = sqlite3.connect(self.path, timeout=10)
                else:
                    conn = sqlite3.connect(self.path.resolve().as_uri() + "?mode=ro", timeout=10, uri=True)
            else:
                from database.utils.db_connection import create_connection
                conn = create_connection()
                if conn is None:
                    raise OSError("Observation database unavailable")
            with closing(conn), closing(conn.cursor()) as cursor:
                def query(sql, params=()):
                    if self.mode != "file":
                        sql = sql.replace("?", "%s")
                    cursor.execute(sql, params)
                    return cursor

                try:
                    if self.mode == "file":
                        query("BEGIN IMMEDIATE" if write else "BEGIN")
                    elif self.mode == "mysql":
                        # The existing pooled provider starts an empty transaction at checkout.
                        conn.rollback()
                        query("SET TRANSACTION ISOLATION LEVEL READ COMMITTED" if write
                              else "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                        conn.begin()
                    else:
                        query("SET TRANSACTION ISOLATION LEVEL READ COMMITTED" if write
                              else "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ")
                    yield query
                    conn.commit()
                except BaseException:
                    conn.rollback()
                    raise

    def initialize(self):
        if self.mode == "file":
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=10)) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
        with self.transaction(write=True) as query:
            for ddl in SCHEMA:
                if self.mode == "mysql":
                    ddl = ddl.replace(" TEXT ", " LONGTEXT ") + (
                        " ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_bin"
                    )
                query(ddl)

    def _insert(self, query, table, columns, values):
        suffix = (" ON DUPLICATE KEY UPDATE " + columns[0] + "=" + columns[0]
                  if self.mode == "mysql" else " ON CONFLICT DO NOTHING")
        query(f"INSERT INTO {table} ({','.join(columns)}) "
              f"VALUES ({','.join('?' for _ in values)}){suffix}", values)

    def publish(self, psop):
        definition, body, revision = _snapshot(psop)
        with self.transaction(write=True) as query:
            self._insert(query, "observation_versions", ("psop_id", "revision", "definition"),
                         (psop.id, revision, body))
        return definition | {"revision": revision}

    def published_revision(self, psop):
        _, _, revision = _snapshot(psop)
        with self.transaction() as query:
            return revision if query(
                "SELECT 1 FROM observation_versions WHERE psop_id=? AND revision=?",
                (psop.id, revision),
            ).fetchone() else None

    def version(self, psop_id, revision):
        with self.transaction() as query:
            return self._version(query, psop_id, revision)

    @staticmethod
    def _version(query, psop_id, revision):
        row = query("SELECT definition FROM observation_versions WHERE psop_id=? AND revision=?",
                    (psop_id, revision)).fetchone()
        return json.loads(row[0]) | {"revision": revision} if row else None

    def ingest(self, events, allowed_psops):
        first = events[0]
        run_id, source = first["subject"], first["source"]
        locking = "" if self.mode == "file" else " FOR UPDATE"
        now = datetime.now(timezone.utc)
        received = now.isoformat()
        expiry = now - timedelta(days=7)
        with self.transaction(write=True) as query:
            ordered = sorted(enumerate(events), key=lambda item: int(item[1]["seq"]))
            _, earliest = ordered[0]
            if earliest["type"] == START:
                data = earliest["data"]
                if "*" not in allowed_psops and data["psop_id"] not in allowed_psops:
                    raise ObservationConflict("PSOP_FORBIDDEN", ordered[0][0])
                version = self._version(query, data["psop_id"], data["psop_revision"])
                if version is None:
                    raise ObservationConflict("REVISION_NOT_FOUND", ordered[0][0])
                if datetime.fromisoformat(earliest["time"]) >= expiry:
                    self._insert(query, "observation_runs",
                                 ("id", "source", "psop_id", "revision", "psop_name", "started_at",
                                  "next_cursor", "contiguous", "highest", "last_received_at"),
                                 (run_id, source, data["psop_id"], data["psop_revision"],
                                  version["name"], datetime.fromisoformat(earliest["time"]).astimezone(timezone.utc).isoformat(),
                                  1, 0, 0, received))
            row = query("SELECT source,psop_id,revision,next_cursor,contiguous,highest,"
                        "terminal_seq,deleted,last_received_at,terminal_received_at,gap_count "
                        "FROM observation_runs WHERE id=?" + locking,
                        (run_id,)).fetchone()
            if not row:
                if earliest["type"] == START:
                    raise ObservationConflict("EXECUTION_CLOSED")
                raise ObservationConflict("START_REQUIRED")
            owner, psop_id, revision, cursor, contiguous, highest, terminal, deleted, last, terminal_at, gaps = row
            if owner != source:
                raise ObservationConflict("OWNER_MISMATCH")
            if "*" not in allowed_psops and psop_id not in allowed_psops:
                raise ObservationConflict("PSOP_FORBIDDEN")
            closed = deleted or _window_expired(last, terminal_at, cutoff=expiry)
            version = self._version(query, psop_id, revision)
            accepted = duplicates = 0
            previous_contiguous = contiguous
            previous_cursor = cursor
            for index, event in ordered:
                seq = int(event["seq"])
                body = encoded(event)
                existing = query("SELECT run_id,seq,body FROM observation_events "
                                 "WHERE source=? AND event_id=?", (source, event["id"])).fetchone()
                if existing:
                    if tuple(existing) != (run_id, seq, body):
                        raise ObservationConflict("EVENT_ID_CONFLICT", index)
                    duplicates += 1
                    continue
                if closed:
                    raise ObservationConflict("EXECUTION_CLOSED", index)
                if seq > contiguous + WINDOW:
                    # The entire request rolls back. Recovery can only use
                    # positions committed before this batch.
                    last = min(seq - 1, previous_contiguous + WINDOW)
                    occupied = query(
                        "SELECT seq FROM observation_events WHERE run_id=? AND seq>? AND seq<=? "
                        "AND cursor_id<? ORDER BY seq", (run_id, previous_contiguous, last, previous_cursor),
                    ).fetchall()
                    raise ObservationConflict(
                        "SEQUENCE_WINDOW", index, contiguous_through=str(previous_contiguous),
                        missing_ranges=_missing_ranges(previous_contiguous + 1, last, occupied),
                    )
                if terminal is not None and seq >= terminal:
                    raise ObservationConflict("TERMINAL_SEQUENCE_CONFLICT", index)
                if event["type"] == FINISH:
                    if seq <= highest:
                        raise ObservationConflict("TERMINAL_SEQUENCE_CONFLICT", index)
                    terminal = seq
                    terminal_at = received
                if event["type"] == GAP:
                    gaps += 1
                self._validate_binding(query, run_id, version, event, index)
                self._insert(query, "observation_events",
                             ("run_id", "seq", "event_id", "source", "cursor_id", "body"),
                             (run_id, seq, event["id"], source, cursor, body))
                if query("SELECT event_id FROM observation_events WHERE run_id=? AND seq=?",
                         (run_id, seq)).fetchone() != (event["id"],):
                    raise ObservationConflict("SEQUENCE_OR_EVENT_ID_CONFLICT", index)
                cursor += 1
                accepted += 1
                highest = max(highest, seq)
                if seq == contiguous + 1:
                    for (stored_seq,) in query(
                        "SELECT seq FROM observation_events WHERE run_id=? AND seq>? ORDER BY seq",
                        (run_id, contiguous),
                    ).fetchall():
                        if stored_seq != contiguous + 1:
                            break
                        contiguous = stored_seq
            if accepted:
                if contiguous > previous_contiguous:
                    self._project_attempts(query, run_id, previous_contiguous, contiguous)
                query("UPDATE observation_runs SET next_cursor=?,contiguous=?,highest=?,terminal_seq=?,"
                      "gap_count=?,last_received_at=?,terminal_received_at=? WHERE id=?",
                      (cursor, contiguous, highest, terminal, gaps, received, terminal_at, run_id))
            ranges = []
            expected = contiguous + 1
            for (seq,) in query("SELECT seq FROM observation_events WHERE run_id=? AND seq>? ORDER BY seq",
                                (run_id, contiguous)).fetchall():
                if seq > expected:
                    ranges.append([str(expected), str(seq - 1)])
                expected = seq + 1
            return {"execution_id": run_id, "accepted": accepted, "duplicates": duplicates,
                    "contiguous_through": str(contiguous), "observed_through": str(highest),
                    "missing_ranges": ranges[:100], "missing_ranges_truncated": len(ranges) > 100}

    def _validate_binding(self, query, run_id, version, event, index):
        data = event["data"]
        if "step_ref" not in data:
            return
        step_index = int(data["step_ref"][1:])
        if step_index >= len(version["steps"]):
            raise ObservationConflict("INVALID_STEP_REF", index)
        position = (run_id, data["step_ref"], int(event["seq"]))
        self._insert(query, "observation_steps", ("run_id", "step_ref", "first_seq"), position)
        query("UPDATE observation_steps SET first_seq=? WHERE run_id=? AND step_ref=? AND first_seq>?",
              (position[2], *position[:2], position[2]))
        if "task_ref" not in data:
            return
        task_index = int(data["task_ref"].split("/t")[1])
        if task_index >= len(version["steps"][step_index]["subtasks"]):
            raise ObservationConflict("INVALID_TASK_REF", index)
        binding = (run_id, data["task_ref"], data["task_id"])
        self._insert(query, "observation_task_ids", ("run_id", "task_ref", "task_id"), binding)
        row = query("SELECT task_id FROM observation_task_ids WHERE run_id=? AND task_ref=?",
                    binding[:2]).fetchone()
        if row != (data["task_id"],):
            raise ObservationConflict("TASK_BINDING_CONFLICT", index)

    def _project_attempts(self, query, run_id, before, through):
        rows = query("SELECT body FROM observation_events WHERE run_id=? AND seq>? AND seq<=? ORDER BY seq",
                     (run_id, before, through)).fetchall()
        for (body,) in rows:
            event = json.loads(body)
            data = event["data"]
            if "task_id" not in data:
                continue
            key = (run_id, data["task_id"], data["attempt"])
            previous = query("SELECT state FROM observation_attempts WHERE run_id=? AND task_id=? AND attempt=?",
                             key).fetchone()
            if previous:
                state = json.loads(previous[0])
                if "outcome" in state and "outcome" in data and state["outcome"] != data["outcome"]:
                    state["outcome_conflict"] = True
                elif "outcome" not in state:
                    state.update(data)
                query("UPDATE observation_attempts SET state=? WHERE run_id=? AND task_id=? AND attempt=?",
                      (encoded(state), *key))
            else:
                self._insert(query, "observation_attempts", ("run_id", "task_id", "attempt", "state"),
                             (*key, encoded(data)))

    def list_runs(self):
        with self.transaction() as query:
            rows = query("""SELECT r.id,r.psop_id,r.revision,r.psop_name,r.started_at,r.contiguous,
                         r.highest,r.terminal_seq,r.last_received_at,r.terminal_received_at,
                         r.gap_count,r.next_cursor,e.body,
                         (SELECT COUNT(*) FROM observation_steps s WHERE s.run_id=r.id AND s.first_seq<=r.contiguous)
                         FROM observation_runs r LEFT JOIN observation_events e
                         ON e.run_id=r.id AND e.seq=r.terminal_seq
                         WHERE r.deleted=0 ORDER BY r.started_at DESC""").fetchall()
        return [_summary(*row) for row in rows]

    def detail(self, run_id):
        with self.transaction() as query:
            row = query("SELECT psop_id,revision,psop_name,started_at,contiguous,highest,terminal_seq,"
                        "last_received_at,terminal_received_at,gap_count,next_cursor "
                        "FROM observation_runs WHERE id=? AND deleted=0", (run_id,)).fetchone()
            if row is None:
                return None
            psop_id, revision, _, _, contiguous, _, terminal, *_ = row
            graph = self._version(query, psop_id, revision)
            terminal_row = query("SELECT body FROM observation_events WHERE run_id=? AND seq=?",
                                 (run_id, terminal)).fetchone() if terminal is not None else None
            count, = query("SELECT COUNT(*) FROM observation_steps WHERE run_id=? AND first_seq<=?",
                           (run_id, contiguous)).fetchone()
            attempts = query("SELECT state FROM observation_attempts WHERE run_id=? ORDER BY task_id,attempt",
                             (run_id,)).fetchall()
            steps = query("SELECT body FROM observation_events WHERE run_id=? AND seq<=? "
                          "AND body LIKE ? ORDER BY seq",
                          (run_id, contiguous, f'%"type":"{PREFIX}step.%')).fetchall()
            timeline = query("SELECT body FROM observation_events WHERE run_id=? ORDER BY seq DESC LIMIT 1001",
                             (run_id,)).fetchall()
        record = _summary(run_id, *row, terminal_row[0] if terminal_row else None, count)
        return _record(record, graph, attempts, steps, timeline)

    def events(self, run_id, after, limit, through=None, *, timeline=False):
        with self.transaction() as query:
            row = query("SELECT next_cursor,psop_id,revision FROM observation_runs WHERE id=? AND deleted=0",
                        (run_id,)).fetchone()
            if row is None:
                return None
            until = min(through, row[0] - 1) if through is not None else row[0] - 1
            rows = query("SELECT cursor_id,body FROM observation_events WHERE run_id=? "
                         "AND cursor_id>? AND cursor_id<=? ORDER BY cursor_id LIMIT ?",
                         (run_id, after, until, limit)).fetchall()
            graph = self._version(query, row[1], row[2]) if timeline else None
        page = []
        for cursor, body in rows:
            event = json.loads(body)
            if timeline:
                event = _timeline_event(event, graph)
            page.append({"cursor": str(cursor), "event": event})
        return page

    def hide(self, run_id):
        with self.transaction(write=True) as query:
            return query("UPDATE observation_runs SET deleted=1 WHERE id=? AND deleted=0",
                         (run_id,)).rowcount == 1

    def stream_close_state(self, run_id, cursor):
        with self.transaction() as query:
            row = query("SELECT terminal_seq,contiguous,next_cursor,last_received_at,terminal_received_at "
                        "FROM observation_runs WHERE id=? AND deleted=0", (run_id,)).fetchone()
        if row is None:
            return "closed", str(cursor)
        terminal, contiguous, next_cursor, last, terminal_at = row
        last_cursor = next_cursor - 1
        if cursor < last_cursor:
            return None
        if terminal is not None and terminal == contiguous:
            return "complete", str(last_cursor)
        if _window_expired(last, terminal_at):
            return "expired", str(last_cursor)
        return None


def _window_expired(last, terminal_at, *, cutoff=None):
    cutoff = cutoff or datetime.now(timezone.utc) - timedelta(days=7)
    return datetime.fromisoformat(terminal_at or last) < cutoff


def _missing_ranges(first, last, occupied):
    ranges = []
    for (seq,) in occupied:
        if first < seq:
            ranges.append([str(first), str(seq - 1)])
        first = seq + 1
    if first <= last:
        ranges.append([str(first), str(last)])
    return ranges


def _step_history(rows):
    steps = {}
    for (body,) in rows:
        event = json.loads(body)
        kind = event["type"]
        if kind not in {PREFIX + "step.started.v1", PREFIX + "step.finished.v1"}:
            continue
        data = event["data"]
        step = steps.setdefault(data["step_ref"], {"step_ref": data["step_ref"]})
        if kind == PREFIX + "step.started.v1":
            step.setdefault("started_at", event["time"])
        elif "outcome" not in step:
            step.update(data | {"completed_at": event["time"]})
    return list(steps.values())


def _record(record, graph, attempts, step_rows, timeline_rows):
    tasks = {}
    for (body,) in attempts:
        attempt = json.loads(body)
        task = tasks.setdefault(attempt["task_id"], {"attempts": {}})
        task["attempts"][attempt["attempt"]] = attempt
        previous_attempts = task["attempts"]
        task.clear()
        task["attempts"] = previous_attempts
        task.update(attempt)
        step_index = int(attempt["step_ref"][1:])
        task_index = int(attempt["task_ref"].split("/t")[1])
        graph["steps"][step_index]["subtasks"][task_index]["status"] = {
            "succeeded": "success", "failed": "failed", "cancelled": "failed",
        }.get(attempt.get("outcome"), "running")

    timeline = []
    for (body,) in reversed(timeline_rows[:1000]):
        entry = _timeline_event(json.loads(body), graph)
        if entry:
            timeline.append(entry)
    record.update(final_psop=graph,
                  step_history=_step_history(step_rows),
                  execution_history=sorted(tasks.values(), key=lambda task: task["task_ref"]),
                  projection_anomaly=any(
                      attempt.get("outcome_conflict") for task in tasks.values()
                      for attempt in task["attempts"].values()
                  ),
                  events=timeline, events_truncated=len(timeline_rows) > 1000)
    return record


def _summary(run_id, psop_id, revision, name, started, contiguous, highest, terminal,
             last, terminal_at, gaps, next_cursor, terminal_body, step_count):
    terminal_event = json.loads(terminal_body) if terminal_body else None
    outcome = terminal_event["data"]["outcome"] if terminal_event else None
    expired = _window_expired(last, terminal_at)
    coverage = ("expired_incomplete" if expired and (contiguous != highest or gaps or not terminal) else
                "gapped" if contiguous != highest or gaps else
                "complete" if terminal is not None else "collecting")
    return {
        "execution_id": run_id, "psop_id": psop_id, "psop_revision": revision,
        "psop_name": name, "started_at": started, "last_received_at": last,
        "completed_at": terminal_event["time"] if terminal_event else None,
        "reported_outcome": outcome,
        "status": {"succeeded": "success", "failed": "failed", "cancelled": "stopped"}.get(outcome, "running"),
        "step_count": step_count, "event_coverage": coverage, "declared_gaps": gaps,
        "capture_status": terminal_event["data"].get("capture_status") if terminal_event else None,
        "projected_through": str(contiguous), "observed_through": str(highest),
        "last_cursor": str(next_cursor - 1),
    }


def _timeline_event(event, graph):
    kind = event["type"].removeprefix(PREFIX).removesuffix(".v1")
    data = dict(event["data"])
    if "step_ref" in data:
        data["step"] = graph["steps"][int(data["step_ref"][1:])]["name"]
    if "task_ref" in data:
        data["subtask_index"] = int(data["task_ref"].split("/t")[1])
    interaction = data.get("interaction", {})
    interaction_type = {
        ("negotiation", "requested"): "negotiation_request",
        ("negotiation", "resolved"): "negotiation_resolved",
        ("negotiation", "failed"): "negotiation_failed",
        ("agent_call", "sent"): "agent_request",
        ("agent_call", "received"): "agent_response",
        ("agent_call", "failed"): "agent_response",
    }.get((interaction.get("kind"), interaction.get("phase")))
    event_type = interaction_type or {
        "step.started": "step_start", "step.finished": "step_complete",
        "task.started": "task_request", "task.progressed": "task_status_changed",
        "task.finished": "task_response",
        "execution.finished": "complete" if data.get("outcome") == "succeeded" else "error",
    }.get(kind)
    if event_type is None:
        return None
    data["status"] = {"succeeded": "success", "failed": "failed",
                      "cancelled": "failed"}.get(data.get("outcome"), "running")
    if "result" in data:
        data["outputs"] = data["result"].get("outputs", {})
    return {"type": event_type, "data": data, "timestamp": datetime.fromisoformat(event["time"]).timestamp(),
            "seq": event["seq"]}


def _store_location():
    conf = get_conf()
    mode = str(conf.get("persistence_mode", "file")).lower()
    path = Path(get_workflow_storage().execution_dir).parent / "execution_observation.sqlite3" if mode == "file" else None
    return mode, path, current_context().backend


def observation_store_for_read():
    mode, path, _ = _store_location()
    return ExecutionObservationStore(mode, path)


def observation_store():
    return _initialized_store(*_store_location())


def publish_saved_psop(psop):
    if observation_enabled():
        try:
            observation_store().publish(psop)
        except Exception as exc:
            logger.warning("Could not register the saved PSOP revision ({})", type(exc).__name__)


def backfill_psop_revisions():
    if not observation_enabled():
        return
    from common.custom import InterfaceType
    from orchestrate.handlers.dispatch import get_storage_handler

    try:
        store = observation_store()
        list_psops = get_storage_handler(InterfaceType.GET_ALL_PSOP)
        load_psop = get_storage_handler(InterfaceType.GET_PSOP_BY_ID)
        for item in list_psops.handle():
            psop = load_psop.handle(item.workflow_id)
            if psop is not None and store.published_revision(psop) is None:
                publish_saved_psop(psop)
    except Exception as exc:
        logger.warning("Could not backfill existing PSOP revisions ({})", type(exc).__name__)


@lru_cache(maxsize=8)
def _initialized_store(mode, path, backend):
    store = ExecutionObservationStore(mode, path)
    store.initialize()
    return store
