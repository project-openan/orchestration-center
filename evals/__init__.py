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

"""Intent-to-PSOP planning evaluation set (OpenAN OrchestrationCenter).

A requirement-based benchmark for the orchestration planning capability of the
orchestration center: natural-language intent + AgentCard pool -> PSOP workflow.

Dataset design is grounded in public planning/workflow benchmarks (PlanBench,
NATURAL PLAN, TravelPlanner, tau-bench, WorfBench); see evals/README.md.
"""

from evals.scoring.case_model import AgentPool, EvalCase, load_cases, load_pool

__all__ = ["AgentPool", "EvalCase", "load_cases", "load_pool"]
