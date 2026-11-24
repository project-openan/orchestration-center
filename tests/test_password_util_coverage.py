# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
"""Coverage for input_password_with_validation interactive retry path."""

from common.util import password_util


def test_strong_password_returned_without_prompting(monkeypatch):
    calls = []
    monkeypatch.setattr("getpass.getpass", lambda prompt: calls.append(prompt) or "StrongP@ss1")
    monkeypatch.setattr("builtins.input", lambda: pytest_fail_input())
    pw = password_util.input_password_with_validation("Enter")
    assert pw == "StrongP@ss1"
    assert calls == ["Enter: "]


def pytest_fail_input():
    raise AssertionError("input() should not be reached for a strong password")


def test_weak_password_confirmed_yes_is_kept(monkeypatch, capsys):
    monkeypatch.setattr("getpass.getpass", lambda prompt: "weak")
    monkeypatch.setattr("builtins.input", lambda: "y")
    pw = password_util.input_password_with_validation("Enter")
    assert pw == "weak"
    out = capsys.readouterr().out
    assert "complexity is low" in out
    assert "y/n" in out


def test_weak_password_rejected_retries_then_strong(monkeypatch, capsys):
    passwords = iter(["weakonlylower", "StrongP@ss1"])
    confirms = iter(["n"])
    monkeypatch.setattr("getpass.getpass", lambda prompt: next(passwords))
    monkeypatch.setattr("builtins.input", lambda: next(confirms))
    pw = password_util.input_password_with_validation("Enter")
    assert pw == "StrongP@ss1"
