import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest
from docx import Document

from iris_v2.project_common import ProjectCommonService, new_project_common
from iris_v2.report_generation import ReportGenerationError, ReportGenerationService
from iris_v2.service import CreateProjectData, ProjectService


def make_project(tmp_path: Path) -> Path:
    project = tmp_path / "project"
    ProjectService().create(
        project,
        CreateProjectData(
            name="Проект ДПБ",
            code="DPB-001",
            organization_name="АО Короткое",
            opo_name="Площадка нефти",
            opo_registration_number="А00-00001-0001",
            organization_snapshot={
                "organization": {
                    "full_name": "Акционерное общество Короткое",
                    "short_name": "АО Короткое",
                    "ids": {"inn": "1234567890"},
                    "contacts": {"phone": "+7 000 000-00-00"},
                },
                "permits": {"license_number": "Лицензия № 1"},
            },
            opo_snapshot={
                "site_id": "opo_0001",
                "name": "Площадка нефти",
                "reg_number": "А00-00001-0001",
                "object_id": "III",
                "sanitary_protection_zone_m": 0,
                "personnel": {
                    "employees_count": 15,
                    "employees_other_opo_count": 4,
                },
            },
        ),
    )
    common = new_project_common("Проект ДПБ", "DPB-001")
    common["dpb_code"] = "ДПБ-01"
    common["executor"]["name"] = "ООО Разработчик"
    ProjectCommonService().save(project, common)
    return project


def install_template(project: Path, unknown_marker: bool = False) -> Path:
    path = project / "input" / "templates" / "selected" / "template_report.docx"
    document = Document()
    paragraph = document.add_paragraph("Проект: ")
    paragraph.add_run("{{ PRO")
    paragraph.add_run("JECT_NAME }}")
    document.add_paragraph("Шифр: {{ DPB_CODE }}")
    document.add_paragraph("Дата: {{ generated_at }}")
    document.add_paragraph("СЗЗ: {{ SITE_SANITARY_PROTECTION_ZONE_M }}")
    document.add_paragraph("{{SUBSTANCES_SECTION}}")
    table = document.add_table(rows=1, cols=1)
    table.cell(0, 0).text = "Организация: {{ FULL_NAME }}"
    document.sections[0].header.paragraphs[0].text = (
        "{{ SHORT_NAME }} — {{ SITE_NAME }}"
    )
    if unknown_marker:
        document.add_paragraph("{{ UNKNOWN_FIELD }}")
    document.save(path)
    config = {
        "format_version": 1,
        "template_profile": "test",
        "documents": [
            {
                "name": path.name,
                "path": "input/templates/selected/template_report.docx",
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        ],
    }
    (project / "report_config.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )
    return path


def write_substances(project: Path) -> None:
    data = [
        {
            "id": 1,
            "name": "Нефть",
            "kind": 0,
            "formula": "Смесь углеводородов",
            "composition": {
                "components": [
                    {"name": "Углеводороды", "mass_fraction": 0.98},
                    {"name": "Вода", "mass_fraction": 0.02},
                ]
            },
            "notes": "Товарная нефть",
            "physical": {
                "density_liquid_kg_per_m3": 850,
                "boiling_point_C": None,
            },
            "explosion": {"flash_point_C": -35},
            "toxicity": {"hazard_class": 3},
            "reactivity": "Стабильна при нормальных условиях",
            "odor": "Характерный",
            "corrosiveness": "",
            "precautions": "Исключить источники зажигания",
            "impact": "Опасна при попадании в окружающую среду",
            "protection": "Спецодежда и средства защиты органов дыхания",
            "neutralization_methods": "Сбор механическим способом",
            "first_aid": "Вывести пострадавшего на свежий воздух",
        }
    ]
    (project / "substances.json").write_text(
        json.dumps(data, ensure_ascii=False), encoding="utf-8"
    )


def all_text(document: Document) -> str:
    values = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                values.extend(paragraph.text for paragraph in cell.paragraphs)
    for section in document.sections:
        values.extend(paragraph.text for paragraph in section.header.paragraphs)
    return "\n".join(values)


def test_scalar_markers_are_filled_and_blocks_are_preserved(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    install_template(project)
    write_substances(project)

    result = ReportGenerationService().generate(
        project, generated_at=datetime(2026, 9, 6, 12, 30)
    )

    text = all_text(Document(result.output_path))
    assert "Проект: Проект ДПБ" in text
    assert "Шифр: ДПБ-01" in text
    assert "Дата: 06.09.2026 12:30" in text
    assert "СЗЗ: отсутствует" in text
    assert "Организация: Акционерное общество Короткое" in text
    assert "АО Короткое — Площадка нефти" in text
    assert "{{SUBSTANCES_SECTION}}" not in text
    assert "Параметр" in text
    assert "0 — Легковоспламеняющаяся жидкость (ЛВЖ)" in text
    assert "Плотность жидкости" in text
    assert "850 кг/м³" in text
    assert "Температура кипения" not in text
    assert all(
        row._tr.get_or_add_trPr().find(
            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}cantSplit"
        ) is not None
        for row in Document(result.output_path).tables[0].rows
    )
    assert result.replaced_count == 7
    assert result.filled_sections == ("SUBSTANCES_SECTION",)
    assert result.deferred_markers == ()


def test_unknown_marker_does_not_replace_existing_report(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    install_template(project, unknown_marker=True)
    output = project / "output" / "template_report_out.docx"
    output.write_bytes(b"previous report")

    with pytest.raises(ReportGenerationError, match="UNKNOWN_FIELD"):
        ReportGenerationService().generate(project)

    assert output.read_bytes() == b"previous report"


def test_changed_template_is_rejected(tmp_path: Path) -> None:
    project = make_project(tmp_path)
    template = install_template(project)
    template.write_bytes(template.read_bytes() + b"changed")

    with pytest.raises(ReportGenerationError, match="изменён после выбора"):
        ReportGenerationService().generate(project)


def test_builtin_default_template_contains_only_supported_markers(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    project = make_project(tmp_path)
    write_substances(project)

    result = ReportGenerationService().generate(project)

    assert result.output_path.is_file()
    assert result.replaced_count > 0
    assert result.filled_sections == ("SUBSTANCES_SECTION",)
    assert "SUBSTANCES_SECTION" not in result.deferred_markers
