import streamlit as st
from target_selection import clear_target_selection, set_target_selection, update_target_selection


def test_target_changes_and_deselection_reset_timelines_and_reports(monkeypatch):
    state = {}
    monkeypatch.setattr(st, 'session_state', state)
    set_target_selection('A')
    set_target_selection('A')
    assert 'chart_interval_revision' not in state
    state.update(imaging_report_markdown='old report', imaging_report_signature='old signature')
    set_target_selection('B')
    assert state['selected_target'] == 'B'
    assert state['chart_interval_revision'] == 1
    assert 'imaging_report_markdown' not in state and 'imaging_report_signature' not in state
    set_target_selection(None)
    assert state['selected_target'] is None
    assert state['chart_interval_revision'] == 2
    set_target_selection('A')
    assert state['chart_interval_revision'] == 2


def test_clear_objects_clears_table_selection_and_saved_report(monkeypatch):
    state = {'selected_target': 'A', 'active_target_table_key': 'target_table:test',
             'target_table:test': {'selection': {'rows': [0]}}, 'imaging_report_markdown': 'old report'}
    monkeypatch.setattr(st, 'session_state', state)
    clear_target_selection()
    assert state['selected_target'] is None
    assert state['target_table:test']['selection']['rows'] == []
    assert state['chart_interval_revision'] == 1
    assert 'imaging_report_markdown' not in state


def test_selection_callback_replaces_the_selected_object(monkeypatch):
    state = {'selected_target': 'A', 'target_table:test': {'selection': {'rows': [1]}}}
    monkeypatch.setattr(st, 'session_state', state)
    update_target_selection('target_table:test', ['A', 'B'])
    assert state['selected_target'] == 'B'
    assert state['chart_interval_revision'] == 1


def test_invalid_selection_rows_are_discarded(monkeypatch):
    state = {'selected_target': 'A', 'target_table:test': {'selection': {'rows': [-1, True, 'bad', 2]}}}
    monkeypatch.setattr(st, 'session_state', state)
    update_target_selection('target_table:test', ['A', 'B'])
    assert state['selected_target'] is None
    assert state['target_table:test']['selection']['rows'] == []
