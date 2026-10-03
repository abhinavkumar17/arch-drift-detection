import json
import subprocess
import pytest
import review_pr
from repo_context import snapshot_repository


def test_committed_snapshot_matches_diff_and_rejects_dirty_checkout(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), '-c', 'core.autocrlf=false', *args])
    git('init')
    (repo / 'Screen.kt').write_text('old\n')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'base')
    base = git('rev-parse', 'HEAD').decode().strip()
    (repo / 'Screen.kt').write_text('new\n')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'head')
    diff = tmp_path / 'input.diff'
    diff.write_bytes(git('diff', base, 'HEAD'))
    manifest = snapshot_repository(repo, diff, tmp_path / 'snapshot', base=base)
    assert manifest['base'] == base
    assert (tmp_path / 'snapshot/Screen.kt').read_text() == 'new\n'
    # Evidence roots plus Kotlin package paths regularly exceed Windows MAX_PATH.
    deep = tmp_path / ('nested-' * 15) / ('evidence-' * 15) / 'snapshot'
    if __import__('os').name == 'nt':
        from pathlib import Path
        Path('\\\\?\\' + str(deep.resolve().parent)).mkdir(parents=True)
    else:
        deep.parent.mkdir(parents=True)
    long_manifest = snapshot_repository(repo, diff, deep, base=base)
    assert long_manifest['files'] == manifest['files']
    (repo / 'Screen.kt').write_text('unreviewed\n')
    with pytest.raises(ValueError, match='clean checkout'):
        snapshot_repository(repo, diff, tmp_path / 'bad', base=base)


@pytest.mark.parametrize('url', ['http://github.com/a/b/pull/1', 'https://evil.example/a/b/pull/1', 'https://github.com/a/b/pull/1?x=2'])
def test_reject_invalid_pr_urls(url):
    with pytest.raises(ValueError):
        review_pr.parse_pr(url)


@pytest.mark.parametrize('key', ['head', 'base'])
def test_changed_revision_rejected(key):
    before = dict(repository='a/b', base='a'*40, head='b'*40)
    after = dict(before, **{key: 'c'*40})
    with pytest.raises(RuntimeError, match='revisions changed'):
        review_pr.assert_same_revision(before, after)


@pytest.mark.parametrize('prepare_only', [True, False])
def test_pr_handoff_uses_fixed_checkout(tmp_path, monkeypatch, prepare_only):
    details = dict(repository='a/b', base='a'*40, head='b'*40, changed_files=5)
    monkeypatch.setattr(review_pr, 'resolve_gh', lambda: 'gh')
    monkeypatch.setattr(review_pr, 'metadata', lambda *args: details)
    def prepare(folder, data, timeout):
        (folder / 'input.diff').write_text('diff')
        (folder / 'checkout').mkdir()
        return folder / 'checkout', 'c'*40
    monkeypatch.setattr(review_pr, 'prepare_checkout', prepare)
    calls = []
    monkeypatch.setattr(review_pr.review_local, 'main', lambda args: calls.append(args) or 0)
    args = ['--pr', 'https://github.com/a/b/pull/1', '--output', str(tmp_path / 'runs')]
    if prepare_only:
        args.append('--prepare-only')
    assert review_pr.main(args) == 0
    summary = json.loads(next((tmp_path / 'runs').glob('*/pr-summary.json')).read_text())
    assert summary['posted'] is False
    assert bool(calls) is not prepare_only
    if calls:
        assert calls[0][calls[0].index('--base') + 1] == 'c'*40
