import pytest
import publish_review as publisher


@pytest.mark.parametrize('scenario', ['preview', 'duplicate', 'stale', 'uncertain'])
def test_publish_guards(tmp_path, monkeypatch, scenario):
    details = dict(url='https://github.com/a/b/pull/1', repository='a/b', number=1, base='a'*40, head='b'*40)
    monkeypatch.setattr(publisher, 'build_payload', lambda folder: (details, {'comments': [{}]}, 'marker'))
    monkeypatch.setattr(publisher, 'resolve_gh', lambda: 'gh')
    monkeypatch.setattr(publisher, 'metadata', lambda *args: dict(details, head='c'*40) if scenario == 'stale' else details)
    calls = []
    def api(*args):
        calls.append(args)
        assert len(args) == 2, 'No POST is permitted in these scenarios'
        return [[dict(body='marker', commit_id=details['head'], id=7, html_url='https://github.com/a/b/pull/1#review')]] if scenario == 'duplicate' else [[]]
    monkeypatch.setattr(publisher, 'api', api)
    if scenario == 'uncertain':
        (tmp_path / 'publish-attempt.json').write_text('{}')
    if scenario in ('stale', 'uncertain'):
        with pytest.raises(RuntimeError):
            publisher.publish(tmp_path, submit=True)
    else:
        result = publisher.publish(tmp_path, submit=scenario == 'duplicate')
        assert result['status'] == ('already_posted' if scenario == 'duplicate' else 'preview_ready')
    assert not (tmp_path / 'publish.lock').exists()


def test_existing_lock_blocks_submission(tmp_path):
    (tmp_path / 'publish.lock').touch()
    with pytest.raises(FileExistsError):
        publisher.publish(tmp_path, True)
    assert (tmp_path / 'publish.lock').exists()
