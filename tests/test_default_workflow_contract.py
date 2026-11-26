# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

import pytest

from orchestrate.agentcard_loader import AgentCardLoader
from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.persistence.file_backend import FilePsopRepository
from scripts import migrate_default_psops as migration

ROOT = Path(__file__).resolve().parents[1]
SEEDS = ROOT/'database'/'seed_data'/'psop'


def test_all_seed_links_and_skills_resolve_in_planning_catalog():
    cards = {card.name: card for card in AgentCardLoader(ROOT/'samples'/'agentcard').get_all_agent_cards()}
    import json
    workflows = {psop.id: psop for path in SEEDS.glob('*.json')
                 for psop in [PSOP.model_validate_json(path.read_text(encoding='utf-8'))]}
    packages = [json.loads(path.read_text(encoding='utf-8')) for path in (ROOT/'samples'/'solution_packages').glob('*.json')]
    assert len(workflows) == len(packages) == 19
    assert {package['workflow_id'] for package in packages} == workflows.keys()
    for workflow in workflows.values():
        for step in workflow.steps:
            for task in step.subtasks:
                assert task.agent in cards, (workflow.name, task.agent)
                assert task.skill in {skill.name for skill in cards[task.agent].skills}, (workflow.name, task.agent, task.skill)


@pytest.mark.parametrize('prefix,forbidden,required', [
    ('IG1501C_', ['Mobile Network Fault'], ['IP Network Fault']),
    ('IG1523E_', ['Mobile Network Fault'], ['IP Network Fault']),
    ('IG1523D_', ['Mobile Network Fault'], ['Transport Network Fault']),
    ('IG1505G_', ['Mobile Network Fault', 'Wireless Network Fault'], ['Computing Network Fault']),
    ('IG1502A_', ['Energy Saving', 'RAN ES'], ['Radio Service', 'Mobile Service']),
    ('IG1525E_', ['Energy Saving', 'RAN ES'], ['IP Quality Intent']),
    ('IG1523B_', ['RAN Agent', 'IP Network Quality'], ['Core Network Analytics']),
])
def test_domain_actions_do_not_use_unrelated_sample_capabilities(prefix, forbidden, required):
    psop = PSOP.model_validate_json(next(SEEDS.glob(prefix+'*.json')).read_text(encoding='utf-8'))
    bindings = '\n'.join(task.agent+' '+task.skill for step in psop.steps for task in step.subtasks)
    assert all(value not in bindings for value in forbidden)
    assert all(value in bindings for value in required)


def test_planning_catalog_is_not_advertised_as_a_deployed_task_t_server():
    import yaml
    catalog_path = ROOT/'samples'/'agentcard'/'spg_an_l4_agents.yaml'
    text = catalog_path.read_text(encoding='utf-8')
    assert 'PLANNING CATALOG ONLY' in text
    cards = yaml.safe_load(text)['agents']
    assert all(not card.get('capabilities', {}).get('extensions') for card in cards)
    for lang, name in [('en', 'SPG Import.md'), ('zh', 'SPG导入.md')]:
        doc = (ROOT/'docs'/lang/name).read_text(encoding='utf-8')
        assert 'Task-T' in doc and 'spg_an_l4_agents.yaml' in doc


@pytest.fixture
def migration_case(tmp_path, monkeypatch):
    previous = PSOP(name='unmodified old default', steps=[])
    replacement = previous.model_copy(update={'name': 'corrected default'})
    (tmp_path/'seed.json').write_text(replacement.model_dump_json(), encoding='utf-8')
    monkeypatch.setattr(migration, 'SEED_DATA_DIR', tmp_path)
    monkeypatch.setattr(migration, 'PREVIOUS_FINGERPRINTS', {'seed': migration.fingerprint(previous)})
    repository = FilePsopRepository(WorkflowStorage(str(tmp_path/'storage')))
    repository.save(previous)
    return repository, previous, replacement, tmp_path/'backup'


def test_migration_preview_writes_neither_workflow_nor_backup(migration_case):
    repository, previous, _, backup = migration_case
    assert migration.migrate(repository, backup_dir=backup)[0]['status'] == 'eligible'
    assert repository.get(previous.id) == previous
    assert not backup.exists()


def test_migration_is_backed_up_verified_and_idempotent(migration_case):
    repository, previous, replacement, backup = migration_case
    assert migration.migrate(repository, apply=True, backup_dir=backup)[0]['status'] == 'updated'
    assert repository.get(previous.id) == replacement
    assert PSOP.model_validate_json((backup/f'{previous.id}.json').read_text(encoding='utf-8')) == previous
    assert migration.migrate(repository, apply=True, backup_dir=backup)[0]['status'] == 'current'


def test_migration_preserves_user_edits(migration_case):
    repository, previous, _, backup = migration_case
    edited = previous.model_copy(update={'description': 'operator added details'})
    repository.save(edited)
    assert migration.migrate(repository, apply=True, backup_dir=backup)[0]['status'] == 'conflict'
    assert repository.get(previous.id) == edited
    assert not backup.exists()


def test_migration_does_not_invent_missing_installed_workflows(migration_case):
    repository, previous, _, backup = migration_case
    repository.delete(previous.id)
    assert migration.migrate(repository, apply=True, backup_dir=backup)[0]['status'] == 'missing'
    assert not backup.exists()


def test_migration_refuses_to_replace_an_existing_different_backup(migration_case):
    repository, previous, _, backup = migration_case
    backup.mkdir()
    unrelated = previous.model_copy(update={'description': 'different backup'})
    path = backup/f'{previous.id}.json'
    path.write_text(unrelated.model_dump_json(), encoding='utf-8')
    with pytest.raises(RuntimeError, match='Existing backup differs'):
        migration.migrate(repository, apply=True, backup_dir=backup)
    assert repository.get(previous.id) == previous
    assert PSOP.model_validate_json(path.read_text(encoding='utf-8')) == unrelated


def test_migration_detects_an_edit_before_saving(migration_case, monkeypatch):
    repository, previous, _, backup = migration_case
    get = repository.get
    edited = previous.model_copy(update={'description': 'concurrent operator edit'})
    calls = 0

    def get_after_edit(workflow_id):
        nonlocal calls
        calls += 1
        if calls == 2:
            repository.save(edited)
        return get(workflow_id)

    monkeypatch.setattr(repository, 'get', get_after_edit)
    with pytest.raises(RuntimeError, match='Workflow changed'):
        migration.migrate(repository, apply=True, backup_dir=backup)
    assert get(previous.id) == edited
    assert (backup/f'{previous.id}.json').exists()


def test_migration_retains_backup_when_save_cannot_be_verified(migration_case, monkeypatch):
    repository, previous, _, backup = migration_case
    monkeypatch.setattr(repository, 'save', lambda _: None)
    with pytest.raises(RuntimeError, match='could not be verified'):
        migration.migrate(repository, apply=True, backup_dir=backup)
    assert repository.get(previous.id) == previous
    assert PSOP.model_validate_json((backup/f'{previous.id}.json').read_text(encoding='utf-8')) == previous
