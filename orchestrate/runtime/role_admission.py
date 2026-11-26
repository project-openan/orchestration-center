# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Center-side role execution admission (REQ74 P4).

Role execution is disabled by default. ``role_execution_mode=pilot`` opens
the controlled technical-pilot mode, and only on an explicitly declared
non-production ``deployment_environment``. The dispatch signature key
(``ORCH_ROLE_DISPATCH_KEY``) authenticates a message; this gate authorizes
the capability and is a separate, explicit operator decision.
"""

from host_agent.role_contract import role_execution_admitted


def configured_role_execution_mode() -> str | None:
    """server.conf key ``role_execution_mode``; unset means disabled."""
    from common.util.config_util import get_conf

    value = get_conf().get("role_execution_mode")
    if value is None:
        return None
    return str(value).strip() or None


def configured_deployment_environment() -> str | None:
    """server.conf key ``deployment_environment``; unset means production."""
    from common.util.config_util import get_conf

    value = get_conf().get("deployment_environment")
    if value is None:
        return None
    return str(value).strip() or None


def role_execution_admission() -> tuple[bool, list[str]]:
    """``(allowed, rejection reasons)`` for this deployment's configuration."""
    return role_execution_admitted(
        configured_role_execution_mode(), configured_deployment_environment())
