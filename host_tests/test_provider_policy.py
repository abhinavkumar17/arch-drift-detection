import pytest
import review_local
import review_pr

@pytest.mark.parametrize('module,args', [
    (review_local, ['--diff', 'missing.diff']),
    (review_pr, ['--pr', 'https://github.com/example/repo/pull/1']),
])
@pytest.mark.parametrize('provider', ['openai-codex', 'google', 'anthropic'])
def test_other_providers_rejected_before_external_calls(module, args, provider, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        pytest.fail('External operation attempted for rejected provider')
    monkeypatch.setattr(module.subprocess, 'run', forbidden)
    monkeypatch.setattr(module.subprocess, 'Popen', forbidden)
    with pytest.raises(SystemExit) as error:
        module.main(args + ['--provider', provider])
    assert error.value.code == 2
    assert 'invalid choice' in capsys.readouterr().err

@pytest.mark.parametrize('module', [review_local, review_pr])
def test_openrouter_defaults(module, monkeypatch):
    original = module.argparse.ArgumentParser.parse_args
    captured = {}
    def capture(parser, args):
        result = original(parser, args)
        captured.update(vars(result))
        raise SystemExit(0)
    monkeypatch.setattr(module.argparse.ArgumentParser, 'parse_args', capture)
    args = ['--diff', 'unused.diff'] if module is review_local else ['--pr', 'unused']
    with pytest.raises(SystemExit):
        module.main(args)
    assert captured['provider'] == 'openrouter'
    assert captured['model'] == 'anthropic/claude-sonnet-4.6'