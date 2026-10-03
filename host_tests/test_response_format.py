import pytest
from review_local import parse_model_response, validate_response

EMPTY = '{"findings": [], "limitations": []}'

@pytest.mark.parametrize('text', [EMPTY, '```json\n'+EMPTY+'\n```', 'Summary.\n```json\n'+EMPTY+'\n```\nRationale.', 'I will inspect.\n'+EMPTY])
def test_supported_wrappers(text):
    assert validate_response(parse_model_response(text), '') == {'findings': [], 'limitations': []}

@pytest.mark.parametrize('text', [EMPTY+EMPTY, '{broken} '+EMPTY, '[]', '{"findings":[],"findings":[],"limitations":[]}', '{"findings":NaN,"limitations":[]}', 'No result', '```json\n{"findings":[]', EMPTY+' []'])
def test_rejects_ambiguous_or_malformed(text):
    with pytest.raises(ValueError):
        parse_model_response(text)

def test_wrapping_does_not_bypass_schema():
    with pytest.raises(ValueError):
        validate_response(parse_model_response('```json\n{"findings": [], "other": []}\n```'), '')
