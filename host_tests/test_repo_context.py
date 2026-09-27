from pathlib import Path
import subprocess
import pytest
from repo_context import snapshot_repository


def test_snapshot_matches_diff_and_excludes_untracked_and_hidden(tmp_path):
    repo = tmp_path / 'repo'
    repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git', '-C', str(repo), *args])
    git('init')
    (repo / 'Screen.kt').write_text('old\n')
    (repo / '.env').write_text('not included')
    git('add', '.')
    git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'baseline')
    (repo / 'Screen.kt').write_text('new\n')
    (repo / 'untracked.kt').write_text('not included')
    diff = tmp_path / 'input.diff'
    diff.write_bytes(git('diff', 'HEAD'))
    manifest = snapshot_repository(repo, diff, tmp_path / 'snapshot')
    assert set(manifest['files']) == {'Screen.kt'}
    assert (tmp_path / 'snapshot' / 'Screen.kt').read_text() == 'new\n'
    assert '.env' in manifest['skipped']
    (repo / 'Screen.kt').write_text('another change\n')
    with pytest.raises(ValueError, match='does not match'):
        snapshot_repository(repo, diff, tmp_path / 'bad')
