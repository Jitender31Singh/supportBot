from trackobit_assistant.services.output_analyzer import condition_matches, analyze_command_output

def test_safe_condition_parser():
    assert condition_matches(1,'< 2')
    assert condition_matches(False,'== false')
    assert not condition_matches(4,'< 2')
    assert not condition_matches(1,"__import__('os').system('id')")

def test_analyze_rule():
    command={'analysis':{'rules':[{'field':'gsm_signal','condition':'< 2','finding':'Weak signal','advice':'Move vehicle'}]}}
    result=analyze_command_output(command,{'gsm_signal':1})
    assert result['verdict']=='issue_found'


def test_missing_expected_fields_is_inconclusive():
    command = {'output_schema': {'gps_fix': {'type': 'string'}, 'gsm_signal': {'type': 'integer'}},
               'analysis': {'rules': [{'field': 'gsm_signal', 'condition': '< 2'}]}}
    result = analyze_command_output(command, {'gsm_signal': 4})
    assert result['verdict'] == 'inconclusive'
    assert 'gps_fix' in result['evidence'][0]


def test_ruleless_command_does_not_claim_ok():
    command = {'output_schema': {'apn': {'type': 'string'}, 'server': {'type': 'string'}},
               'analysis': {'rules': []}}
    result = analyze_command_output(command, {'apn': 'internet', 'server': 'tracker.example'})
    assert result['verdict'] == 'inconclusive'
