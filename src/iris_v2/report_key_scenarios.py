from pathlib import Path
from typing import Any

from docx.document import Document as DocumentType
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt

from iris_v2.key_scenarios import KeyScenariosError, KeyScenariosService


MARKER = "{{TOP_SCENARIOS_BY_COMPONENT_SECTION}}"


class ReportKeyScenariosError(Exception):
    pass


def load_key_scenario_rows(
    project_directory: Path | str,
) -> tuple[dict[str, str], ...]:
    try:
        result = KeyScenariosService().calculate(project_directory)
    except KeyScenariosError as exc:
        raise ReportKeyScenariosError(str(exc)) from exc

    return tuple(
        {
            "component": str(item["hazard_component"]),
            "scenario_type": str(item["scenario_type_name"]),
            "scenario_code": str(item["scenario_code"]),
            "equipment": str(item["equipment_name"]),
            "fatalities": str(item["fatalities_count"]),
            "injured": str(item["injured_count"]),
            "damage": f"{float(item['total_damage']):.1f}".replace(".", ","),
            "frequency": f"{float(item['scenario_frequency']):.3E}",
        }
        for item in result.rows
    )


def _shade(cell: Any, color: str) -> None:
    properties = cell._tc.get_or_add_tcPr()
    shading = properties.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        properties.append(shading)
    shading.set(qn("w:fill"), color)


def _cell_margins(cell: Any, value: int = 50) -> None:
    properties = cell._tc.get_or_add_tcPr()
    margins = properties.first_child_found_in("w:tcMar")
    if margins is None:
        margins = OxmlElement("w:tcMar")
        properties.append(margins)
    for side in ("top", "start", "bottom", "end"):
        element = margins.find(qn(f"w:{side}"))
        if element is None:
            element = OxmlElement(f"w:{side}")
            margins.append(element)
        element.set(qn("w:w"), str(value))
        element.set(qn("w:type"), "dxa")


def _set_cell_text(
    cell: Any,
    value: str,
    *,
    bold: bool = False,
    centered: bool = False,
    font_size: float = 8.5,
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
    run.font.size = Pt(font_size)
    fonts = run._element.get_or_add_rPr().get_or_add_rFonts()
    for name in ("ascii", "hAnsi", "eastAsia"):
        fonts.set(qn(f"w:{name}"), "Times New Roman")
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    _cell_margins(cell)


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
    proportions = (0.14, 0.12, 0.08, 0.19, 0.10, 0.12, 0.14, 0.11)
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
        properties = row._tr.get_or_add_trPr()
        if properties.find(qn("w:cantSplit")) is None:
            properties.append(OxmlElement("w:cantSplit"))
        for cell, width in zip(row._tr.tc_lst, widths):
            cell_width = cell.get_or_add_tcPr().get_or_add_tcW()
            cell_width.set(qn("w:w"), str(width))
            cell_width.set(qn("w:type"), "dxa")


def render_key_scenarios_section(
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
    table = document.add_table(rows=1, cols=8)
    table.style = "Table Grid"
    marker_paragraph._p.addnext(table._tbl)
    for run in marker_paragraph.runs:
        run.text = ""
    marker_paragraph.paragraph_format.page_break_before = True
    marker_paragraph.paragraph_format.keep_with_next = True
    marker_paragraph.paragraph_format.space_before = Pt(0)
    marker_paragraph.paragraph_format.space_after = Pt(0)
    headers = (
        "Составляющая\nОПО",
        "Тип сценария",
        "№",
        "Оборудование",
        "Погибло,\nчел.",
        "Пострадало,\nчел.",
        "Суммарный ущерб,\nтыс. руб.",
        "Частота,\n1/год",
    )
    for cell, value in zip(table.rows[0].cells, headers):
        _set_cell_text(cell, value, bold=True, centered=True, font_size=7.5)
        _shade(cell, "D9E1F2")
    repeat_header = OxmlElement("w:tblHeader")
    repeat_header.set(qn("w:val"), "true")
    table.rows[0]._tr.get_or_add_trPr().append(repeat_header)

    for item in rows:
        cells = table.add_row().cells
        values = (
            item["component"],
            item["scenario_type"],
            item["scenario_code"],
            item["equipment"],
            item["fatalities"],
            item["injured"],
            item["damage"],
            item["frequency"],
        )
        for column, (cell, value) in enumerate(zip(cells, values)):
            _set_cell_text(cell, value, centered=column not in (0, 1, 3))

    _set_table_geometry(section, table)
    return True


__all__ = [
    "MARKER",
    "ReportKeyScenariosError",
    "load_key_scenario_rows",
    "render_key_scenarios_section",
]
