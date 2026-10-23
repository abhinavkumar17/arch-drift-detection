import difflib
import pytest
from classify_pr import classify, DEFAULT_POLICY

def diff(path, old, new):
    return ''.join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), 'a/' + path, 'b/' + path))

def test_dependency_rule_avoids_model():
    def forbidden(prompt):
        pytest.fail('Rules must not call a model')
    result = classify(diff('gradle/libs.versions.toml', '[versions]\nkotlin = "2.0"\n', '[versions]\nkotlin = "2.1"\n'), model_call=forbidden)
    assert result['category'] == 'dependency_update'
    assert not result['model_attempted']

def test_translation_rule():
    result = classify(diff('app/src/main/res/values-fr/strings.xml', '<string name="hello">Bonjour</string>\n', '<string name="hello">Salut</string>\n'))
    assert result['category'] == 'translation_update'

def test_release_requires_explicit_repository_policy():
    patch = diff('release.properties', 'versionCode=3\n', 'versionCode=4\n')
    assert classify(patch)['category'] == 'full_review'
    assert classify(patch, {**DEFAULT_POLICY, 'release_files': ['release.properties']})['category'] == 'release_metadata'

@pytest.mark.parametrize('path,old,new', [
    ('gradle/libs.versions.toml', '[libraries]\na = "1"\n', '[libraries]\na = "2"\n'),
    ('app/src/main/res/values-fr/strings.xml', '<string name="x">Hello %s</string>\n', '<string name="x">Hello</string>\n'),
    ('app/src/main/res/values/strings.xml', '<string name="x">Hello</string>\n', '<string name="x">Hi</string>\n'),
    ('Foo.kt', 'val x = 1\n', 'val x = 2\n'),
])
def test_uncertain_content_full_review(path, old, new):
    assert classify(diff(path, old, new))['category'] == 'full_review'

def test_mixed_changes_not_dependency_only():
    patch = diff('gradle/libs.versions.toml', '[versions]\na = "1"\n', '[versions]\na = "2"\n') + diff('Foo.kt', 'val a=1\n', 'val a=2\n')
    result = classify(patch)
    assert result['category'] == 'full_review'
    assert len(result['files']) == 2

def test_valid_model_answer_is_advisory():
    result = classify(diff('Foo.kt', 'a\n', 'b\n'), model_call=lambda p: {'category': 'full_review', 'reason': 'Application change', 'files': ['Foo.kt'], 'uncertain': False, 'areas': []})
    assert result['source'] == 'model'
    assert result['model_attempted'] and result['advisory']

@pytest.mark.parametrize('answer', [
    {'category': 'translation_update', 'reason': 'x', 'files': [], 'uncertain': False},
    {'category': 'translation_update', 'reason': 'x', 'files': ['Foo.kt'], 'uncertain': True},
    {'category': 'made_up', 'reason': 'x', 'files': ['Foo.kt'], 'uncertain': False},
    {},
])
def test_invalid_model_falls_back(answer):
    result = classify(diff('Foo.kt', 'a\n', 'b\n'), model_call=lambda p: answer)
    assert result['category'] == 'full_review' and result['source'] == 'fallback'

def test_budget_stops_call():
    def forbidden(prompt):
        pytest.fail('Oversized input must not call model')
    result = classify(diff('Foo.kt', 'a\n', 'b\n'), model_call=forbidden, limit=1)
    assert not result['model_attempted']
    assert result['category'] == 'full_review'

def test_model_error_falls_back():
    def fail(prompt):
        raise TimeoutError('timeout')
    assert classify(diff('Foo.kt', 'a\n', 'b\n'), model_call=fail)['source'] == 'fallback'

def test_malformed_diff_falls_back():
    assert classify('not a diff')['category'] == 'full_review'

@pytest.mark.parametrize('tag,path,evidence,valid', [
    ('authentication','Foo.kt','b',True),
    ('made_up','Foo.kt','b',False),
    ('security','Other.kt','b',False),
    ('security','Foo.kt','not present',False),
])
def test_area_evidence(tag,path,evidence,valid):
    answer = {'category':'full_review','reason':'App code','files':['Foo.kt'],'uncertain':False,
              'areas':[{'tag':tag,'path':path,'evidence':evidence,'reason':'Affected code'}]}
    result = classify(diff('Foo.kt','a\n','b\n'),model_call=lambda p:answer)
    assert (result['source'] == 'model') == valid

def test_rules_do_not_claim_area_assessment():
    result = classify(diff('gradle/libs.versions.toml','[versions]\na="1"\n','[versions]\na="2"\n'))
    assert result['areas_status'] == 'not_assessed'

def test_evidence_indentation_ignored_but_content_preserved():
    answer = {'category':'full_review','reason':'App code','files':['Foo.kt'],'uncertain':False,
              'areas':[{'tag':'database_migration','path':'Foo.kt','evidence':'db.migrate(2)','reason':'Migration changed'}]}
    patch = diff('Foo.kt','    db.migrate(1)\n','    db.migrate(2)\n')
    assert classify(patch,model_call=lambda p:answer)['source'] == 'model'
    answer['areas'][0]['evidence'] = 'db.migrate(3)'
    assert classify(patch,model_call=lambda p:answer)['source'] == 'fallback'
