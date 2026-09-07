import json
from pathlib import Path

import pytest
from docx import Document

from iris_v2.report_substances_by_component import (
    ReportSubstancesByComponentError,
    load_substances_by_component_rows,
    render_substances_by_component_table,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def equipment(
    equipment_id: int,
    substance_id: int,
    component: str,
    equipment_type: int,
    count: int | None,
) -> dict:
    return {
        "id": equipment_id,
        "substance_id": substance_id,
        "hazard_component": component,
        "equipment_type": equipment_type,
        "equipment_count": count,
    }


def test_substances_are_aggregated_by_component_without_characteristics(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "substances.json",
        [
            {"id": 1, "name": "Нефть", "kind": 9},
            {"id": 2, "name": "Попутный нефтяной газ", "kind": 2},
        ],
    )
    write_json(
        tmp_path / "equipments.json",
        [
            equipment(1, 1, "Участок подготовки", 9, None),
            equipment(2, 1, "Участок подготовки", 1, 2),
            equipment(3, 2, "Сепарационная площадка", 1, 3),
        ],
    )
    write_json(
        tmp_path / "amount_results.json",
        {
            "results": [
                {"equipment_id": 1, "amount_t": 5.0},
                {"equipment_id": 2, "amount_t": 10.0},
                {"equipment_id": 3, "amount_t": 1.25},
            ]
        },
    )

    assert load_substances_by_component_rows(tmp_path) == (
        {
            "component": "Участок подготовки",
            "substance": "Нефть",
            "amount": "25,000",
        },
        {
            "component": "Сепарационная площадка",
            "substance": "Попутный нефтяной газ",
            "amount": "3,750",
        },
    )


def test_extra_amount_result_is_rejected(tmp_path: Path) -> None:
    write_json(tmp_path / "substances.json", [{"id": 1, "name": "Нефть"}])
    write_json(
        tmp_path / "equipments.json",
        [equipment(1, 1, "Участок", 9, None)],
    )
    write_json(
        tmp_path / "amount_results.json",
        {
            "results": [
                {"equipment_id": 1, "amount_t": 5.0},
                {"equipment_id": 2, "amount_t": 1.0},
            ]
        },
    )

    with pytest.raises(ReportSubstancesByComponentError, match="отсутствующее"):
        load_substances_by_component_rows(tmp_path)


def test_table_replaces_marker_and_repeats_header() -> None:
    document = Document()
    document.add_paragraph("{{SUBSTANCES_BY_COMPONENT_TABLE}}")
    rows = (
        {
            "component": "Участок подготовки",
            "substance": "Нефть",
            "amount": "25,000",
        },
    )

    assert render_substances_by_component_table(document, rows)
    assert "SUBSTANCES_BY_COMPONENT" not in "\n".join(
        paragraph.text for paragraph in document.paragraphs
    )
    assert [cell.text for cell in document.tables[0].rows[1].cells] == [
        "Участок подготовки",
        "Нефть",
        "25,000",
    ]
    properties = document.tables[0].rows[0]._tr.get_or_add_trPr()
    assert properties.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblHeader"
    ) is not None
