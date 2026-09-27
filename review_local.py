"""Coordinate Docker preparation and local Pi; never post findings to GitHub."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading


def run_lookup(command, folder, timeout, say):
    """Stream structured Pi events, preserving raw tool results in the evidence log."""
    with (folder / 'model-errors.log').open('w', encoding='utf-8') as errors:
        process = subprocess.Popen(command, cwd=folder, stdout=subprocess.PIPE, stderr=errors,
                                   text=True, encoding='utf-8', errors='replace')
        timed_out = threading.Event()
        def stop():
            timed_out.set()
            process.kill()
        timer = threading.Timer(timeout, stop)
        timer.start()
        try:
            with (folder / 'tool-events.jsonl').open('w', encoding='utf-8') as log:
                for line in process.stdout:
                    log.write(line)
                    log.flush()
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    kind = event.get('type')
                    if kind == 'tools_enabled':
                        say('TOOLS ENABLED: ' + ', '.join(event['tools']))
                    elif kind == 'tool_start':
                        say('TOOL: ' + event['tool'] + ' ' + json.dumps(event['input'], ensure_ascii=True))
                    elif kind == 'tool_result':
                        say('TOOL RESULT: ' + event['tool'] + (' (truncated)' if event['truncated'] else ' completed'))
                    elif kind == 'request_budget':
                        say(f"REQUEST: {event['request']}; estimated context {event['estimated_tokens']} / {event['input_limit']} tokens")
                    elif kind in ('tool_error', 'review_error'):
                        say('LOOKUP: ' + event['error'])
                    elif kind == 'usage':
                        say('USAGE: provider-reported usage saved in tool-events.jsonl')
                    elif kind in ('model_started', 'model_finished', 'auto_compaction_start', 'auto_compaction_end', 'auto_retry_start', 'auto_retry_end'):
                        say('PI: ' + kind.replace('_', ' '))
            code = process.wait()
            if timed_out.is_set():
                raise TimeoutError('Repository review exceeded its time allowance.')
            return code
        finally:
            timer.cancel()
            if process.poll() is None:
                process.kill()
                process.wait()


def save(path, value):
    path.write_text(json.dumps(value, indent=2), encoding='utf-8')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def run_process(command, cwd, stdout, stderr, timeout):
    with stdout.open('w', encoding='utf-8') as output, stderr.open('w', encoding='utf-8') as errors:
        return subprocess.run(command, cwd=cwd, stdout=output, stderr=errors,
                              timeout=timeout, check=False).returncode


def pi_command(executable):
    # Invoke Node directly on Windows, avoiding cmd.exe shell quoting for .cmd shims.
    if Path(executable).suffix.lower() == '.cmd':
        cli = Path(executable).parent / 'node_modules/@earendil-works/pi-coding-agent/dist/cli.js'
        node = shutil.which('node')
        if not node or not cli.is_file():
            raise RuntimeError('Cannot resolve Pi Node entry point; check your Node and Pi installation.')
        return [node, str(cli)]
    return [executable]


def validate_response(payload, diff):
    from core.annotate import annotate, allow_list, is_in_diff
    if not isinstance(payload, dict) or set(payload) != {'findings', 'limitations'}:
        raise ValueError('Response must contain findings and limitations only.')
    if not isinstance(payload['findings'], list) or not isinstance(payload['limitations'], list):
        raise ValueError('Findings and limitations must be lists.')
    if any(not isinstance(item, str) for item in payload['limitations']):
        raise ValueError('Each limitation must be text.')
    allowed = allow_list(annotate(diff))
    text_fields = ('path', 'side', 'principle', 'title', 'explanation', 'evidence', 'suggested_change')
    for index, finding in enumerate(payload['findings']):
        if not isinstance(finding, dict) or set(finding) != set(text_fields) | {'line'}:
            raise ValueError(f'Finding {index + 1} has incorrect fields.')
        if any(not isinstance(finding[key], str) or not finding[key].strip() for key in text_fields):
            raise ValueError(f'Finding {index + 1} has empty or invalid text.')
        if type(finding['line']) is not int or finding['line'] <= 0:
            raise ValueError(f'Finding {index + 1} has an invalid line.')
        if not is_in_diff(finding['path'], finding['line'], finding['side'], allowed):
            raise ValueError(f'Finding {index + 1} does not reference an allowed changed line.')
    return payload


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diff', type=Path, required=True)
    parser.add_argument('--repo', type=Path, help='Enable read-only source lookup from this checkout; diff must match HEAD changes')
    parser.add_argument('--context-budget', type=int, default=32000, help='Estimated per-request context limit in lookup mode, separate from initial prep budget')
    parser.add_argument('--output', type=Path, default=Path('out/local-reviews'))
    parser.add_argument('--image', default='arch-drift')
    parser.add_argument('--budget', type=int, default=16000)
    parser.add_argument('--provider', default='openai-codex')
    parser.add_argument('--model', default='gpt-5.5')
    parser.add_argument('--timeout', type=int, default=600, help='Seconds allowed for each external step')
    args = parser.parse_args(argv)
    if args.budget <= 0 or args.timeout <= 0 or args.context_budget <= 0:
        parser.error('Budget and timeout must be positive.')
    if not args.diff.is_file():
        parser.error('Diff file does not exist.')
    args.output.mkdir(parents=True, exist_ok=True)
    folder = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'),
                                  dir=args.output.resolve()))
    status = {'status': 'preparing', 'model_invocation_attempted': False,
              'provider': args.provider, 'model': args.model, 'image': args.image,
              'input_budget': args.budget}
    def say(message):
        print(message, flush=True)
        with (folder / 'review.log').open('a', encoding='utf-8') as log:
            log.write(message + '\n')
    def finish(state, code, error=None):
        status['status'] = state
        if error:
            status['error'] = str(error)
        save(folder / 'review-summary.json', status)
        say(f'FINISHED: {state}. Evidence: {folder}')
        return code
    say(f'Evidence folder: {folder}')
    phase = 'preparation_failed'
    try:
        # Check local validation dependencies before spending on a model call.
        from core.annotate import annotate
        docker = shutil.which('docker')
        pi = shutil.which('pi.cmd' if os.name == 'nt' else 'pi')
        if not docker or not pi:
            raise RuntimeError('Docker and Pi must be installed and available on PATH.')
        pi_args = pi_command(pi)
        source = folder / 'input.diff'
        source.write_bytes(args.diff.read_bytes())
        annotate(source.read_text(encoding='utf-8-sig'))
        status['diff_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        if args.repo:
            from repo_context import snapshot_repository
            say('PREPARATION: capturing tracked source files for read-only lookup.')
            manifest = snapshot_repository(args.repo, source, folder / 'repository')
            status['repository_head'] = manifest['head']
            status['repository_files'] = len(manifest['files'])
            status['review_mode'] = 'repository_lookup'
            status['context_budget_estimated'] = args.context_budget
            sdk = Path(pi_args[-1]).parent / 'index.js'
            if not sdk.is_file():
                raise RuntimeError('Cannot resolve installed Pi SDK. This lookup adapter requires the Node-based Pi installation.')
        if ',' in str(folder):
            raise ValueError('The output path cannot contain a comma (Docker mount syntax).')
        save(folder / 'review-summary.json', status)
        say('RUNNING: Docker preparation. Detailed output: preparation.log')
        code = run_process([docker, 'run', '--rm', '--env', 'EVIDENCE_BUCKET=', '--mount',
                            f'type=bind,source={folder},target=/work', args.image,
                            '--diff', '/work/input.diff', '--output', '/work/preparation',
                            '--budget', str(args.budget)], folder, folder / 'preparation.log',
                           folder / 'preparation-errors.log', args.timeout)
        status['preparation_exit_code'] = code
        runs = list((folder / 'preparation').glob('*/summary.json'))
        if len(runs) != 1:
            raise RuntimeError('Expected exactly one preparation summary; inspect preparation logs.')
        prepared = runs[0].parent
        summary = read(prepared / 'summary.json')
        report = read(prepared / 'budget-report.json') if (prepared / 'budget-report.json').exists() else {}
        if code == 2 and summary.get('status') == 'over_budget':
            return finish('over_budget', 2)
        if code != 0 or summary.get('status') != 'ready' or report.get('fits') is not True:
            raise RuntimeError('Preparation did not succeed with a fitting prompt; Pi was not called.')
        if any(summary.get('steps', {}).get(step) != 'passed'
               for step in ('tests', 'diff', 'annotation', 'prompt_budget')):
            raise RuntimeError('Preparation step status is incomplete.')
        if report.get('input_budget') != args.budget or report.get('estimated_tokens', args.budget + 1) > args.budget:
            raise RuntimeError('Budget report is inconsistent.')
        prompt = prepared / 'prompt.txt'
        if not prompt.is_file() or not prompt.stat().st_size:
            raise RuntimeError('Prepared prompt is missing or empty.')
        if (prepared / 'pr.diff').read_bytes() != source.read_bytes():
            raise RuntimeError('Prepared diff differs from the supplied input.')
        status['prompt_sha256'] = hashlib.sha256(prompt.read_bytes()).hexdigest()
        status['estimated_tokens'] = report['estimated_tokens']
        say('PASSED: Preparation and budget. Starting local Pi with the saved prompt.')
        phase = 'model_failed'
        status['status'] = 'reviewing'
        status['model_invocation_attempted'] = True
        save(folder / 'review-summary.json', status)
        # Fresh session, no repository discovery or tools; review only the provided input.
        if args.repo:
            config = {'snapshot': str(folder / 'repository'), 'manifest': manifest,
                      'output': str(folder), 'prompt': str(prompt), 'sdk': str(sdk),
                      'provider': args.provider, 'model': args.model, 'contextBudget': args.context_budget}
            save(folder / 'lookup-config.json', config)
            code = run_lookup([pi_args[0], str(Path(__file__).with_name('pi_repo_review.mjs')),
                               str(folder / 'lookup-config.json')], folder, args.timeout, say)
            if (folder / 'lookup-summary.json').exists():
                status['lookup'] = read(folder / 'lookup-summary.json')
        else:
            code = run_process(pi_args + ['--print', '--no-tools', '--no-extensions', '--no-skills',
                           '--no-context-files', '--no-prompt-templates', '--no-session',
                           '--provider', args.provider, '--model', args.model, '@' + str(prompt)],
                           folder, folder / 'model-response.txt', folder / 'model-errors.log', args.timeout)
        status['model_exit_code'] = code
        if code:
            raise RuntimeError('Pi failed; inspect model-errors.log and model-response.txt.')
        phase = 'invalid_response'
        payload = validate_response(read(folder / 'model-response.txt'), source.read_text(encoding='utf-8-sig'))
        save(folder / 'findings.json', payload)
        status['finding_count'] = len(payload['findings'])
        status['limitation_count'] = len(payload['limitations'])
        say(f'PASSED: Response format and locations validated; {status["finding_count"]} findings. This does not validate reasoning accuracy.')
        return finish('review_completed', 0)
    except Exception as error:
        return finish(phase, 1, error)


if __name__ == '__main__':
    raise SystemExit(main())
