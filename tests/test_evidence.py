"""Evidence upload tests: fake S3, real files, no AWS requests."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
import entrypoint
from core.evidence import upload_evidence
from test_prompt import DIFF


class FakeS3:
    def __init__(self):
        self.objects = {}
        self.fail_on = None

    def upload_file(self, filename, bucket, key):
        if Path(filename).name == self.fail_on:
            raise RuntimeError('Simulated upload failure')
        self.objects[(bucket, key)] = Path(filename).read_bytes()


@pytest.fixture
def s3(monkeypatch):
    fake = FakeS3()

    def client(service):
        assert service == 's3'
        return fake

    monkeypatch.setitem(sys.modules, 'boto3', SimpleNamespace(client=client))
    monkeypatch.delenv('EVIDENCE_BUCKET', raising=False)
    return fake


def test_uploads_evidence_only_and_receipt_last(tmp_path, s3):
    (tmp_path / 'tests.log').write_bytes(b'tests passed\n')
    (tmp_path / 'summary.json').write_text('{"status": "ready"}')
    (tmp_path / 'private.txt').write_text('not evidence')
    (tmp_path / 'repo').mkdir()
    (tmp_path / 'repo' / 'source.kt').write_text('not evidence')

    destination = upload_evidence(tmp_path, 'test-bucket')
    prefix = f'runs/{tmp_path.name}/'
    assert destination == f's3://test-bucket/{prefix}'
    assert list(s3.objects) == [
        ('test-bucket', prefix + 'tests.log'),
        ('test-bucket', prefix + 'summary.json'),
        ('test-bucket', prefix + 'upload-report.json'),
    ]
    assert s3.objects[('test-bucket', prefix + 'tests.log')] == b'tests passed\n'
    receipt = json.loads(s3.objects[('test-bucket', prefix + 'upload-report.json')])
    assert receipt['status'] == 'uploaded'
    assert receipt['uploaded_files'] == ['tests.log', 'summary.json']


@pytest.mark.parametrize('failure', ['summary.json', 'upload-report.json'])
def test_failed_upload_records_partial_progress(tmp_path, s3, failure):
    (tmp_path / 'tests.log').write_text('tests passed')
    (tmp_path / 'summary.json').write_text('{}')
    s3.fail_on = failure
    with pytest.raises(RuntimeError, match='Simulated upload failure'):
        upload_evidence(tmp_path, 'test-bucket')
    report = json.loads((tmp_path / 'upload-report.json').read_text())
    assert report['status'] == 'failed'
    assert report['error'] == 'Simulated upload failure'
    expected = ['tests.log'] if failure == 'summary.json' else ['tests.log', 'summary.json']
    assert report['uploaded_files'] == expected
    assert not any(key.endswith('upload-report.json') for _, key in s3.objects)


@pytest.fixture
def prepared_run(tmp_path, monkeypatch, s3):
    source = tmp_path / 'input.diff'
    source.write_text(DIFF, encoding='utf-8')
    output = tmp_path / 'runs'

    def simulated_command(args, destination, cwd=entrypoint.ROOT):
        destination.write_text('Simulated subprocess success')

    monkeypatch.setattr(entrypoint, 'command', simulated_command)
    return ['--diff', str(source), '--output', str(output)], output


@pytest.mark.parametrize('budget,code,status', [(800000, 0, 'ready'), (1, 2, 'over_budget')])
def test_runner_uploads_full_prompt_for_fit_and_overflow(prepared_run, s3, budget, code, status):
    args, output = prepared_run
    assert entrypoint.main(args + ['--budget', str(budget), '--evidence-bucket', 'test-bucket']) == code
    run = next(output.iterdir())
    prefix = f'runs/{run.name}/'
    summary = json.loads(s3.objects[('test-bucket', prefix + 'summary.json')])
    assert summary['status'] == status
    assert s3.objects[('test-bucket', prefix + 'prompt.txt')] == (run / 'prompt.txt').read_bytes()
    assert s3.objects[('test-bucket', prefix + 'pr.diff')] == (run / 'pr.diff').read_bytes()
    assert json.loads((run / 'upload-report.json').read_text())['status'] == 'uploaded'


@pytest.mark.parametrize('budget', [800000, 1])
def test_runner_upload_failure_returns_error(prepared_run, s3, budget, capsys):
    args, output = prepared_run
    s3.fail_on = 'prompt.txt'
    assert entrypoint.main(args + ['--budget', str(budget), '--evidence-bucket', 'test-bucket']) == 1
    run = next(output.iterdir())
    assert json.loads((run / 'upload-report.json').read_text())['status'] == 'failed'
    assert 'FAILED: Evidence upload:' in capsys.readouterr().out
    assert (run / 'prompt.txt').exists()


def test_failed_test_gate_still_uploads_available_evidence(prepared_run, monkeypatch, s3):
    args, output = prepared_run

    def fail(args, destination, cwd=entrypoint.ROOT):
        destination.write_text('Simulated application test failure')
        raise RuntimeError('Application tests failed')

    monkeypatch.setattr(entrypoint, 'command', fail)
    assert entrypoint.main(args + ['--evidence-bucket', 'test-bucket']) == 1
    run = next(output.iterdir())
    prefix = f'runs/{run.name}/'
    summary = json.loads(s3.objects[('test-bucket', prefix + 'summary.json')])
    assert summary['status'] == 'failed'
    assert summary['steps']['diff'] == 'skipped'
    assert ('test-bucket', prefix + 'tests.log') in s3.objects
    assert ('test-bucket', prefix + 'prompt.txt') not in s3.objects
    assert json.loads((run / 'upload-report.json').read_text())['status'] == 'uploaded'


def test_no_bucket_never_creates_aws_client(prepared_run, monkeypatch, s3):
    args, output = prepared_run

    def forbidden_client(*args, **kwargs):
        pytest.fail('Local-only run must not create an AWS client')

    monkeypatch.setitem(sys.modules, 'boto3', SimpleNamespace(client=forbidden_client))
    assert entrypoint.main(args) == 0
    run = next(output.iterdir())
    assert (run / 'summary.json').exists()
    assert not (run / 'upload-report.json').exists()


def test_bucket_environment_setting_and_cli_override(monkeypatch):
    monkeypatch.setenv('EVIDENCE_BUCKET', 'environment-bucket')
    assert entrypoint.parser().parse_args([]).evidence_bucket == 'environment-bucket'
    assert entrypoint.parser().parse_args(['--evidence-bucket', 'cli-bucket']).evidence_bucket == 'cli-bucket'
