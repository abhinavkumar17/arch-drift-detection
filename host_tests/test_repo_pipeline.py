import json
from pathlib import Path
import pytest
import review_local as review
import repo_context

DIFF = 'diff --git a/Screen.kt b/Screen.kt\n--- a/Screen.kt\n+++ b/Screen.kt\n@@ -1 +1 @@\n-old\n+new\n'


@pytest.mark.parametrize('outcome', ['success', 'model_error', 'invalid_json'])
def test_repository_pipeline_uses_adapter_and_validates(tmp_path, monkeypatch, outcome):
    source = tmp_path / 'input.diff'
    source.write_text(DIFF)
    sdk = tmp_path / 'index.js'
    sdk.touch()
    monkeypatch.setattr(review.shutil, 'which', lambda name: name)
    monkeypatch.setattr(review, 'pi_command', lambda executable: ['node', str(tmp_path / 'cli.js')])
    monkeypatch.setattr(repo_context, 'snapshot_repository', lambda *args: {'head': 'test', 'files': {}})
    def prep(command, cwd, stdout, stderr, timeout):
        assert command[0] == 'docker'
        prepared = cwd / 'preparation' / 'run'
        prepared.mkdir(parents=True)
        review.save(prepared / 'summary.json', {'status': 'ready', 'steps': dict.fromkeys(('tests', 'diff', 'annotation', 'prompt_budget'), 'passed')})
        review.save(prepared / 'budget-report.json', {'fits': True, 'input_budget': 16000, 'estimated_tokens': 100})
        (prepared / 'prompt.txt').write_text('review prompt')
        (prepared / 'pr.diff').write_text(DIFF)
        return 0
    monkeypatch.setattr(review, 'run_process', prep)
    def lookup(command, folder, timeout, say):
        assert command[1].endswith('pi_repo_review.mjs')
        config = review.read(Path(command[-1]))
        assert config['contextBudget'] == 32000
        assert Path(config['prompt']).read_text() == 'review prompt'
        if outcome == 'model_error':
            return 1
        (folder / 'model-response.txt').write_text('bad' if outcome == 'invalid_json' else json.dumps({'findings': [], 'limitations': []}))
        review.save(folder / 'lookup-summary.json', {'tool_calls': 3, 'usage': None})
        return 0
    monkeypatch.setattr(review, 'run_lookup', lookup)
    code = review.main(['--diff', str(source), '--repo', str(tmp_path), '--output', str(tmp_path / 'runs')])
    folder = next((tmp_path / 'runs').iterdir())
    summary = review.read(folder / 'review-summary.json')
    assert code == (0 if outcome == 'success' else 1)
    assert summary['status'] == {'success': 'review_completed', 'model_error': 'model_failed', 'invalid_json': 'invalid_response'}[outcome]
    assert (folder / 'findings.json').exists() == (outcome == 'success')
