from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest
from sequence_analyser import analyse_sequence


def item(kind, **kwargs):
    return {'$type': f'NINA.Sequencer.SequenceItem.Imaging.{kind}, NINA.Sequencer', **kwargs}


def group(items=(), conditions=(), triggers=(), **kwargs):
    return {'$type': 'NINA.Sequencer.Container.SequentialContainer, NINA.Sequencer',
            'Name': 'Test sequence', 'Items': list(items), 'Conditions': list(conditions),
            'Triggers': list(triggers), **kwargs}


def analyse(node):
    return analyse_sequence(json.dumps(node))


def test_exposures_waits_and_nested_loops():
    inner = group([item('TakeExposure', ExposureTime=30), item('WaitForTimeSpan', Time=2.5)],
                  [item('LoopCondition', Iterations=4)])
    result = analyse(group([inner], [item('LoopCondition', Iterations=3)]))
    assert [r['Expected time'] for r in result.rows] == ['6 min', '30 s']
    assert all(r['Type'] == 'Instruction' and r['Enabled'] == 'Unknown' for r in result.rows)
    assert '12 repetitions' in result.rows[0]['Note']


def test_jsonnet_references_wrappers_and_parent_backreferences():
    child = item('TakeExposure', ExposureTime=60, Parent={'$ref': 'root'})
    root = group(**{'$id': 'root'})
    root['Items'] = {'$id': 'items', '$values': [child]}
    root['Triggers'] = {'$values': []}
    root['Conditions'] = {'$values': []}
    result = analyse(root)
    assert len(result.rows) == 1
    assert result.rows[0]['Expected time'] == '1 min'


@pytest.mark.parametrize('flag', [{'IsEnabled': False}, {'Enabled': 'false'}, {'IsDisabled': True}, {'Status': 5}, {'Status': 'DISABLED'}])
def test_disabled_steps_and_inherited_disabling(flag):
    result = analyse(group([group([item('TakeExposure', ExposureTime=30)], **flag)]))
    assert result.rows[0]['Enabled'] == 'No'
    assert result.rows[0]['Expected time'] == '0 s'
    assert 'parent' in result.rows[0]['Note']


def test_missing_status_is_unknown_instead_of_enabled():
    result = analyse(group([item('TakeExposure', Name='Deep Sky OSC 2', ExposureTime=60)]))
    assert result.rows[0]['Enabled'] == 'Unknown'
    assert result.unknown_enabled
    assert 'assumes enabled' in result.rows[0]['Note']


def test_explicit_status_and_inherited_unknown_status():
    result = analyse(group([item('TakeExposure', IsEnabled=True, ExposureTime=60)], IsEnabled=True))
    assert result.rows[0]['Enabled'] == 'Yes'
    assert not result.unknown_enabled
    result = analyse(group([item('TakeExposure', IsEnabled=True, ExposureTime=60)]))
    assert result.rows[0]['Enabled'] == 'Unknown'
    result = analyse(group([item('TakeExposure', IsEnabled=False, ExposureTime=60)]))
    assert result.rows[0]['Enabled'] == 'No'
    assert result.rows[0]['Expected time'] == '0 s'


def test_trigger_actions_are_conditional_not_fixed_totals():
    trigger = {'$type': 'NINA.Sequencer.Trigger.Guider.DitherAfterExposures, NINA',
               'TriggerRunner': group([item('WaitForTimeSpan', Time=10)])}
    result = analyse(group([item('TakeExposure', ExposureTime=60)], triggers=[trigger]))
    assert [r['Type'] for r in result.rows] == ['Instruction', 'Trigger', 'Instruction']
    assert result.rows[1]['Expected time'] == result.rows[2]['Expected time'] == 'Variable'
    assert 'Per activation/pass: 10 s' in result.rows[2]['Note']


def test_smart_exposure_counts_once_and_retains_triggers():
    smart = group([item('SwitchFilter'), item('TakeExposure', ExposureTime=120)],
                  [item('LoopCondition', Iterations=10)],
                  [dict(item('DitherAfterExposures'), TriggerRunner=group([item('Dither')]))],
                  **{'$type': 'NINA.Sequencer.SequenceItem.Imaging.SmartExposure, NINA', 'Name': 'Smart exposure'})
    result = analyse(group([smart]))
    assert result.rows[0]['Expected time'] == '≥ 20 min'
    assert len(result.rows) == 3
    assert not any('Take Exposure' in r['Trigger or instruction'] for r in result.rows)


def test_unknown_loop_conditions_and_runtime_expressions_are_variable():
    result = analyse(group([item('TakeExposure', ExposureTime=60)], [item('TimeCondition', Hours=5)]))
    assert result.rows[0]['Expected time'] == 'Variable'
    assert 'Per activation/pass: 1 min' in result.rows[0]['Note']
    result = analyse(group([item('TakeExposure', ExposureTime=60, ExposureTimeExpression={'Definition': 'target.exposure'})]))
    assert result.rows[0]['Expected time'] == 'Variable'


def test_numeric_expressions_override_saved_values_and_progress_is_ignored():
    result = analyse(group([item('TakeExposure', ExposureTime=60, ExposureCount=8,
                                 ExposureTimeExpression={'Definition': '2.5'})],
                           [item('LoopCondition', Iterations=10, CompletedIterations=9)]))
    assert result.rows[0]['Expected time'] == '25 s'


def test_multiple_loop_conditions_stop_at_first_limit_not_product():
    result = analyse(group([item('TakeExposure', ExposureTime=10)],
                           [item('LoopCondition', Iterations=3), item('LoopCondition', Iterations=5)]))
    assert result.rows[0]['Expected time'] == '30 s'


def test_unknown_plugin_and_hardware_instructions_stay_visible():
    result = analyse(group([{'$type': 'Plugin.MagicInstruction, Plugin'}, item('RunAutofocus')]))
    assert len(result.rows) == 2
    assert all(r['Expected time'] == 'Variable' for r in result.rows)
    assert 'Plugin' in result.rows[0]['Note']
    assert 'focuser' in result.rows[1]['Note']


@pytest.mark.parametrize('content', [b'{broken', b'[]', b'{"hello": "world"}', b'null'])
def test_bad_or_unrelated_json_is_rejected(content):
    with pytest.raises(ValueError):
        analyse_sequence(content)


def test_circular_and_missing_references_are_rejected():
    for root in (group([{'$ref': 'root'}], **{'$id': 'root'}), group([{'$ref': 'missing'}])):
        with pytest.raises(ValueError, match='circular|missing'):
            analyse(root)


def test_utf8_bom_and_empty_sequence():
    result = analyse_sequence(b'\xef\xbb\xbf' + json.dumps(group()).encode())
    assert result.rows == []


def test_malformed_child_lists_and_trigger_runners_report_errors():
    for root in (group(Items={'$values': 'bad'}),
                 group(triggers=[dict(item('CustomTrigger'), TriggerRunner='bad')])):
        with pytest.raises(ValueError, match='invalid'):
            analyse(root)


PAGE = str(Path(__file__).resolve().parents[1] / 'pages' / '3_Sequence_analyser.py')


def test_page_initial_state():
    app = AppTest.from_file(PAGE).run()
    assert not app.exception
    assert app.title[0].value == 'Sequence analyser'
    assert 'Choose a sequence' in app.info[0].value
    assert len(app.get('file_uploader')) == 1


def test_page_displays_uploaded_table_and_invalid_file_error():
    upload = BytesIO(json.dumps(group([item('TakeExposure', ExposureTime=90)])).encode())
    with patch('streamlit.file_uploader', return_value=upload):
        app = AppTest.from_file(PAGE).run()
    assert not app.exception
    assert next(m for m in app.metric if m.label == 'Expected sequence time').value == '00:01:30'
    assert any(c.label == 'Disable Take Exposure' for c in app.checkbox)
    with patch('streamlit.file_uploader', return_value=BytesIO(b'invalid')):
        app = AppTest.from_file(PAGE).run()
    assert not app.exception
    assert app.error and not app.dataframe
