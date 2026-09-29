"""The automatic table summary an input file becomes: exact stats over the whole file."""

from datetime import date

from app.modules.datasets.domain import TableSummary


def test_summary_reports_type_distinct_count_empty_columns_and_samples() -> None:
    summary = TableSummary("gl.xlsx", ["ACCT", "AMT", "DT", "EMPTY"], sample_rows=2, max_distinct=100, examples=2)
    rows = [
        {"ACCT": "A1", "AMT": 1, "DT": date(2026, 4, 1), "EMPTY": None},
        {"ACCT": "A2", "AMT": 2.5, "DT": date(2026, 4, 2), "EMPTY": ""},
        {"ACCT": "A3", "AMT": 3, "DT": date(2026, 4, 3), "EMPTY": None},
    ]
    for row in rows:
        summary.add(row)
    text = summary.render()
    assert "ROWS: 3" in text
    assert '"column": "AMT", "type": "DOUBLE", "distinct_count": 3, "all_null": false' in text
    assert '"column": "EMPTY", "type": "EMPTY", "distinct_count": 0, "all_null": true' in text
    assert '"column": "ACCT", "type": "VARCHAR", "distinct_count": 3, "all_null": false}' in text  # no examples: 3 > 2
    assert "A3" not in text  # only the first 2 rows are samples, and 3 distinct values exceed the 2 examples
