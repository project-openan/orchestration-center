# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import json

import pytest

from database.utils import sql_dialect
from orchestrate.handlers import execution_record_processor as records


@pytest.mark.parametrize('mode', ['mysql', 'postgresql'])
def test_timestamp_contract_is_utc_for_both_sql_backends(monkeypatch, mode):
    monkeypatch.setattr(sql_dialect, 'persistence_mode', lambda: mode)
    aware = datetime(2026, 10, 19, 8, 5, tzinfo=timezone(timedelta(hours=8)))
    assert sql_dialect.timestamp_parameter(aware) == datetime(2026, 10, 19, 0, 5)
    assert sql_dialect.timestamp_iso(aware) == '2026-10-19T00:05:00+00:00'
    assert sql_dialect.timestamp_iso(datetime(2026, 10, 19, 0, 5)) == '2026-10-19T00:05:00+00:00'
    assert sql_dialect.timestamp_parameter(None) is None
    assert sql_dialect.timestamp_iso(None) is None


def test_legacy_summary_uses_offset_preserved_in_snapshot(monkeypatch):
    connection = MagicMock()
    monkeypatch.setattr(records, 'create_connection', lambda: connection)
    snapshot = {'started_at': '2026-10-19T08:05:00+08:00', 'completed_at': None}
    row = ('execution', 'workflow', 'Synthetic', datetime(2026, 10, 19, 8, 5), None,
           'running', 0, json.dumps(snapshot))
    monkeypatch.setattr(records, 'execute_query', lambda *_: ([row], None))
    result = records.db_list_execution_records()[0]
    assert result['started_at'] == '2026-10-19T00:05:00+00:00'
    assert result['completed_at'] is None
    connection.close.assert_called_once()
