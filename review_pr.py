"""Fetch a public GitHub PR at fixed revisions and run the local reviewer. No posting."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time

import review_local


def parse_pr(url):
    match = re.fullmatch(r'https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/([1-9][0-9]*)/?', url)
    if not match:
        raise ValueError('Use a GitHub PR URL: https://github.com/owner/repository/pull/number')
    return match.groups()


def resolve_gh():
    found = shutil.which('gh')
    if found:
        return found
    candidate = Path(os.environ.get('LOCALAPPDATA', '')) / 'Programs/GitHubCLI/bin/gh.exe'
    if candidate.is_file():
        return str(candidate)
    raise RuntimeError('Install GitHub CLI and run gh auth login first.')


def metadata(gh, owner, repo, number):
    # Only public test repositories in this first milestone. Never persist API credentials.
    result = subprocess.run([gh, 'api', f'repos/{owner}/{repo}/pulls/{number}'],
                            capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError('Cannot read the PR. Check GitHub CLI authentication and repository access.')
    raw = json.loads(result.stdout)
    if raw['state'] != 'open':
        raise ValueError('The PR must be open.')
    if raw['base']['repo']['private'] or raw['head']['repo']['private']:
        raise ValueError('This initial coordinator supports public test repositories only.')
    for side in ('base', 'head'):
        if not re.fullmatch(r'[0-9a-f]{40}', raw[side]['sha']):
            raise ValueError('GitHub returned an invalid commit SHA.')
    if raw['base']['repo']['full_name'].lower() != f'{owner}/{repo}'.lower():
        raise ValueError('PR base repository does not match the requested URL.')
    return {'url': raw['html_url'], 'title': raw['title'], 'number': int(number),
            'repository': f'{owner}/{repo}', 'base': raw['base']['sha'],
            'head': raw['head']['sha'], 'changed_files': raw['changed_files']}


def assert_same_revision(before, after):
    if any(before[key] != after[key] for key in ('repository', 'base', 'head')):
        raise RuntimeError('PR revisions changed during this run. Results are not current; start a new run.')


def prepare_checkout(folder, details, timeout=300):
    checkout = folder / 'checkout'
    checkout.mkdir()
    def git(*args):
        with (folder / 'git-errors.log').open('ab') as errors:
            result = subprocess.run(['git', '-c', f'safe.directory={checkout.as_posix()}',
                                     '-c', 'core.autocrlf=false', '-c', 'core.longpaths=true', '-c', 'core.hooksPath=/dev/null',
                                     '-C', str(checkout), *args], stdout=subprocess.PIPE,
                                    stderr=errors, timeout=timeout, check=False)
        if result.returncode:
            raise RuntimeError('Git preparation failed; see git-errors.log.')
        return result.stdout
    git('init')
    remote = 'https://github.com/' + details['repository'] + '.git'
    # Fetch exact objects rather than a moving branch. Full ancestry is needed for merge-base.
    git('fetch', '--no-tags', remote, details['base'], details['head'])
    git('checkout', '--detach', details['head'])
    merge_base = git('merge-base', details['base'], details['head']).decode().strip()
    diff = git('diff', '--no-ext-diff', '--no-textconv', merge_base, details['head'], '--')
    if not diff.strip():
        raise ValueError('PR has no reviewable diff.')
    changed = git('diff', '--name-only', '-z', merge_base, details['head'], '--').split(b'\0')
    if len([name for name in changed if name]) != details['changed_files']:
        raise ValueError('Fetched change count does not match GitHub; retry with a stable PR.')
    (folder / 'input.diff').write_bytes(diff)
    return checkout, merge_base


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pr', required=True)
    parser.add_argument('--prepare-only', action='store_true', help='Verify PR input without calling Docker or Pi')
    parser.add_argument('--output', type=Path, default=Path('out/pr-reviews'))
    parser.add_argument('--budget', type=int, default=16000)
    parser.add_argument('--context-budget', type=int, default=32000)
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--provider', choices=['openrouter'], default='openrouter', help='Reviews use OpenRouter only; other providers are rejected.')
    parser.add_argument('--model', default='anthropic/claude-sonnet-4.6')
    parser.add_argument('--image', default='arch-drift')
    args = parser.parse_args(argv)
    try:
        identity = parse_pr(args.pr)
    except ValueError as error:
        parser.error(str(error))
    if min(args.budget, args.context_budget, args.timeout) <= 0:
        parser.error('Budgets and timeout must be positive.')
    args.output.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),
                                  dir=args.output.resolve()))
    started = time.monotonic()
    summary = {'status': 'preparing', 'pr_url': args.pr, 'posted': False}
    def finish(status, code, error=None):
        summary.update(status=status, elapsed_seconds=round(time.monotonic() - started, 2))
        if error:
            summary['error'] = str(error)
            print(str(error), flush=True)
        review_local.save(folder / 'pr-summary.json', summary)
        print(f'FINISHED: {status}. Evidence: {folder}', flush=True)
        return code
    try:
        gh = resolve_gh()
        print('PR: reading base and head revisions.', flush=True)
        details = metadata(gh, *identity)
        review_local.save(folder / 'pr.json', details)
        print('PR: fetching exact commits into a separate checkout.', flush=True)
        checkout, base = prepare_checkout(folder, details, args.timeout)
        summary.update(head=details['head'], base=details['base'], merge_base=base,
                       changed_files=details['changed_files'],
                       diff_sha256=hashlib.sha256((folder / 'input.diff').read_bytes()).hexdigest())
        assert_same_revision(details, metadata(gh, *identity))
        print(f'PASSED: fixed PR input; {details["changed_files"]} changed files.', flush=True)
        if args.prepare_only:
            return finish('input_ready', 0)
        print('REVIEW: handing the PR diff and matching code to the existing local reviewer.', flush=True)
        code = review_local.main(['--diff', str(folder / 'input.diff'), '--repo', str(checkout),
                                  '--base', base, '--output', str(folder / 'review'),
                                  '--budget', str(args.budget), '--context-budget', str(args.context_budget),
                                  '--timeout', str(args.timeout), '--provider', args.provider,
                                  '--model', args.model, '--image', args.image])
        summaries = list((folder / 'review').glob('*/review-summary.json'))
        if len(summaries) == 1:
            summary['review'] = review_local.read(summaries[0])
            summary['review_folder'] = str(summaries[0].parent)
        if code:
            return finish('review_failed', code)
        assert_same_revision(details, metadata(gh, *identity))
        return finish('review_completed', 0)
    except Exception as error:
        return finish('failed', 1, error)


if __name__ == '__main__':
    raise SystemExit(main())
