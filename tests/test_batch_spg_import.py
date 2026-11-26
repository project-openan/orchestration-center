# Copyright (c) 2026 Huawei Technologies Co., Ltd.
# All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.persistence.file_backend import FilePsopRepository
from scripts import batch_spg_to_psop as batch


@pytest.fixture
def pipeline(tmp_path, monkeypatch):
    psop = PSOP(name='synthetic', steps=[])
    parser, generator = MagicMock(), MagicMock()
    parser.parse_pdf_chapter.return_value = '# Synthetic business process'
    generator.generate_psop_workflow.return_value = psop
    monkeypatch.setattr(batch, 'SolutionPackageParser', lambda: parser)
    monkeypatch.setattr(batch, 'PsopGenerator', lambda: generator)
    repository = FilePsopRepository(WorkflowStorage(str(tmp_path/'target')))
    context = SimpleNamespace(psops=repository, mode='file', check_ready=MagicMock(), initialize=MagicMock(), close=MagicMock())
    monkeypatch.setattr(batch, 'build_context', lambda: context)
    monkeypatch.setattr(batch, 'precheck_llm', MagicMock(return_value=True))
    monkeypatch.setattr(batch, 'AgentCardLoader', lambda _: SimpleNamespace(get_all_agent_cards=lambda: [SimpleNamespace(name='A')]))
    pdf = tmp_path/'synthetic.pdf'
    pdf.write_bytes(b'%PDF-synthetic-input-for-mocked-parser')
    cards = tmp_path/'cards'
    cards.mkdir()
    (cards/'agent.yaml').write_text('synthetic planning catalog', encoding='utf-8')
    output = tmp_path/'exports'
    args = ['batch', '--pdf-dir', str(tmp_path), '--agent-cards-dir', str(cards), '--export-dir', str(output), '--retries', '1']
    return SimpleNamespace(psop=psop, parser=parser, generator=generator, repository=repository,
                           context=context, pdf=pdf, output=output, args=args, cards=cards)


def test_dry_run_then_real_run_saves_cached_generation(pipeline, monkeypatch):
    monkeypatch.setattr(sys, 'argv', pipeline.args + ['--dry-run'])
    assert batch.main() == 0
    assert batch.load_state(pipeline.output)[pipeline.pdf.name]['status'] == 'generated'
    assert pipeline.repository.get(pipeline.psop.id) is None
    pipeline.context.initialize.assert_not_called()
    pipeline.generator.generate_psop_workflow.reset_mock()
    batch.precheck_llm.reset_mock()
    monkeypatch.setattr(sys, 'argv', pipeline.args)
    assert batch.main() == 0
    pipeline.generator.generate_psop_workflow.assert_not_called()
    batch.precheck_llm.assert_not_called()
    assert pipeline.repository.get(pipeline.psop.id) == pipeline.psop
    assert batch.load_state(pipeline.output)[pipeline.pdf.name]['saved_to'] == 'file'


def test_cached_success_is_replayed_to_a_different_empty_target(pipeline, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'argv', pipeline.args)
    assert batch.main() == 0
    pipeline.context.psops = FilePsopRepository(WorkflowStorage(str(tmp_path/'second-target')))
    assert batch.main() == 0
    assert pipeline.context.psops.get(pipeline.psop.id) == pipeline.psop
    assert pipeline.generator.generate_psop_workflow.call_count == 1


@pytest.mark.parametrize('change', ['pdf', 'chapter', 'catalog', 'legacy_state'])
def test_changed_input_or_unverified_legacy_state_is_not_skipped(pipeline, monkeypatch, change):
    monkeypatch.setattr(sys, 'argv', pipeline.args + ['--dry-run'])
    assert batch.main() == 0
    if change == 'pdf':
        pipeline.pdf.write_bytes(b'%PDF-new-source')
    elif change == 'chapter':
        monkeypatch.setattr(sys, 'argv', pipeline.args + ['--dry-run', '--chapter', '6. Other'])
    elif change == 'catalog':
        (pipeline.cards/'agent.yaml').write_text('changed catalog', encoding='utf-8')
    else:
        state = batch.load_state(pipeline.output)
        state[pipeline.pdf.name].pop('input_fingerprint')
        batch.save_state(pipeline.output, state)
        (pipeline.output/'generated'/f'{pipeline.pdf.stem}.json').unlink()
    assert batch.main() == 0
    assert pipeline.generator.generate_psop_workflow.call_count == 2


def test_storage_failure_retains_export_and_retries_without_llm(pipeline, monkeypatch):
    real_save = pipeline.repository.save
    monkeypatch.setattr(pipeline.repository, 'save', MagicMock(side_effect=OSError('synthetic save failure')))
    monkeypatch.setattr(sys, 'argv', pipeline.args)
    assert batch.main() == 1
    assert (pipeline.output/'psop'/f'{pipeline.pdf.stem}.json').exists()
    assert batch.load_state(pipeline.output)[pipeline.pdf.name]['psop_id'] == pipeline.psop.id
    monkeypatch.setattr(pipeline.repository, 'save', real_save)
    assert batch.main() == 0
    assert pipeline.generator.generate_psop_workflow.call_count == 1


def test_user_edit_is_not_overwritten_on_resume(pipeline, monkeypatch):
    monkeypatch.setattr(sys, 'argv', pipeline.args)
    assert batch.main() == 0
    edited = pipeline.psop.model_copy(update={'name': 'operator edit'})
    pipeline.repository.save(edited)
    assert batch.main() == 1
    assert pipeline.repository.get(edited.id).name == 'operator edit'


def test_false_save_result_is_not_success(pipeline, monkeypatch):
    monkeypatch.setattr(pipeline.repository, 'save', lambda _: None)
    result = batch.convert_one_pdf(pipeline.pdf, '5. Interaction Flow', [], 1, False,
                                  repository=pipeline.repository, export_dir=pipeline.output)
    assert result.status == 'failed'
    assert 'verified' in result.error


def test_missing_checkpoint_after_commit_does_not_generate_duplicate(pipeline, monkeypatch):
    monkeypatch.setattr(sys, 'argv', pipeline.args)
    assert batch.main() == 0
    (pipeline.output/batch.STATE_FILE_NAME).unlink()
    assert batch.main() == 0
    assert pipeline.generator.generate_psop_workflow.call_count == 1
    assert len(pipeline.repository.list_summaries()) == 1


def test_modified_export_is_not_silently_reused(pipeline, monkeypatch):
    monkeypatch.setattr(sys, 'argv', pipeline.args + ['--dry-run'])
    assert batch.main() == 0
    (pipeline.output/'preflow'/f'{pipeline.pdf.stem}.md').write_text('modified', encoding='utf-8')
    assert batch.main() == 0
    assert pipeline.generator.generate_psop_workflow.call_count == 2


@pytest.mark.parametrize('value', [[], None, 'invalid', '{broken JSON'])
def test_invalid_checkpoint_shape_does_not_block_verified_recovery(pipeline, monkeypatch, value):
    monkeypatch.setattr(sys, 'argv', pipeline.args)
    assert batch.main() == 0
    content = value if value == '{broken JSON' else json.dumps(value)
    (pipeline.output/batch.STATE_FILE_NAME).write_text(content, encoding='utf-8')
    assert batch.main() == 0
    assert pipeline.generator.generate_psop_workflow.call_count == 1
    assert len(pipeline.repository.list_summaries()) == 1


@pytest.mark.parametrize('value', [[], None, 'invalid', '{broken JSON'])
def test_invalid_manifest_shape_is_not_reused(pipeline, monkeypatch, value):
    monkeypatch.setattr(sys, 'argv', pipeline.args + ['--dry-run'])
    assert batch.main() == 0
    content = value if value == '{broken JSON' else json.dumps(value)
    (pipeline.output/'generated'/f'{pipeline.pdf.stem}.json').write_text(content, encoding='utf-8')
    assert batch.main() == 0
    assert pipeline.generator.generate_psop_workflow.call_count == 2


def test_standalone_save_uses_real_file_port_without_web_import(tmp_path):
    root = Path(__file__).resolve().parents[1]
    code = """
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from scripts import batch_spg_to_psop as batch
from orchestrate.core.model.psop import PSOP
from orchestrate.core.persistence import WorkflowStorage
from orchestrate.persistence import StorageContext
from orchestrate.persistence.file_backend import FilePersistenceBackend
from orchestrate.workflow_storage_instance import get_workflow_storage
root = Path(sys.argv[1])
context = StorageContext(FilePersistenceBackend(storage=WorkflowStorage(str(root/'store'))))
psop = PSOP(name='standalone', steps=[])
with patch.object(batch,'SolutionPackageParser') as parser, patch.object(batch,'PsopGenerator') as generator, patch.object(batch,'build_context',return_value=context):
    parser.return_value.parse_pdf_chapter.return_value = 'synthetic'
    generator.return_value.generate_psop_workflow.return_value = psop
    result = batch.convert_one_pdf(Path('synthetic.pdf'),'chapter',[],1,False,export_dir=root/'output')
assert result.status == 'success', result.error
assert context.psops.get(psop.id) == psop
assert 'orchestrate.server.frontend_support_server' not in sys.modules
print('STANDALONE_SAVE_OK')
"""
    env = {**os.environ, 'TESTING': 'true', 'PYTHONIOENCODING': 'utf-8'}
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], cwd=root, env=env,
                            capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    assert 'STANDALONE_SAVE_OK' in result.stdout
