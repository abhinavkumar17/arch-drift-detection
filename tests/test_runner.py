import json
from pathlib import Path
import subprocess

import pytest
import entrypoint
from test_prompt import DIFF


@pytest.mark.parametrize('budget,code,status', [(800000, 0, 'ready'), (1, 2, 'over_budget')])
def test_saved_diff_report_and_unique_runs(tmp_path, monkeypatch, budget, code, status):
    source = tmp_path / 'input.diff'
    source.write_text(DIFF, encoding='utf-8')
    monkeypatch.setattr(entrypoint, 'command', lambda args, destination, cwd=entrypoint.ROOT: destination.write_text('simulated subprocess success'))
    output = tmp_path / 'runs'
    for _ in range(2):
        assert entrypoint.main(['--diff', str(source), '--output', str(output), '--budget', str(budget)]) == code
    runs = list(output.iterdir())
    assert len(runs) == 2
    for run in runs:
        summary = json.loads((run / 'summary.json').read_text())
        assert summary['status'] == status
        assert summary['model_called'] is False
        report = json.loads((run / 'budget-report.json').read_text())
        assert report['fits'] == (code == 0)
        assert '[NEW:L1]' in (run / 'prompt.txt').read_text()
        assert (run / 'pr.diff').read_bytes() == source.read_bytes()


def test_failed_tests_stop_before_diff(tmp_path, monkeypatch):
    def fail(args, destination, cwd=entrypoint.ROOT):
        destination.write_text('Example test failure')
        raise RuntimeError('Tests failed; see tests.log')
    monkeypatch.setattr(entrypoint, 'command', fail)
    assert entrypoint.main(['--output', str(tmp_path)]) == 1
    run = next(tmp_path.iterdir())
    summary = json.loads((run / 'summary.json').read_text())
    assert summary['steps'] == dict(tests='failed', diff='skipped', annotation='skipped', prompt_budget='skipped')
    assert not (run / 'pr.diff').exists()
    assert 'Example test failure' in (run / 'tests.log').read_text()


def test_real_git_commit_range(tmp_path, monkeypatch):
    repo = tmp_path / 'source'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.STDOUT, text=True).strip()
    git('init')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'user.name', 'Fixture')
    hashes = []
    for value in ['one', 'two', 'three']:
        (repo / 'Main.kt').write_text(value + '\n')
        git('add', '.')
        git('commit', '-m', value)
        hashes.append(git('rev-parse', 'HEAD'))
    original = entrypoint.command
    def controlled(args, destination, cwd=entrypoint.ROOT):
        if 'pytest' in args or any(str(arg).endswith('annotate.py') for arg in args):
            destination.write_text('subprocess skipped in integration test')
        else:
            original(args, destination, cwd)
    monkeypatch.setattr(entrypoint, 'command', controlled)
    output = tmp_path / 'runs'
    assert entrypoint.main(['--repo', str(repo), '--commits', '2', '--output', str(output)]) == 0
    summary = json.loads((next(output.iterdir()) / 'summary.json').read_text())
    assert summary['source']['base_commit'] == hashes[0]
    assert summary['source']['head_commit'] == hashes[2]


@pytest.mark.parametrize('number', ['0', '-1'])
def test_invalid_commit_count(number):
    with pytest.raises(SystemExit):
        entrypoint.parser().parse_args(['--commits', number])
