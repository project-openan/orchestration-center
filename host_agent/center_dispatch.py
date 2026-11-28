# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# SPDX-License-Identifier: Apache-2.0

"""Compatibility alias: the centre dispatch proof lives in ``host_agent.dispatch_proof``."""

from host_agent.dispatch_proof import (  # noqa: F401 - re-exported wire contract
    CENTER_DISPATCH_PROOF,
    CLAIMS_VARIABLE,
    CLOCK_SKEW_SECONDS,
    KEY_ENV,
    MAX_AGE_SECONDS,
    PSOP_REVISION_KEY,
    claim_execution,
    verified_center_dispatch_id,
    write_center_dispatch_proof,
)
