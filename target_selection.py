"""Keep up to two target identities in the order they were selected."""


def ordered_selection(previous, requested):
    """Retain checked targets in click order; ignore additions once two are kept."""
    requested = list(dict.fromkeys(requested))
    retained = [name for name in previous if name in requested][:2]
    return (retained + [name for name in requested if name not in retained])[:2]


def update_target_selection(table_key, names):
    """Reconcile a checkbox event before Streamlit renders the table again."""
    import streamlit as st
    rows = st.session_state[table_key].get('selection', {}).get('rows', [])
    requested = [names[row] for row in rows if isinstance(row, int) and 0 <= row < len(names)]
    selected = ordered_selection(st.session_state.get('selected_targets', []), requested)
    st.session_state['selected_targets'] = selected
    accepted_rows = [names.index(name) for name in selected]
    if set(rows) != set(accepted_rows):
        # A third checkbox must return to unchecked, not merely be ignored by the plot.
        st.session_state[table_key] = {'selection': {'rows': accepted_rows, 'columns': [], 'cells': []}}
