# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Application dispatch bound to the configured storage, not global DB settings."""
from common.custom import BaseHandler, InterfaceType
from orchestrate.persistence.context import current_context


class _StorageHandler(BaseHandler):
    def __init__(self, interface_type: InterfaceType):
        self._interface_type = interface_type

    def handle(self, *args, **kwargs):
        # Resolve on invocation: cached proxies must not retain an old backend
        # or bypass an extension registered after their creation.
        from common.custom import HandlerRegistry

        context = current_context()
        with context.backend.operation_scope():
            handler = HandlerRegistry.get_handler(self._interface_type, mode=context.mode)
            result = handler.handle(*args, **kwargs)
            if self._interface_type == InterfaceType.SAVE_PSOP:
                _publish_saved_psop(args, kwargs)
            return result


def _publish_saved_psop(args, kwargs) -> None:
    """Register the saved revision as a side channel; a failure here must not fail the save.

    Depends on the saved PSOP object, not on a handler return value: most handlers succeed
    without returning anything, and the argument may be passed positionally or by keyword.
    """
    try:
        from orchestrate.persistence.execution_observation import (
            observation_enabled,
            publish_saved_psop,
        )

        if not observation_enabled():
            return
        psop = args[0] if args else kwargs.get("psop")
        if psop is not None:
            publish_saved_psop(psop)
    except Exception as exc:  # noqa: BLE001 - observation is a side channel
        from loguru import logger

        logger.warning("Could not publish the saved PSOP revision ({}: {})",
                       type(exc).__name__, exc)


def get_storage_handler(interface_type: InterfaceType) -> BaseHandler:
    """Return a lazy handler whose complete call uses the current backend."""
    return _StorageHandler(interface_type)
