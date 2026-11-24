"""Maintain one selected target and invalidate its previous chart interval."""


def set_target_selection(selected):
    """Clear timelines and reports when the selected target changes or is cleared."""
    import streamlit as st
    previous = st.session_state.get('selected_target')
    if previous is not None and previous != selected:
        st.session_state['chart_interval_revision'] = st.session_state.get('chart_interval_revision', 0) + 1
        st.session_state.pop('imaging_report_markdown', None)
        st.session_state.pop('imaging_report_signature', None)
    st.session_state['selected_target'] = selected


def clear_target_selection():
    """Clear the visible table checkboxes from the chart's Clear objects action."""
    import streamlit as st
    set_target_selection(None)
    table_key = st.session_state.get('active_target_table_key')
    if table_key:
        st.session_state[table_key] = {'selection': {'rows': [], 'columns': [], 'cells': []}}


def update_target_selection(table_key, names):
    """Reconcile a checkbox event before Streamlit renders the table again."""
    import streamlit as st
    rows = st.session_state[table_key].get('selection', {}).get('rows', [])
    valid_rows = [row for row in rows if type(row) is int and 0 <= row < len(names)]
    selected = names[valid_rows[0]] if valid_rows else None
    set_target_selection(selected)
    accepted_rows = [valid_rows[0]] if valid_rows else []
    if rows != accepted_rows:
        st.session_state[table_key] = {'selection': {'rows': accepted_rows, 'columns': [], 'cells': []}}
