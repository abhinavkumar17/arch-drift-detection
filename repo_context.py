"""Build a reproducible, source-only snapshot for local review tools."""
import hashlib
import json
from pathlib import Path
import subprocess

SOURCE_SUFFIXES = {'.kt', '.kts', '.java', '.xml', '.md', '.txt', '.toml', '.pro'}


def snapshot_repository(repo, diff, destination):
    repo = Path(repo).resolve(strict=True)
    def git(*args):
        return subprocess.check_output(['git', '-c', f'safe.directory={repo.as_posix()}',
                                        '-C', str(repo), *args], timeout=30)
    actual = git('diff', '--no-ext-diff', '--no-textconv', 'HEAD', '--')
    normalize = lambda value: value.replace(b'\r\n', b'\n').strip()
    if normalize(actual) != normalize(Path(diff).read_bytes()):
        raise ValueError('The supplied diff does not match this checkout against HEAD. Export a fresh diff first.')
    head = git('rev-parse', 'HEAD').decode().strip()
    destination.mkdir()
    files = {}
    total = 0
    skipped = []
    for name in git('ls-files', '-z').decode('utf-8').split('\0'):
        if not name:
            continue
        relative = Path(name)
        if (relative.is_absolute() or '..' in relative.parts or
                any(part.startswith('.') for part in relative.parts) or
                relative.suffix.lower() not in SOURCE_SUFFIXES):
            skipped.append(name)
            continue
        source = repo / relative
        if not source.exists():  # Deleted tracked file.
            continue
        if source.is_symlink() or not source.resolve().is_relative_to(repo):
            raise ValueError(f'Repository link is not supported: {name}')
        if source.stat().st_size > 512_000:
            skipped.append(name)
            continue
        data = source.read_bytes()
        try:
            data.decode('utf-8')
        except UnicodeDecodeError:
            skipped.append(name)
            continue
        if b'\0' in data:
            skipped.append(name)
            continue
        total += len(data)
        if total > 50_000_000:
            raise ValueError('Source snapshot exceeds 50 MB.')
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files[relative.as_posix()] = hashlib.sha256(data).hexdigest()
    if git('rev-parse', 'HEAD').decode().strip() != head or normalize(git('diff', '--no-ext-diff', '--no-textconv', 'HEAD', '--')) != normalize(actual):
        raise ValueError('Checkout changed while preparing the snapshot; retry with a stable checkout.')
    manifest = {'head': head, 'files': files, 'skipped': skipped,
                'scope': 'Tracked UTF-8 source files only; no hidden files, binaries, or untracked files.'}
    (destination.parent / 'repository-manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest
