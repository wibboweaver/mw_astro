from datetime import datetime
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from streamlit.testing.v1 import AppTest

import sequence_view
from sequence_view import SequencePlan
from sequence_insights import (capture_summary, capture_totals, clock_duration, format_timing,
                               heading, projected_finish)
from test_sequence_analyser import group, item
from test_sequence_view import content


def smart(exposure=120, count=30, frame='LIGHT'):
    return group([item('SwitchFilter', Filter=None), item('TakeExposure', ExposureTime=exposure, ImageType=frame)],
                 [item('LoopCondition', Iterations=count)],
                 **{'$type': 'NINA.Sequencer.SequenceItem.Imaging.SmartExposure, NINA'})


def capture_plan():
    target = group([item('SwitchFilter', Filter={'_name': 'Broadband'}), smart()],
                   Name='Deep sky OSC 1', Target={'TargetName': 'M 31'})
    trained = group([group([item('TakeExposure', ExposureTime=0, ImageType='FLAT')],
                           [item('LoopCondition', Iterations=30)])],
                    **{'$type': 'NINA.Sequencer.SequenceItem.FlatDevice.TrainedFlatExposure, NINA'})
    dark_flat = group([group([item('TakeExposure', ExposureTime=0, ImageType='DARK')],
                             [item('LoopCondition', Iterations=30)])],
                      **{'$type': 'NINA.Sequencer.SequenceItem.FlatDevice.TrainedDarkFlatExposure, NINA'})
    return content(group([target, trained, dark_flat, smart(frame='DARK')]))


@pytest.mark.parametrize('raw,expected', [
    ('≈ 1 h 10 min + variable', '01:10 variable'),
    ('≥ 1 h 10 min', '01:10 variable'),
    ('1 h 10 min', '01:10'), ('≈ 10 min', '00:10 estimated'),
    ('30 s', '00:00:30'), ('0 s', '00:00'), ('Variable', '--:-- variable'),
    ('≥ 10 s per activation', '00:00:10 variable per activation'),
    ('10 s per pass', '00:00:10 per pass'), ('25 h 5 min', '25:05'),
])
def test_consistent_time_format(raw, expected):
    assert format_timing(raw) == expected


def test_requested_heading_format():
    assert heading('Targets', True, '≈ 1 h 10 min + variable') == 'Targets: [Enabled] Time: 01:10 variable'
    assert heading('End', True, '≈ 1 h 10 min + variable') == 'End: [Enabled] Time: 01:10 variable'
    assert heading('Targets', False, '0 s') == 'Targets: [Disabled] Time: 00:00'
    assert clock_duration(0.25) == '00:00:01'


def test_capture_summary_counts_actual_exposures_without_composite_double_counting():
    captures = capture_summary(SequencePlan(capture_plan()))
    assert len(captures) == 4
    light = next(capture for capture in captures if capture.frame_type == 'LIGHT')
    assert (light.target, light.filter, light.frames, light.exposure, light.seconds) == ('M 31', 'Broadband', 30, 120, 3600)
    assert capture_totals(captures) == '01:00'
    assert capture_totals(captures, lights=False) == '01:00 variable'
    for frame in ('FLAT', 'DARK FLAT'):
        capture = next(capture for capture in captures if capture.frame_type == frame)
        assert capture.frames == 30 and capture.exposure is None and capture.seconds is None
        assert capture.row()['Exposure time'] == '--:-- variable'


def test_capture_summary_excludes_disabled_targets_and_individual_exposures():
    source = capture_plan()
    plan = SequencePlan(source, {'root/items/0'})
    assert all(capture.frame_type != 'LIGHT' for capture in capture_summary(plan))
    assert capture_totals(capture_summary(plan)) == '00:00'
    plan = SequencePlan(source, {'root'})
    assert capture_summary(plan) == []


def test_summary_aggregates_matching_exposures_and_fixed_nested_loops():
    source = content(group([item('TakeExposure', ExposureTime=10), item('TakeExposure', ExposureTime=10)],
                           [item('LoopCondition', Iterations=3)]))
    captures = capture_summary(SequencePlan(source))
    assert len(captures) == 1 and captures[0].frames == 6 and captures[0].seconds == 60


def test_variable_loop_and_runtime_exposure_do_not_produce_false_totals():
    source = content(group([item('TakeExposure', ExposureTime=10,
                                 ExposureTimeExpression={'Definition': 'camera.exposure'})],
                           [item('TimeCondition', Hours=6)]))
    capture = capture_summary(SequencePlan(source))[0]
    assert capture.frames is None and capture.exposure is None and capture.seconds is None


def test_trigger_captures_are_conditional_and_excluded_from_scheduled_totals():
    trigger = dict(item('CustomTrigger'), TriggerRunner=group([item('TakeExposure', ExposureTime=10)]))
    captures = capture_summary(SequencePlan(content(group(triggers=[trigger]))))
    assert len(captures) == 1 and captures[0].conditional and captures[0].seconds is None
    assert capture_totals(captures) == '00:00'
    assert 'Conditional' in captures[0].row()['Note']


def test_finish_projection_handles_midnight_and_clock_changes():
    plan = SequencePlan(content(group([item('WaitForTimeSpan', Time=7200)])))
    start = datetime(2026, 11, 21, 23, 0, tzinfo=ZoneInfo('Europe/London'))
    end, variable = projected_finish(plan, start)
    assert end == datetime(2026, 11, 22, 1, 0, tzinfo=start.tzinfo) and not variable
    start = datetime(2026, 10, 25, 0, 30, tzinfo=start.tzinfo)
    end, _ = projected_finish(plan, start)
    assert end.hour == 1 and end.minute == 30 and end.tzname() == 'GMT'


def test_finish_projection_reports_unestimated_work_and_disabled_zero_duration():
    start = datetime(2026, 11, 21, 20, 0, tzinfo=ZoneInfo('Europe/London'))
    source = content(group([item('RunAutofocus')]))
    assert projected_finish(SequencePlan(source), start) == (None, True)
    assert projected_finish(SequencePlan(source, {'root'}), start) == (start, False)


PAGE = str(Path(__file__).resolve().parents[1] / 'pages' / '3_Sequence_analyser.py')


def test_page_capture_finish_controls_and_compact_heading(tmp_path, monkeypatch):
    monkeypatch.setattr(sequence_view, 'SETTINGS_DIR', tmp_path)
    source = capture_plan()
    with patch('streamlit.file_uploader', return_value=BytesIO(source)):
        app = AppTest.from_file(PAGE).run()
        assert not app.exception
        assert any(exp.label == 'Capture summary' and not exp.proto.expanded for exp in app.expander)
        assert not any(exp.label.startswith('Check these') for exp in app.expander)
        assert any('Deep sky OSC 1: [Enabled] Time: 01:00 variable' == exp.label for exp in app.expander)
        assert len(app.dataframe[0].value) == 4
        assert app.sidebar.date_input(key='sequence_session_date')
        assert app.sidebar.time_input(key='sequence_session_start')
        next(box for box in app.checkbox if box.label == 'Disable Deep sky OSC 1').check().run()
        assert not app.exception
        assert 'LIGHT' not in set(app.dataframe[0].value['Frame type'])
        assert any('Deep sky OSC 1: [Disabled] Time: 00:00' == exp.label for exp in app.expander)
