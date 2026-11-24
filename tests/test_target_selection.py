from target_selection import ordered_selection
import streamlit as st
from target_selection import clear_target_selection, set_target_selection, update_target_selection


def test_click_order_survives_table_row_order_and_primary_removal():
    assert ordered_selection(['A'], ['B', 'A']) == ['A', 'B']
    assert ordered_selection(['A', 'B'], ['B']) == ['B']
    assert ordered_selection(['B'], ['A', 'B']) == ['B', 'A']


def test_third_selection_is_ignored_and_deselection_frees_a_slot():
    assert ordered_selection(['A', 'B'], ['C', 'B', 'A']) == ['A', 'B']
    assert ordered_selection(['A', 'B'], ['B', 'C']) == ['B', 'C']
    assert ordered_selection(['A', 'B'], []) == []


def test_removing_either_target_invalidates_timelines_but_adding_does_not(monkeypatch):
    state = {'selected_targets': ['A'], 'chart_interval_revision': 7,
             'imaging_report_markdown': 'old report', 'imaging_report_signature': 'old signature'}
    monkeypatch.setattr(st, 'session_state', state)
    set_target_selection(['A', 'B'])
    assert state['chart_interval_revision'] == 7
    set_target_selection(['A'])
    assert state['chart_interval_revision'] == 8
    assert 'imaging_report_markdown' not in state
    assert 'imaging_report_signature' not in state
    set_target_selection(['A', 'B'])
    set_target_selection(['B'])
    assert state['chart_interval_revision'] == 9


def test_clear_objects_clears_table_selection_and_saved_report(monkeypatch):
    state = {'selected_targets': ['A', 'B'], 'selected_target': 'A',
             'active_target_table_key': 'target_table:test',
             'target_table:test': {'selection': {'rows': [1, 0]}},
             'imaging_report_markdown': 'old report'}
    monkeypatch.setattr(st, 'session_state', state)
    clear_target_selection()
    assert state['selected_targets'] == []
    assert state['target_table:test']['selection']['rows'] == []
    assert state['chart_interval_revision'] == 1
    assert 'selected_target' not in state and 'imaging_report_markdown' not in state


def test_ignored_third_target_does_not_clear_timelines(monkeypatch):
    state = {'selected_targets': ['A', 'B'], 'target_table:test': {'selection': {'rows': [0, 1, 2]}}}
    monkeypatch.setattr(st, 'session_state', state)
    update_target_selection('target_table:test', ['A', 'B', 'C'])
    assert state['selected_targets'] == ['A', 'B']
    assert state['target_table:test']['selection']['rows'] == [0, 1]
    assert 'chart_interval_revision' not in state
