from io import BytesIO
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

import sequence_view
from sequence_view import (SequencePlan, instruction_details, load_choices, readable_title,
                           save_choices, sequence_key)
from test_sequence_analyser import group, item


def content(document):
    return json.dumps(document).encode()


@pytest.mark.parametrize('kind', ['MessageBox', 'Annotation'])
def test_whitespace_only_messages_render_without_crashing(kind):
    source = content(group([item(kind, Text=' \r\n\t ')]))
    plan = SequencePlan(source)
    node = plan.nodes['root/items/0']
    assert readable_title(node) == node.name
    with patch('streamlit.file_uploader', return_value=BytesIO(source)):
        app = AppTest.from_file(PAGE).run()
    assert not app.exception


def sample():
    trigger = dict(item('DitherAfterExposures'), TriggerRunner=group([item('WaitForTimeSpan', Time=10)]))
    first = group([item('TakeExposure', ExposureTime=60)], triggers=[trigger], Name='Deep sky OSC 1')
    second = group([item('TakeExposure', ExposureTime=120)], triggers=[trigger], Name='Deep sky OSC 2')
    return content(group([first, second]))


@pytest.fixture(autouse=True)
def local_choices(tmp_path, monkeypatch):
    monkeypatch.setattr(sequence_view, 'SETTINGS_DIR', tmp_path / 'choices')


def test_disabled_parent_excludes_all_children_and_triggers_from_projections():
    source = sample()
    plan = SequencePlan(source)
    assert plan.projection == (180, True)
    plan = SequencePlan(source, {'root/items/1'})
    assert plan.projection == (60, True)
    assert plan.timing(plan.nodes['root/items/1']) == '0 s'
    assert all(not plan.state(node) and plan.timing(node) == '0 s'
               for key, node in plan.nodes.items() if key.startswith('root/items/1/'))
    assert all('Deep sky OSC 2' not in row['Trigger or instruction'] for row in plan.active_rows)
    assert len([r for r in plan.active_rows if r['Type'] == 'Trigger']) == 1


def test_disabling_all_groups_removes_unknown_overheads_and_gives_zero():
    plan = SequencePlan(sample(), {'root/items/0', 'root/items/1'})
    assert plan.projection == (0, False)
    assert plan.timing(plan.root) == '0 s'
    assert plan.active_rows == []


def test_root_disable_and_reenable_preserve_child_choices():
    source = sample()
    choices = {'root', 'root/items/1'}
    assert SequencePlan(source, choices).projection == (0, False)
    choices.remove('root')
    plan = SequencePlan(source, choices)
    assert plan.projection == (60, True)
    assert not plan.state(plan.nodes['root/items/1'])


def test_individual_instruction_and_trigger_disables_change_totals():
    plan = SequencePlan(sample(), {'root/items/0/items/0', 'root/items/1'})
    assert plan.projection == (0, True)  # An active conditional trigger remains.
    plan = SequencePlan(sample(), {'root/items/0/triggers/0', 'root/items/1'})
    assert plan.projection == (60, False)
    assert plan.timing(plan.root) == '1 min'


def test_parallel_loop_and_smart_exposure_totals_respect_internal_choices():
    parallel = group([item('TakeExposure', ExposureTime=60), item('TakeExposure', ExposureTime=120)],
                     [item('LoopCondition', Iterations=3)],
                     **{'$type': 'NINA.Sequencer.Container.ParallelContainer, NINA'})
    source = content(group([parallel]))
    assert SequencePlan(source).projection == (360, False)
    assert SequencePlan(source, {'root/items/0/items/1'}).projection == (180, False)
    smart = group([item('SwitchFilter'), item('TakeExposure', ExposureTime=60)],
                  [item('LoopCondition', Iterations=10)],
                  **{'$type': 'NINA.Sequencer.SequenceItem.Imaging.SmartExposure, NINA'})
    source = content(group([smart]))
    assert SequencePlan(source).projection == (600, True)
    assert SequencePlan(source, {'root/items/0/items/0'}).projection == (600, False)


def test_duplicate_names_and_shared_references_have_independent_choices():
    exposure = item('TakeExposure', ExposureTime=60, **{'$id': 'shared'})
    source = content(group([group([exposure], Name='Same'), group([{'$ref': 'shared'}], Name='Same')]))
    plan = SequencePlan(source, {'root/items/0/items/0'})
    assert plan.projection == (60, False)
    assert not plan.state(plan.nodes['root/items/0/items/0'])
    assert plan.state(plan.nodes['root/items/1/items/0'])


def test_choice_persistence_and_sequence_isolation():
    first, second = sequence_key(sample()), sequence_key(content(group()))
    save_choices(first, {'root/items/1'})
    assert load_choices(first) == {'root/items/1'}
    assert load_choices(second) == set()
    save_choices(first, set())
    assert load_choices(first) == set()


def test_camera_ramps_use_minutes_and_disabling_removes_allowances():
    source = content(group([item('CoolCamera', Duration=10, Temperature=-10),
                            item('WarmCamera', Duration=10)]))
    plan = SequencePlan(source)
    assert plan.projection == (1200, False)
    assert plan.timing(plan.nodes['root/items/0']) == '≈ 10 min'
    assert plan.timing(plan.root) == '≈ 20 min'
    assert 'Target: -10°C' in plan.rows[0]['Note']
    assert 'actual time depends' in plan.rows[0]['Note']
    plan = SequencePlan(source, {'root/items/0'})
    assert plan.projection == (600, False)
    assert plan.timing(plan.nodes['root/items/0']) == '0 s'
    plan = SequencePlan(source, {'root'})
    assert plan.projection == (0, False)
    assert plan.timing(plan.root) == '0 s'


def test_immediate_and_expression_camera_ramps_remain_variable():
    for duration in (0, None, {'Definition': 'camera.duration'}):
        step = item('CoolCamera', Duration=duration)
        if isinstance(duration, dict):
            step['DurationExpression'] = duration
        plan = SequencePlan(content(group([step])))
        assert plan.timing(plan.root) == 'Variable'
        assert plan.projection == (0, True)


def test_camera_ramp_allowance_inside_parallel_and_with_unknown_overhead():
    source = content(group([item('CoolCamera', Duration=10), item('TakeExposure', ExposureTime=900)],
                           **{'$type': 'NINA.Sequencer.Container.ParallelContainer, NINA'}))
    plan = SequencePlan(source)
    assert plan.projection == (900, False)
    assert plan.timing(plan.root) == '≈ 15 min'
    source = content(group([item('CoolCamera', Duration=10), item('RunAutofocus')]))
    plan = SequencePlan(source)
    assert plan.projection == (600, True)
    assert plan.timing(plan.root) == '≈ 10 min + variable'


def test_bad_saved_choices_are_not_silently_discarded():
    sequence_view.SETTINGS_DIR.mkdir()
    (sequence_view.SETTINGS_DIR / 'bad.json').write_text('{broken')
    with pytest.raises(ValueError):
        load_choices('bad')


PAGE = str(Path(__file__).resolve().parents[1] / 'pages' / '3_Sequence_analyser.py')


def test_page_hierarchy_disable_inheritance_reenable_and_reload():
    source = sample()
    with patch('streamlit.file_uploader', return_value=BytesIO(source)):
        app = AppTest.from_file(PAGE).run()
        assert not app.exception
        assert any('Deep sky OSC 1' in exp.label for exp in app.expander)
        assert any('Deep sky OSC 2' in exp.label and not exp.proto.expanded for exp in app.expander)
        next(c for c in app.checkbox if c.label == 'Disable Deep sky OSC 2').check().run()
        assert not app.exception
        assert next(m for m in app.metric if m.label == 'Expected sequence time').value == '00:01 variable'
        assert any(c.disabled and c.value for c in app.checkbox if c.label == 'Disabled by parent')
        assert any('Deep sky OSC 2' in exp.label and 'Disabled' in exp.label for exp in app.expander)
        reloaded = AppTest.from_file(PAGE).run()
        assert not reloaded.exception
        assert next(c for c in reloaded.checkbox if c.label == 'Disable Deep sky OSC 2').value
        next(c for c in app.checkbox if c.label == 'Disable Deep sky OSC 2').uncheck().run()
        assert not app.exception
        assert next(m for m in app.metric if m.label == 'Expected sequence time').value == '00:03 variable'


def test_saving_failure_keeps_disabled_branch_excluded_and_reports_error():
    with patch('streamlit.file_uploader', return_value=BytesIO(sample())):
        app = AppTest.from_file(PAGE).run()
        with patch('sequence_view.save_choices', side_effect=OSError('disk unavailable')):
            next(c for c in app.checkbox if c.label == 'Disable Deep sky OSC 2').check().run()
        assert not app.exception
        assert 'could not be saved' in app.error[0].value
        assert next(m for m in app.metric if m.label == 'Expected sequence time').value == '00:01 variable'


def test_sections_expose_actual_conditions_items_and_triggers():
    source = content(group([item('TakeExposure', ExposureTime=30)],
                           [item('LoopCondition', Iterations=4)]))
    plan = SequencePlan(source)
    sections = plan.sections(plan.root)
    assert list(sections) == ['Conditions', 'Items', 'Triggers']
    assert [len(children) for children in sections.values()] == [1, 1, 0]
    condition = sections['Conditions'][0]
    assert condition.role == 'Condition'
    assert readable_title(condition) == 'Repeat 4 times'
    assert plan.timing(condition) == '0 s'
    assert plan.projection == (120, False)
    assert len(plan.rows) == 1
    plan = SequencePlan(source, {condition.key})
    assert plan.projection == (30, False)
    assert plan.timing(plan.root) == '30 s'


def test_disabling_smart_exposure_condition_removes_repeat_count():
    smart = group([item('TakeExposure', ExposureTime=30)],
                  [item('LoopCondition', Iterations=10)], Iterations=10,
                  **{'$type': 'NINA.Sequencer.SequenceItem.Imaging.SmartExposure, NINA'})
    source = content(smart)
    assert SequencePlan(source).projection == (300, False)
    assert SequencePlan(source, {'root/conditions/0'}).projection == (30, False)


def test_instruction_details_hide_metadata_and_explain_settings():
    step = item('TakeExposure', ExposureTime=120, ImageType='LIGHT',
                Gain=-1, Offset=-1, Binning={'X': 1, 'Y': 2},
                **{'$id': 'capture', 'Parent': {'$ref': 'root'}, 'IsExpanded': True,
                   'ExposureCount': 17, 'Attempts': 1, 'ErrorBehavior': 0})
    plan = SequencePlan(content(group([step], **{'$id': 'root'})))
    details = dict(instruction_details(plan.nodes['root/items/0']))
    assert details == {'Exposure time': '120 s', 'Frame type': 'LIGHT', 'Gain': 'Camera default',
                       'Offset': 'Camera default', 'Binning': '1 × 2'}


def test_nondefault_failures_and_filter_names_are_readable():
    step = item('SwitchFilter', Filter={'_name': 'Broadband', '_position': 0},
                Attempts=3, ErrorBehavior=2)
    plan = SequencePlan(content(group([step])))
    assert dict(instruction_details(plan.nodes['root/items/0'])) == {
        'Filter': 'Broadband', 'Maximum attempts': '3', 'On failure': 'Abort the sequence'}


def test_page_simplified_sections_full_message_and_no_json_metadata():
    message = 'Initialisation Checks\r\n\r\nConfirm that:\r\n- Targets have been identified.'
    source = content(group([item('MessageBox', Text=message)],
                           [item('LoopCondition', Iterations=4)], Name='Start',
                           **{'$id': 'root'}))
    with patch('streamlit.file_uploader', return_value=BytesIO(source)):
        app = AppTest.from_file(PAGE).run()
    assert not app.exception
    labels = [exp.label.split(': [')[0] for exp in app.expander]
    assert 'Conditions (1)' in labels and 'Items (1)' in labels
    assert app.sidebar.checkbox(key='sequence_hide_empty_containers').value
    assert not any(label in {'Conditions (0)', 'Items (0)', 'Triggers (0)'} for label in labels)
    assert any('Message: Initialisation Checks' in label for label in labels)
    assert any('Repeat 4 times' in label for label in labels)
    assert any(t.value == message.replace('\r\n', '\n') for t in app.text)
    visible_text = '\n'.join(labels + [t.value for t in app.text] + [c.value for c in app.caption])
    assert all(field not in visible_text for field in ('$id', '$type', '$values', 'IsExpanded', 'ErrorBehavior'))


def test_hide_empty_containers_toggle_preserves_nonempty_sections_and_totals():
    source = content(group([group([], Name='Empty group'), item('TakeExposure', ExposureTime=30)]))
    with patch('streamlit.file_uploader', return_value=BytesIO(source)):
        app = AppTest.from_file(PAGE).run()
        assert not app.exception
        assert app.sidebar.checkbox(key='sequence_hide_empty_containers').value
        assert 'Items (2)' in [exp.label.split(': [')[0] for exp in app.expander]
        assert not any(exp.label.split(': [')[0] in {'Conditions (0)', 'Items (0)', 'Triggers (0)'} for exp in app.expander)
        initial_time = next(metric.value for metric in app.metric if metric.label == 'Expected sequence time')
        app.sidebar.checkbox(key='sequence_hide_empty_containers').uncheck().run()
        assert not app.exception
        labels = [exp.label.split(': [')[0] for exp in app.expander]
        assert all(label in labels for label in ('Conditions (0)', 'Items (0)', 'Triggers (0)', 'Items (2)'))
        assert next(metric.value for metric in app.metric if metric.label == 'Expected sequence time') == initial_time
        app.sidebar.checkbox(key='sequence_hide_empty_containers').check().run()
        assert not app.exception
        assert not any(exp.label.split(': [')[0] in {'Conditions (0)', 'Items (0)', 'Triggers (0)'} for exp in app.expander)


def test_section_times_roll_up_nested_loops_and_respect_disables():
    source = content(group([group([item('TakeExposure', ExposureTime=30), item('WaitForTimeSpan', Time=10)],
                                 [item('LoopCondition', Iterations=3)], Name='Nested'),
                            item('TakeExposure', ExposureTime=60)]))
    plan = SequencePlan(source)
    assert plan.timing(plan.root) == '3 min'
    assert plan.section_timing(plan.root, 'Items') == '3 min'
    nested = plan.nodes['root/items/0']
    assert plan.timing(nested) == plan.section_timing(nested, 'Items') == '2 min'
    assert plan.section_timing(nested, 'Conditions') == '0 s'
    assert plan.section_timing(nested, 'Triggers') == '0 s'
    disabled = SequencePlan(source, {'root/items/0/items/0'})
    assert disabled.timing(disabled.root) == '1 min 30 s'
    assert disabled.section_timing(disabled.root, 'Items') == '1 min 30 s'


def test_trigger_action_times_are_per_activation_and_not_added_as_scheduled_work():
    trigger = dict(item('CustomTrigger'), TriggerRunner=group([item('WaitForTimeSpan', Time=10)]))
    plan = SequencePlan(content(group([item('TakeExposure', ExposureTime=60)], triggers=[trigger])))
    assert plan.timing(plan.root) == '≥ 1 min'
    assert plan.section_timing(plan.root, 'Items') == '1 min'
    assert plan.section_timing(plan.root, 'Triggers') == '≥ 10 s per activation each'
    assert plan.timing(plan.nodes['root/triggers/0']) == '≥ 10 s per activation'
    assert plan.timing(plan.nodes['root/triggers/0/runner']) == '10 s per activation'


def test_every_expander_has_a_time_including_empty_sections():
    source = content(group([item('TakeExposure', ExposureTime=30)], [item('LoopCondition', Iterations=2)]))
    with patch('streamlit.file_uploader', return_value=BytesIO(source)):
        app = AppTest.from_file(PAGE).run()
        app.sidebar.checkbox(key='sequence_hide_empty_containers').uncheck().run()
    assert not app.exception
    assert all(': [' in exp.label and '] Time: ' in exp.label for exp in app.expander
               if exp.label != 'Capture summary')
    assert any(exp.label == 'Items (1): [Enabled] Time: 00:01' for exp in app.expander)
    assert any(exp.label == 'Conditions (1): [Enabled] Time: 00:00' for exp in app.expander)
    assert any(exp.label == 'Triggers (0): [Enabled] Time: 00:00' for exp in app.expander)
