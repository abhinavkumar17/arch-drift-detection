import json
from pathlib import Path
import subprocess
import pytest
import review_local as review

DIFF = 'diff --git a/Screen.kt b/Screen.kt\n--- a/Screen.kt\n+++ b/Screen.kt\n@@ -1 +1 @@\n-old\n+new\n'


@pytest.mark.parametrize('scenario,expected,invoked', [
    ('valid', 'review_completed', True),
    ('empty', 'review_completed', True),
    ('overflow', 'over_budget', False),
    ('prep_failure', 'preparation_failed', False),
    ('false_ready', 'preparation_failed', False),
    ('wrong_diff', 'preparation_failed', False),
    ('model_failure', 'model_failed', True),
    ('timeout', 'model_failed', True),
    ('bad_json', 'invalid_response', True),
    ('wrong_line', 'invalid_response', True),
    ('missing_field', 'invalid_response', True),
])
def test_pipeline_gates_and_evidence(tmp_path, monkeypatch, scenario, expected, invoked):
    source = tmp_path / 'source.diff'
    source.write_text(DIFF)
    monkeypatch.setattr(review.shutil, 'which', lambda name: name)
    monkeypatch.setattr(review, 'pi_command', lambda executable: ['pi'])
    calls = []
    def execute(command, cwd, stdout, stderr, timeout):
        calls.append(command)
        stdout.write_text('')
        stderr.write_text('')
        if command[0] == 'docker':
            prepared = cwd / 'preparation' / 'run'
            prepared.mkdir(parents=True)
            state = 'over_budget' if scenario == 'overflow' else 'failed' if scenario == 'prep_failure' else 'ready'
            review.save(prepared / 'summary.json', {'status': state, 'steps': dict.fromkeys(('tests','diff','annotation','prompt_budget'), 'passed')})
            review.save(prepared / 'budget-report.json', {'fits': scenario not in ('overflow','false_ready'), 'input_budget':16000, 'estimated_tokens':100})
            (prepared / 'prompt.txt').write_text('Bundled prompt')
            (prepared / 'pr.diff').write_text('wrong' if scenario == 'wrong_diff' else DIFF)
            return 2 if scenario == 'overflow' else 1 if scenario == 'prep_failure' else 0
        assert '--no-tools' in command and '--no-session' in command
        assert Path(command[-1][1:]).read_text() == 'Bundled prompt'
        if scenario == 'timeout':
            raise subprocess.TimeoutExpired(command, timeout)
        if scenario == 'model_failure':
            stderr.write_text('simulated authentication failure')
            return 1
        finding = dict(path='Screen.kt', line=1, side='RIGHT', principle='State owner',
                       title='Issue', explanation='Reason', evidence='new', suggested_change='Fix')
        if scenario == 'wrong_line':
            finding['line'] = 90
        if scenario == 'missing_field':
            del finding['evidence']
        stdout.write_text('not JSON' if scenario == 'bad_json' else json.dumps({'findings': [] if scenario == 'empty' else [finding], 'limitations': []}))
        return 0
    monkeypatch.setattr(review, 'run_process', execute)
    result = review.main(['--diff', str(source), '--output', str(tmp_path / 'output')])
    folder = next((tmp_path / 'output').iterdir())
    summary = review.read(folder / 'review-summary.json')
    assert summary['status'] == expected
    assert summary['model_invocation_attempted'] == invoked
    assert len(calls) == (2 if invoked else 1)
    assert result == (0 if expected == 'review_completed' else 2 if expected == 'over_budget' else 1)
    assert (folder / 'input.diff').read_text() == DIFF
    assert (folder / 'findings.json').exists() == (expected == 'review_completed')


def test_windows_shim_uses_node_without_shell(tmp_path, monkeypatch):
    shim = tmp_path / 'pi.cmd'
    cli = tmp_path / 'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'
    cli.parent.mkdir(parents=True)
    cli.touch()
    monkeypatch.setattr(review.shutil, 'which', lambda name: 'node.exe')
    assert review.pi_command(str(shim)) == ['node.exe', str(cli)]
