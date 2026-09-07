import math
from pathlib import Path
from typing import Any

from docx.document import Document as DocumentType
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from iris_v2.equipment import PIPELINE_TYPES
from iris_v2.report_distribution import (
    ReportDistributionError,
    load_amount_results,
)
from iris_v2.report_equipment import ReportEquipmentError, load_project_equipment
from iris_v2.substances import SubstanceError, SubstanceService


MARKER = "{{SUBSTANCES_BY_COMPONENT_TABLE}}"


class ReportSubstancesByComponentError(Exception):
    pass


def _mass(value: Any, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0
    ):
        raise ReportSubstancesByComponentError(
            f"{label} должно быть числом не меньше нуля"
        )
    return float(value)


def _units(item: dict[str, Any], equipment_id: int) -> int:
    if item.get("equipment_type") in PIPELINE_TYPES:
        return 1
    value = item.get("equipment_count")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 1
        or not float(value).is_integer()
    ):
        raise ReportSubstancesByComponentError(
            f"Оборудование {equipment_id}: equipment_count должно быть "
            "целым числом не меньше 1"
        )
    return int(value)


def load_substances_by_component_rows(
    project_directory: Path | str,
) -> tuple[dict[str, str], ...]:
    project = Path(project_directory)
    try:
        substances = SubstanceService().load_project(project)
        equipment = load_project_equipment(project)
        amounts = load_amount_results(project)
    except (SubstanceError, ReportEquipmentError, ReportDistributionError) as exc:
        raise ReportSubstancesByComponentError(str(exc)) from exc
    if not substances:
        raise ReportSubstancesByComponentError(
            "Вещества проекта не выбраны. Сначала заполните модуль «Вещества»"
        )

    names: dict[int, str] = {}
    for index, item in enumerate(substances, start=1):
        substance_id = item.get("id")
        name = str(item.get("name", "")).strip()
        if (
            isinstance(substance_id, bool)
            or not isinstance(substance_id, int)
            or substance_id <= 0
            or substance_id in names
        ):
            raise ReportSubstancesByComponentError(
                f"substances.json, запись {index}: недопустимый или повторяющийся id"
            )
        if not name:
            raise ReportSubstancesByComponentError(
                f"Вещество {substance_id}: наименование не заполнено"
            )
        names[substance_id] = name

    amount_by_equipment: dict[int, float] = {}
    for index, item in enumerate(amounts, start=1):
        equipment_id = item.get("equipment_id")
        if (
            isinstance(equipment_id, bool)
            or not isinstance(equipment_id, int)
            or equipment_id <= 0
            or equipment_id in amount_by_equipment
        ):
            raise ReportSubstancesByComponentError(
                f"amount_results.json, запись {index}: "
                "недопустимый или повторяющийся equipment_id"
            )
        amount_by_equipment[equipment_id] = _mass(
            item.get("amount_t"),
            f"amount_results.json, оборудование {equipment_id}: amount_t",
        )

    grouped: dict[tuple[str, int], float] = {}
    equipment_ids: set[int] = set()
    for index, item in enumerate(equipment, start=1):
        equipment_id = item.get("id")
        if (
            isinstance(equipment_id, bool)
            or not isinstance(equipment_id, int)
            or equipment_id <= 0
            or equipment_id in equipment_ids
        ):
            raise ReportSubstancesByComponentError(
                f"equipments.json, запись {index}: недопустимый или повторяющийся id"
            )
        equipment_ids.add(equipment_id)
        component = str(item.get("hazard_component", "")).strip()
        if not component:
            raise ReportSubstancesByComponentError(
                f"Оборудование {equipment_id}: составляющая ОПО не заполнена"
            )
        substance_id = item.get("substance_id")
        if (
            isinstance(substance_id, bool)
            or not isinstance(substance_id, int)
            or substance_id not in names
        ):
            raise ReportSubstancesByComponentError(
                f"Оборудование {equipment_id}: substance_id отсутствует "
                "в substances.json"
            )
        if equipment_id not in amount_by_equipment:
            raise ReportSubstancesByComponentError(
                f"В amount_results.json отсутствует оборудование id={equipment_id}"
            )
        key = (component, substance_id)
        grouped[key] = grouped.get(key, 0.0) + (
            amount_by_equipment[equipment_id] * _units(item, equipment_id)
        )

    extra_ids = set(amount_by_equipment) - equipment_ids
    if extra_ids:
        values = ", ".join(str(value) for value in sorted(extra_ids))
        raise ReportSubstancesByComponentError(
            "В amount_results.json найдено отсутствующее в equipments.json "
            f"оборудование: {values}"
        )
    return tuple(
        {
            "component": component,
            "substance": names[substance_id],
            "amount": f"{amount:.3f}".replace(".", ","),
        }
        for (component, substance_id), amount in grouped.items()
    )


def _shade(cell: Any, color: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), color)


def _set_cell_text(
    cell: Any,
    value: str,
    *,
    bold: bool = False,
    centered: bool = False,
) -> None:
    cell.text = ""
    paragraph = cell.paragraphs[0]
    paragraph.paragraph_format.space_before = Pt(0)
    paragraph.paragraph_format.space_after = Pt(0)
    paragraph.alignment = (
        WD_ALIGN_PARAGRAPH.CENTER if centered else WD_ALIGN_PARAGRAPH.LEFT
    )
    run = paragraph.add_run(value)
    run.bold = bold
    run.font.name = "Times New Roman"
    run.font.size = Pt(9)
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for name in ("ascii", "hAnsi", "eastAsia"):
        fonts.set(qn(f"w:{name}"), "Times New Roman")
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER


def _paragraph_section(document: DocumentType, paragraph_element: Any) -> Any:
    section_index = 0
    for child in document.element.body:
        if child is paragraph_element:
            break
        if child.tag == qn("w:p") and child.find(
            f"./{qn('w:pPr')}/{qn('w:sectPr')}"
        ) is not None:
            section_index += 1
    return document.sections[min(section_index, len(document.sections) - 1)]


def _set_table_geometry(section: Any, table: Any) -> None:
    total_twips = int(
        (section.page_width - section.left_margin - section.right_margin) / 635
    )
    proportions = (0.42, 0.35, 0.23)
    widths = [int(total_twips * value) for value in proportions[:-1]]
    widths.append(total_twips - sum(widths))
    table.autofit = False
    properties = table._tbl.tblPr
    table_width = properties.find(qn("w:tblW"))
    if table_width is None:
        table_width = OxmlElement("w:tblW")
        properties.append(table_width)
    table_width.set(qn("w:w"), str(total_twips))
    table_width.set(qn("w:type"), "dxa")
    grid = table._tbl.tblGrid
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        column = OxmlElement("w:gridCol")
        column.set(qn("w:w"), str(width))
        grid.append(column)
    for row in table.rows:
        row_properties = row._tr.get_or_add_trPr()
        if row_properties.find(qn("w:cantSplit")) is None:
            row_properties.append(OxmlElement("w:cantSplit"))
        for cell, width in zip(row._tr.tc_lst, widths):
            cell_width = cell.get_or_add_tcPr().get_or_add_tcW()
            cell_width.set(qn("w:w"), str(width))
            cell_width.set(qn("w:type"), "dxa")


def render_substances_by_component_table(
    document: DocumentType,
    rows: tuple[dict[str, str], ...],
) -> bool:
    marker_paragraph = next(
        (paragraph for paragraph in document.paragraphs if MARKER in paragraph.text),
        None,
    )
    if marker_paragraph is None:
        return False
    section = _paragraph_section(document, marker_paragraph._p)
    table = document.add_table(rows=1, cols=3)
    table.style = "Table Grid"
    marker_paragraph._p.addnext(table._tbl)
    headers = (
        "Составляющая ОПО",
        "Опасное вещество",
        "Количество ОВ в составляющей, т",
    )
    for cell, value in zip(table.rows[0].cells, headers):
        _set_cell_text(cell, value, bold=True, centered=True)
        _shade(cell, "D9E1F2")
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    table.rows[0]._tr.get_or_add_trPr().append(repeat_header)
    for item in rows:
        cells = table.add_row().cells
        values = (item["component"], item["substance"], item["amount"])
        for column, (cell, value) in enumerate(zip(cells, values)):
            _set_cell_text(cell, value, centered=column == 2)
    marker_paragraph._element.getparent().remove(marker_paragraph._element)
    _set_table_geometry(section, table)
    return True


__all__ = [
    "MARKER",
    "ReportSubstancesByComponentError",
    "load_substances_by_component_rows",
    "render_substances_by_component_table",
]
