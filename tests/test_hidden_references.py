"""
test_hidden_references.py — pytest tests for hidden-object reference
detection used by the README/HTML generators.
"""

from tmdl_lens.readme_generator import (
    _build_hidden_reference_map,
    _find_hidden_references,
    _hidden_reference_note,
)
from tmdl_lens.tmdl_parser import Column, Measure, SemanticModel, Table


def _build_test_model() -> SemanticModel:
    """A small model with hidden columns, hidden tables and ambiguous names."""
    sales = Table(
        name="Sales",
        table_type="fact",
        columns=[
            Column(name="Visible", data_type="int64"),
            Column(name="Secret", data_type="int64", is_hidden=True),
        ],
        measures=[
            Measure(name="Visible Measure", dax_expression="SUM('Sales'[Visible])"),
            Measure(
                name="Hidden Measure",
                dax_expression="SUM('Sales'[Visible])",
                is_hidden=True,
            ),
        ],
    )
    helper = Table(
        name="Helper",
        table_type="helper",
        is_hidden=True,
        columns=[Column(name="Key", data_type="int64")],
        measures=[Measure(name="Open Count", dax_expression="COUNTROWS('Helper')")],
    )
    t1 = Table(
        name="T1",
        table_type="dim",
        measures=[Measure(name="Amb", dax_expression="1", is_hidden=True)],
    )
    t2 = Table(
        name="T2",
        table_type="dim",
        measures=[Measure(name="Amb", dax_expression="1", is_hidden=True)],
    )
    return SemanticModel(report_name="Test", tables=[sales, helper, t1, t2])


def _maps(model):
    return _build_hidden_reference_map(model)


def test_build_map_hidden_objects():
    tables, hidden_measures, hidden_columns = _maps(_build_test_model())
    assert hidden_measures["Hidden Measure"] == "Sales"
    assert hidden_measures["Open Count"] == "Helper"      # via hidden table
    assert set(hidden_measures["Amb"]) == {"T1", "T2"}    # ambiguous
    assert hidden_columns[("Sales", "Secret")] is True
    assert hidden_columns[("Helper", "Key")] is True      # via hidden table
    assert ("Sales", "Visible") not in hidden_columns


def test_hidden_column_reference():
    tables, hm, hc = _maps(_build_test_model())
    refs = _find_hidden_references("X = 'Sales'[Secret]", tables, hm, hc)
    assert refs == [("Sales[Secret]", "Sales")]


def test_hidden_table_column_reference():
    tables, hm, hc = _maps(_build_test_model())
    refs = _find_hidden_references("X = 'Helper'[Key]", tables, hm, hc)
    assert refs == [("Helper[Key]", "Helper")]


def test_hidden_measure_reference():
    tables, hm, hc = _maps(_build_test_model())
    refs = _find_hidden_references("X = [Hidden Measure]", tables, hm, hc)
    assert refs == [("[Hidden Measure]", "Sales")]


def test_ambiguous_measure_skipped():
    tables, hm, hc = _maps(_build_test_model())
    refs = _find_hidden_references("X = [Amb]", tables, hm, hc)
    assert refs == []


def test_string_literals_ignored():
    tables, hm, hc = _maps(_build_test_model())
    dax = '"Sales[Secret]" & [Hidden Measure]'
    refs = _find_hidden_references(dax, tables, hm, hc)
    assert refs == [("[Hidden Measure]", "Sales")]


def test_visible_references_not_flagged():
    tables, hm, hc = _maps(_build_test_model())
    dax = "'Sales'[Visible] + [Visible Measure]"
    refs = _find_hidden_references(dax, tables, hm, hc)
    assert refs == []


def test_empty_expression():
    tables, hm, hc = _maps(_build_test_model())
    assert _find_hidden_references("", tables, hm, hc) == []


def test_hidden_reference_note():
    refs = [("Sales[Secret]", "Sales"), ("[Hidden Measure]", "Sales")]
    note = _hidden_reference_note(refs)
    assert note.startswith("⚠ References hidden:")
    assert "`Sales[Secret]`" in note
    assert "`[Hidden Measure]`" in note
    assert _hidden_reference_note([]) == ""
