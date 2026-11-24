from target_selection import ordered_selection


def test_click_order_survives_table_row_order_and_primary_removal():
    assert ordered_selection(['A'], ['B', 'A']) == ['A', 'B']
    assert ordered_selection(['A', 'B'], ['B']) == ['B']
    assert ordered_selection(['B'], ['A', 'B']) == ['B', 'A']


def test_third_selection_is_ignored_and_deselection_frees_a_slot():
    assert ordered_selection(['A', 'B'], ['C', 'B', 'A']) == ['A', 'B']
    assert ordered_selection(['A', 'B'], ['B', 'C']) == ['B', 'C']
    assert ordered_selection(['A', 'B'], []) == []
