import json
from pathlib import Path

from docx import Document

from iris_v2.report_key_scenarios import (
    load_key_scenario_description_rows,
    load_key_scenario_rows,
    render_key_scenario_descriptions,
    render_key_scenarios_section,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def row(
    code: str,
    component: str,
    fatalities: int,
    injured: int,
    damage: float,
    frequency: float,
) -> dict:
    return {
        "scenario_code": code,
        "hazard_component": component,
        "equipment_name": f"Оборудование {code}",
        "fatalities_count": fatalities,
        "injured_count": injured,
        "total_damage": damage,
        "scenario_frequency": frequency,
        "scenario_text": f"Описание {code}",
    }


def test_rows_use_key_scenario_selection_and_report_formats(tmp_path: Path) -> None:
    write_json(
        tmp_path / "risk_results.json",
        {
            "results": [
                row("С1", "Участок", 1, 3, 1200.25, 4e-5),
                row("С2", "Участок", 2, 4, 900.0, 2e-5),
                row("С3", "Участок", 0, 1, 500.0, 6e-5),
            ]
        },
    )

    rows = load_key_scenario_rows(tmp_path)

    assert rows == (
        {
            "component": "Участок",
            "scenario_type": "Наиболее опасный",
            "scenario_code": "С2",
            "equipment": "Оборудование С2",
            "fatalities": "2",
            "injured": "4",
            "damage": "900,0",
            "frequency": "2.000E-05",
        },
        {
            "component": "Участок",
            "scenario_type": "Наиболее вероятный",
            "scenario_code": "С3",
            "equipment": "Оборудование С3",
            "fatalities": "0",
            "injured": "1",
            "damage": "500,0",
            "frequency": "6.000E-05",
        },
    )
    assert (tmp_path / "key_scenarios.json").is_file()


def test_section_replaces_marker_with_repeatable_table() -> None:
    document = Document()
    document.add_paragraph("{{TOP_SCENARIOS_BY_COMPONENT_SECTION}}")
    rows = (
        {
            "component": "Участок",
            "scenario_type": "Наиболее опасный",
            "scenario_code": "С1",
            "equipment": "Аппарат",
            "fatalities": "1",
            "injured": "2",
            "damage": "100,0",
            "frequency": "1.000E-05",
        },
    )

    assert render_key_scenarios_section(document, rows)
    assert "TOP_SCENARIOS" not in "\n".join(p.text for p in document.paragraphs)
    assert [cell.text for cell in document.tables[0].rows[1].cells] == [
        "Участок",
        "Наиболее опасный",
        "С1",
        "Аппарат",
        "1",
        "2",
        "100,0",
        "1.000E-05",
    ]
    properties = document.tables[0].rows[0]._tr.get_or_add_trPr()
    assert properties.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblHeader"
    ) is not None


def test_description_rows_use_selected_scenarios_and_full_text(
    tmp_path: Path,
) -> None:
    write_json(
        tmp_path / "risk_results.json",
        {
            "results": [
                row("С1", "Участок", 1, 3, 1200.25, 4e-5),
                row("С2", "Участок", 2, 4, 900.0, 2e-5),
                row("С3", "Участок", 0, 1, 500.0, 6e-5),
            ]
        },
    )

    assert load_key_scenario_description_rows(tmp_path) == (
        {
            "component": "Участок",
            "scenario_type": "Наиболее опасный",
            "scenario_code": "С2",
            "description": "Описание С2",
        },
        {
            "component": "Участок",
            "scenario_type": "Наиболее вероятный",
            "scenario_code": "С3",
            "description": "Описание С3",
        },
    )


def test_description_table_replaces_marker_and_repeats_header() -> None:
    document = Document()
    document.add_paragraph("{{TOP_SCENARIOS_DESC_BY_COMPONENT}}")
    rows = (
        {
            "component": "Участок",
            "scenario_type": "Наиболее опасный",
            "scenario_code": "С1",
            "description": "Разрыв трубопровода → пожар пролива",
        },
    )

    assert render_key_scenario_descriptions(document, rows)
    assert "TOP_SCENARIOS_DESC" not in "\n".join(
        paragraph.text for paragraph in document.paragraphs
    )
    assert [cell.text for cell in document.tables[0].rows[1].cells] == [
        "Участок",
        "Наиболее опасный",
        "С1",
        "Разрыв трубопровода → пожар пролива",
    ]
    properties = document.tables[0].rows[0]._tr.get_or_add_trPr()
    assert properties.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}tblHeader"
    ) is not None
