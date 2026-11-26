# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""First-class Host Agent runtime for workflow execution."""

from importlib import import_module

# Importing a public wire contract must not initialize the execution runtime.
_EXPORT_MODULES = {
    "ControlPointContext": "config",
    "HostAgentConfig": "config",
    "RoleExecutionContext": "config",
    "RoleTaskIdentity": "config",
    "HostAgentEventCallback": "runtime",
    "HostAgentExecutor": "runtime",
    "HostExecutionTracker": "execution",
    "host_event_state": "execution",
    "host_final_state": "execution",
}

__all__ = [
    "ControlPointContext",
    "HostAgentEventCallback",
    "HostAgentConfig",
    "RoleExecutionContext",
    "RoleTaskIdentity",
    "HostAgentExecutor",
    "HostExecutionTracker",
    "host_event_state",
    "host_final_state",
]


def __getattr__(name: str):
    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(f".{module_name}", __name__), name)
    globals()[name] = value
    return value
