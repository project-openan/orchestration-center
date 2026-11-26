# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Small dialect boundary shared by the SQL processors and user store."""

import re
from datetime import datetime, timezone

from common.util.persistence_mode import persistence_mode


def upsert_sql(table: str, key: str, columns: tuple[str, ...]) -> str:
    """Build a parameterized upsert from internal, validated identifiers only."""
    for identifier in (table, key, *columns):
        if not re.fullmatch(r"[a-z_]+", identifier):
            raise ValueError("Invalid SQL identifier")
    names = ", ".join(columns)
    placeholders = ", ".join("%s" for _ in columns)
    updates = [column for column in columns if column != key]
    insert = f"INSERT INTO {table} ({names}) VALUES ({placeholders})"
    if persistence_mode() == "mysql":
        # Row aliases avoid the deprecated VALUES(column) function (MySQL 8.0.19+).
        assignments = ", ".join(f"{column} = incoming.{column}" for column in updates)
        return f"{insert} AS incoming ON DUPLICATE KEY UPDATE {assignments}"
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in updates)
    return f"{insert} ON CONFLICT ({key}) DO UPDATE SET {assignments}"


def null_safe_equal(column: str) -> str:
    """Dialect-specific null-safe equality for password compare-and-swap."""
    if not re.fullmatch(r"[a-z_]+", column):
        raise ValueError("Invalid SQL identifier")
    operator = "<=>" if persistence_mode() == "mysql" else "IS NOT DISTINCT FROM"
    return f"{column} {operator} %s"


def timestamp_parameter(value: datetime | None):
    """Both SQL schemas use timezone-less columns; bind explicit naive UTC.

    Passing an aware datetime to PostgreSQL TIMESTAMP otherwise delegates the
    conversion to the connection timezone and can shift the stored instant.
    """
    if value is not None and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def timestamp_iso(value):
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return value
