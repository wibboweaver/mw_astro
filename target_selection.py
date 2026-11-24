"""Keep up to two target identities in the order they were selected."""


def ordered_selection(previous, requested):
    """Retain checked targets in click order; ignore additions once two are kept."""
    requested = list(dict.fromkeys(requested))
    retained = [name for name in previous if name in requested][:2]
    return (retained + [name for name in requested if name not in retained])[:2]


def set_target_selection(selected):
    """Invalidate every timeline and report whenever a selected object is removed."""
    import streamlit as st
    if set(st.session_state.get('selected_targets', [])) - set(selected):
        st.session_state['chart_interval_revision'] = st.session_state.get('chart_interval_revision', 0) + 1
        st.session_state.pop('imaging_report_markdown', None)
        st.session_state.pop('imaging_report_signature', None)
    st.session_state['selected_targets'] = selected


def clear_target_selection():
    """Clear the visible table checkboxes from the chart's Clear objects action."""
    import streamlit as st
    set_target_selection([])
    st.session_state.pop('selected_target', None)
    table_key = st.session_state.get('active_target_table_key')
    if table_key:
        st.session_state[table_key] = {'selection': {'rows': [], 'columns': [], 'cells': []}}


def update_target_selection(table_key, names):
    """Reconcile a checkbox event before Streamlit renders the table again."""
    import streamlit as st
    rows = st.session_state[table_key].get('selection', {}).get('rows', [])
    requested = [names[row] for row in rows if isinstance(row, int) and 0 <= row < len(names)]
    selected = ordered_selection(st.session_state.get('selected_targets', []), requested)
    set_target_selection(selected)
    accepted_rows = [names.index(name) for name in selected]
    if set(rows) != set(accepted_rows):
        # A third checkbox must return to unchecked, not merely be ignored by the plot.
        st.session_state[table_key] = {'selection': {'rows': accepted_rows, 'columns': [], 'cells': []}}
