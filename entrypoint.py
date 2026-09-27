"""Local and Docker review preparation, with a test gate and saved evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent
STEPS = ('tests', 'diff', 'annotation', 'prompt_budget')


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('Must be a positive integer')
    return number


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--repo', default=os.getenv('REPO_URL', 'https://github.com/Alamofire/Alamofire.git'))
    p.add_argument('--commits', type=positive, default=20)
    p.add_argument('--head', default=os.getenv('HEAD_REF', 'HEAD'))
    p.add_argument('--base', default=os.getenv('BASE'))
    p.add_argument('--diff', type=Path, help='Use an existing diff instead of cloning')
    p.add_argument('--output', type=Path, default=Path(os.getenv('OUTPUT_DIR', 'out/runs')))
    p.add_argument('--budget', type=positive, default=800000)
    p.add_argument('--evidence-bucket', default=os.getenv('EVIDENCE_BUCKET'),
                   help='Optionally upload run evidence to S3')
    return p


def command(args, destination, cwd=ROOT):
    with destination.open('w', encoding='utf-8') as log:
        result = subprocess.run(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f'Command failed (exit {result.returncode}); details: {destination.name}')


def main(argv=None):
    args = parser().parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=args.output))
    summary = {'status': 'running', 'steps': {name: 'pending' for name in STEPS}, 'model_called': False}
    current = 'tests'
    exit_code = 1

    def say(message):
        print(message, flush=True)
        with (folder / 'run.log').open('a', encoding='utf-8') as log:
            log.write(message + '\n')

    def save():
        (folder / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    def start(step):
        nonlocal current
        current = step
        summary['steps'][step] = 'running'
        save()
        say(f'RUNNING: {step}')

    def passed(detail):
        summary['steps'][current] = 'passed'
        save()
        say(f'PASSED: {detail}')

    say(f'Evidence folder: {folder.resolve()}')
    try:
        start('tests')
        command([sys.executable, '-m', 'pytest', 'tests', '-v', '-p', 'no:cacheprovider', f'--junitxml={folder.resolve() / "tests.xml"}'], folder / 'tests.log')
        passed('Application tests. See tests.log and tests.xml; this is not an architecture verdict.')
        start('diff')
        diff = folder / 'pr.diff'
        if args.diff:
            diff.write_bytes(args.diff.read_bytes())
            summary['source'] = {'saved_diff': str(args.diff.resolve())}
        else:
            repo = folder.resolve() / 'repo'
            command(['git', 'clone', '--quiet', '--', args.repo, str(repo)], folder / 'clone.log')
            def resolve(ref):
                return subprocess.check_output(['git', 'rev-parse', '--verify', '--end-of-options', ref + '^{commit}'], cwd=repo, text=True, stderr=subprocess.PIPE).strip()
            head = resolve(args.head)
            base = resolve(args.base or f'{head}~{args.commits}')
            with diff.open('wb') as output, (folder / 'git-diff.log').open('wb') as errors:
                subprocess.run(['git', 'diff', '--no-ext-diff', '--no-textconv', base, head, '--'], cwd=repo, stdout=output, stderr=errors, check=True)
            summary['source'] = {'repository': args.repo, 'base_commit': base, 'head_commit': head}
        passed('Input saved as pr.diff; exact source recorded in summary.json.')
        start('annotation')
        command([sys.executable, str(ROOT / 'annotate.py'), str(diff.resolve())], folder / 'annotation.log')
        passed('Annotated lines saved in annotation.log.')
        start('prompt_budget')
        from core.prompt import prepare_prompt
        template = ROOT / 'REVIEW_TEMPLATE.md'
        guidelines = ROOT / 'GUIDELINES_V2.md'
        result = prepare_prompt(template.read_text(encoding='utf-8'), guidelines.read_text(encoding='utf-8'), diff.read_text(encoding='utf-8'), args.budget)
        (folder / 'prompt.txt').write_text(result.text, encoding='utf-8')
        report = {'input_budget': result.input_budget, 'estimated_tokens': result.estimated_tokens, 'fits': result.fits, 'estimator': 'ceil(characters / 3)', 'budget_trimming': False, 'input_sha256': {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in [('diff', diff), ('template', template), ('guidelines', guidelines)]}}
        (folder / 'budget-report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        summary['status'] = 'ready' if result.fits else 'over_budget'
        summary['steps'][current] = 'passed' if result.fits else 'over_budget'
        say(f'{summary["status"].upper()}: {result.estimated_tokens:,} estimated tokens / {args.budget:,} input budget. Prompt and budget report saved; no model called.')
        if not result.fits:
            say('Stopped: reduce the code-change scope. No files were trimmed to fit.')
        exit_code = 0 if result.fits else 2
    except Exception as error:
        summary['status'] = 'failed'
        summary['steps'][current] = 'failed'
        summary['error'] = str(error)
        for step in STEPS:
            if summary['steps'][step] == 'pending':
                summary['steps'][step] = 'skipped'
        say(f'FAILED: {current}: {error}. Later steps skipped.')
        exit_code = 1
    finally:
        save()
        say(f'Finished: {summary["status"]}. See summary.json.')


    if args.evidence_bucket:
        try:
            from core.evidence import upload_evidence

            say('RUNNING: Saving evidence to S3.')
            destination = upload_evidence(folder=folder, bucket=args.evidence_bucket)
            say(f'PASSED: Evidence saved to {destination}')
        except Exception as error:
            say(f'FAILED: Evidence upload: {error}')
            exit_code = 1
    else:
        say('S3 upload not configured; evidence saved locally.')

    return exit_code

if __name__ == '__main__':
    sys.exit(main())
