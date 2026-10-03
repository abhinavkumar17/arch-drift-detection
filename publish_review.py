"""Preview or publish validated local PR findings as an inline GitHub review."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

from review_local import read, save, validate_response, parse_model_response
from review_pr import parse_pr, resolve_gh, metadata, assert_same_revision


def api(gh, endpoint, payload=None):
    command = [gh, 'api', endpoint]
    if payload is None:
        command += ['--paginate', '--slurp']
    else:
        command += ['--method', 'POST', '--input', '-']
    result = subprocess.run(command, input=json.dumps(payload).encode() if payload else None,
                            capture_output=True, timeout=60, check=False)
    if result.returncode:
        raise RuntimeError('GitHub request failed; no automatic submission retry was attempted.')
    return json.loads(result.stdout)


def build_payload(folder):
    summary = read(folder / 'pr-summary.json')
    details = read(folder / 'pr.json')
    if summary.get('status') != 'review_completed':
        raise ValueError('A completed PR review is required.')
    assert_same_revision(details, dict(repository=details['repository'], base=summary['base'], head=summary['head']))
    review = Path(summary['review_folder']).resolve()
    if not review.is_relative_to(folder.resolve()):
        raise ValueError('Review evidence must be inside this run folder.')
    diff = (folder / 'input.diff').read_bytes()
    if hashlib.sha256(diff).hexdigest() != summary['diff_sha256']:
        raise ValueError('Saved diff has changed since review.')
    local = read(review / 'review-summary.json')
    if (local.get('status') != 'review_completed' or local.get('diff_sha256') != summary['diff_sha256']
            or local.get('repository_head') != details['head']):
        raise ValueError('Review provenance does not match the PR.')
    findings = validate_response(read(review / 'findings.json'), diff.decode('utf-8-sig'))
    if findings != parse_model_response((review / 'model-response.txt').read_text(encoding='utf-8-sig')):
        raise ValueError('Findings differ from the saved model response.')
    if not findings['findings']:
        raise ValueError('No findings to post.')
    comments = []
    for item in findings['findings']:
        body = (f"**{item['title']}**\n\n{item['explanation']}\n\n"
                f"**Principle:** {item['principle']}\n\n**Evidence:** {item['evidence']}\n\n"
                f"**Suggested change:** {item['suggested_change']}")
        # Avoid accidental notifications from model-generated text.
        body = body.replace('@', '@\u200b')
        comments.append(dict(path=item['path'], line=item['line'], side=item['side'], body=body))
    fingerprint = hashlib.sha256(json.dumps([details['repository'], details['number'], details['head'], comments],
                                           sort_keys=True).encode()).hexdigest()
    marker = '<!-- arch-drift-review:' + fingerprint + ' -->'
    body = 'Architecture review from the local Pi pipeline. Findings are model-generated; format and changed-line locations were validated.'
    if findings['limitations']:
        body += '\n\nLimitations:\n' + '\n'.join('- ' + value.replace('@', '@\u200b') for value in findings['limitations'])
    return details, dict(commit_id=details['head'], event='COMMENT', body=body + '\n\n' + marker, comments=comments), marker


def publish(folder, submit=False):
    folder = Path(folder).resolve()
    # Atomic local lock prevents concurrent submissions from this evidence folder.
    lock = folder / 'publish.lock'
    with lock.open('x'):
        pass
    try:
        details, payload, marker = build_payload(folder)
        identity = parse_pr(details['url'])
        gh = resolve_gh()
        assert_same_revision(details, metadata(gh, *identity))
        endpoint = f"repos/{details['repository']}/pulls/{details['number']}/reviews"
        pages = api(gh, endpoint)
        existing = next((item for page in pages for item in page
                         if marker in (item.get('body') or '') and item.get('commit_id') == details['head']), None)
        if existing:
            receipt = dict(status='already_posted', url=existing['html_url'], id=existing['id'])
            save(folder / 'publish-result.json', receipt)
            return receipt
        save(folder / 'review-to-post.json', payload)
        if not submit:
            return dict(status='preview_ready', comments=len(payload['comments']))
        journal = folder / 'publish-attempt.json'
        if journal.exists():
            raise RuntimeError('An earlier submission may have reached GitHub. Inspect it before retrying.')
        assert_same_revision(details, metadata(gh, *identity))
        save(journal, dict(status='submission_started', marker=marker, head=details['head']))
        result = api(gh, endpoint, payload)
        receipt = dict(status='posted', url=result['html_url'], id=result['id'], head=details['head'])
        save(folder / 'publish-result.json', receipt)
        summary = read(folder / 'pr-summary.json')
        summary.update(posted=True, review_url=result['html_url'])
        save(folder / 'pr-summary.json', summary)
        return receipt
    finally:
        lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    parser.add_argument('--post', action='store_true', help='Submit the review; default only prepares a preview')
    args = parser.parse_args()
    try:
        print(json.dumps(publish(args.run, args.post), indent=2))
        return 0
    except Exception as error:
        print('Publishing stopped: ' + str(error))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
