# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
#
# SPDX-License-Identifier: Apache-2.0

"""Host-scoped Authorization-T and Notification-T lifecycle for the SPN sample."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from contextlib import suppress
from typing import Any

from a2a_t.core.metadata import (
    AUTHORIZATION_T_EXTENSION_URI,
    NOTIFICATION_T_EXTENSION_URI,
)
from loguru import logger
from workflow_engine import A2ATransport, ExtensionSender, ReceivedMessage

from samples.spn_host_agent.content import (
    RECOVERY_RESULT_REQUIRED_FIELDS,
    authorization_content,
    create_a2at_client,
    notification_content,
)


class SpnExtensionLifecycle:
    """Run independent protocol operations outside every workflow execution."""

    _RETRY_SECONDS = 2.0

    def __init__(
        self,
        agent_cards: Sequence[Any],
        credentials_config: str,
        ssl_verify: bool,
    ) -> None:
        self._agent_cards = tuple(agent_cards)
        self._authorization_targets = self._targets_for(
            AUTHORIZATION_T_EXTENSION_URI
        )
        self._notification_targets = self._targets_for(
            NOTIFICATION_T_EXTENSION_URI
        )
        self._authorization_transport = A2ATransport(
            agent_cards=list(self._agent_cards),
            credentials_config=credentials_config,
            ssl_verify=ssl_verify,
        )
        self._notification_transport = A2ATransport(
            agent_cards=list(self._agent_cards),
            credentials_config=credentials_config,
            ssl_verify=ssl_verify,
        )
        self._authorization_sender = ExtensionSender(self._authorization_transport)
        self._notification_sender = ExtensionSender(self._notification_transport)
        self._authorized: set[str] = set()
        self._completed_notifications: set[str] = set()
        self._subscriptions: dict[str, Any] = {}
        self._stop = asyncio.Event()
        self._runner: asyncio.Task | None = None

    def _targets_for(self, extension_uri: str) -> tuple[str, ...]:
        targets: list[str] = []
        for card in self._agent_cards:
            name = getattr(card, "name", "")
            if not name or name == "Host Agent":
                continue
            capabilities = getattr(card, "capabilities", None)
            extensions = getattr(capabilities, "extensions", ()) if capabilities else ()
            if extension_uri in {getattr(extension, "uri", "") for extension in extensions}:
                targets.append(name)
        return tuple(targets)

    def start(self) -> None:
        if self._runner is None and (
            self._authorization_targets or self._notification_targets
        ):
            self._runner = asyncio.create_task(
                self._run(),
                name="spn-independent-extension-lifecycle",
            )

    async def _run(self) -> None:
        while not self._stop.is_set():
            await asyncio.gather(
                self._ensure_authorizations(),
                self._ensure_subscriptions(),
            )
            try:
                await asyncio.wait_for(
                    self._stop.wait(),
                    timeout=self._RETRY_SECONDS,
                )
            except TimeoutError:
                continue

    async def _ensure_authorizations(self) -> None:
        for agent_name in self._authorization_targets:
            if self._stop.is_set() or agent_name in self._authorized:
                continue
            try:
                content = await asyncio.to_thread(
                    authorization_content,
                    create_a2at_client(),
                )
                result = await self._authorization_sender.send_authorization(
                    agent_name,
                    content,
                )
                if not result.is_success:
                    raise RuntimeError(
                        f"{result.failure_code or 'authorization.not_completed'}: "
                        f"{result.failure_message or result.task_state or 'authorization failed'}"
                    )
                self._authorized.add(agent_name)
                logger.info(
                    f"[SpnExtensionLifecycle] Authorization-T accepted by {agent_name}"
                )
            except Exception as error:
                logger.warning(
                    f"[SpnExtensionLifecycle] Authorization-T to {agent_name} failed; "
                    f"workflow execution remains independent: {error}"
                )

    async def _ensure_subscriptions(self) -> None:
        for agent_name in self._notification_targets:
            if self._stop.is_set() or agent_name in self._completed_notifications:
                continue
            current = self._subscriptions.get(agent_name)
            if current is not None and current.is_active:
                continue
            try:
                content = await asyncio.to_thread(
                    notification_content,
                    create_a2at_client(),
                )
                subscription = self._notification_sender.open_notification(
                    agent_name,
                    content,
                    lambda handle, message, name=agent_name: self._on_notification(
                        handle,
                        message,
                        name,
                    ),
                )
                self._subscriptions[agent_name] = subscription
                acknowledgement = await asyncio.wait_for(
                    subscription.acknowledgement,
                    timeout=30,
                )
                acknowledged = acknowledgement.is_success or (
                    not acknowledgement.is_failure
                    and acknowledgement.task_state in {
                        "TASK_STATE_SUBMITTED", "TASK_STATE_WORKING",
                    }
                )
                if not acknowledged:
                    raise RuntimeError(
                        f"{acknowledgement.failure_code or 'notification.not_acknowledged'}: "
                        f"{acknowledgement.failure_message or acknowledgement.task_state or 'subscription failed'}"
                    )
                logger.info(
                    f"[SpnExtensionLifecycle] Notification-T subscription active for {agent_name}"
                )
            except Exception as error:
                failed = self._subscriptions.pop(agent_name, None)
                if failed is not None:
                    failed.close()
                logger.warning(
                    f"[SpnExtensionLifecycle] Notification-T subscription to {agent_name} "
                    f"failed; workflow execution remains independent: {error}"
                )

    def _on_notification(
        self,
        subscription,
        received: ReceivedMessage,
        agent_name: str,
    ) -> None:
        recovery = self._recovery_result(received)
        if recovery is None:
            if any(
                artifact.name == "notification-subscription"
                for artifact in received.artifacts
            ):
                logger.debug(
                    f"[SpnExtensionLifecycle] Notification-T acknowledgement from {agent_name}"
                )
            return
        missing = RECOVERY_RESULT_REQUIRED_FIELDS.difference(recovery)
        if missing:
            logger.warning(
                f"[SpnExtensionLifecycle] Ignoring incomplete Notification-T result from "
                f"{agent_name}; missing={sorted(missing)}"
            )
            return
        logger.info(
            f"[SpnExtensionLifecycle] Notification-T recovery result from {agent_name}: "
            f"status={recovery['业务抢通方案执行状态']}, "
            f"result={recovery['业务抢通方案执行结果']}, "
            f"taskId={recovery['投诉诊断任务流水号']}"
        )
        self._completed_notifications.add(agent_name)
        asyncio.get_running_loop().call_soon(subscription.close)

    @staticmethod
    def _recovery_result(received: ReceivedMessage) -> dict[str, Any] | None:
        for artifact in received.artifacts:
            if artifact.name != "recovery-result":
                continue
            artifact_message = ReceivedMessage(artifacts=(artifact,))
            for output in artifact_message.outputs(include_message=False):
                if isinstance(output, Mapping):
                    return dict(output)
            return {}
        return None

    def request_stop(self) -> None:
        self._stop.set()
        for subscription in tuple(self._subscriptions.values()):
            subscription.close()

    async def aclose(self) -> None:
        self.request_stop()
        if self._runner is not None:
            self._runner.cancel()
            with suppress(asyncio.CancelledError):
                await self._runner
        await self._authorization_transport.close()
        await self._notification_transport.close()


__all__ = ["SpnExtensionLifecycle"]
