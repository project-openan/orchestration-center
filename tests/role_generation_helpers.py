# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

"""Synthetic, instance-independent catalog and model responses for generation tests."""

from copy import deepcopy


def catalog_payload():
    source = dict(package="synthetic", pdf="synthetic.pdf", pdf_pages=[1])
    return dict(catalog_version="generation-v1", roles=[dict(
        role_id=role, role_version="1", name=f"Display {role}", description="Approved capability",
        source=source, review_status="approved", skills=[dict(
            skill_id="explore", name="Shared skill name", description="Explore intent",
            source=source, review_status="approved",
        ), dict(skill_id="private-draft", name="Draft skill", description="Unapproved",
                source=source, review_status="draft")],
    ) for role in ("role-a", "role-b")])


def workflow_payload():
    return dict(name="Role design", steps=[dict(name="analyze", subtasks=[dict(
        task_id="original-1", description="Analyze intent", binding="role",
        agent="role-a", role_version="1", skill="explore",
    )], next=[])])


def action_matches():
    return [dict(action_id=f"a{index}", role_id=role, role_version="1", skill_id="explore")
            for index, role in enumerate(("role-a", "role-b"), 1)]


def structure_from_prompt(prompt):
    import json

    text = prompt.split("Selected tasks:\n", 1)[1]
    tasks, _ = json.JSONDecoder().raw_decode(text)
    return dict(name="Arranged", steps=[dict(name="parallel", subtasks=tasks, next=[])])


class JsonModel:
    """Deterministic model substitute; callables can inspect the actual prompt."""

    def __init__(self, *responses):
        self.responses = iter(responses)
        self.prompts = []

    def ask_llm(self, prompt):
        import json

        self.prompts.append(prompt)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        if callable(response):
            response = response(prompt)
        return None, json.dumps(deepcopy(response))
