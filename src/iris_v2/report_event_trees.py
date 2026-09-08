import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from docx.document import Document as DocumentType
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Inches, Pt
from PIL import Image

from iris_v2.calculation_cases import FILE_NAME as CASES_FILE_NAME
from iris_v2.event_tree_images import EventTreeImageError, EventTreeImageService
from iris_v2.typical_scenarios import TypicalScenarioError, TypicalScenarioService


MARKER = "{{EVENT_TREES_SECTION}}"


class ReportEventTreesError(Exception):
    pass


@dataclass(frozen=True)
class EventTreeReportItem:
    equipment_type: int
    kind: int
    equipment_name: str
    kind_name: str
    path: Path


def _load_cases(project: Path) -> list[dict[str, Any]]:
    path = project / CASES_FILE_NAME
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReportEventTreesError(
            "Расчётные сценарии не сформированы. "
            "Сначала выполните модуль «Расчётные сценарии»"
        ) from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportEventTreesError(
            f"Не удалось прочитать {CASES_FILE_NAME}"
        ) from exc
    cases = raw.get("cases") if isinstance(raw, dict) else None
    if (
        not isinstance(cases, list)
        or not cases
        or any(not isinstance(item, dict) for item in cases)
    ):
        raise ReportEventTreesError(
            f"Файл {CASES_FILE_NAME} не содержит расчётных сценариев"
        )
    return cases


def prepare_event_trees(
    project_directory: Path | str,
) -> tuple[EventTreeReportItem, ...]:
    project = Path(project_directory)
    cases = _load_cases(project)
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for index, case in enumerate(cases, start=1):
        equipment_type = case.get("equipment_type")
        kind = case.get("kind")
        if (
            isinstance(equipment_type, bool)
            or not isinstance(equipment_type, int)
            or equipment_type not in range(10)
        ):
            raise ReportEventTreesError(
                f"Сценарий {index}: equipment_type должен быть от 0 до 9"
            )
        if isinstance(kind, bool) or not isinstance(kind, int) or kind not in range(10):
            raise ReportEventTreesError(
                f"Сценарий {index}: kind должен быть от 0 до 9"
            )
        pair = (equipment_type, kind)
        if pair not in seen:
            seen.add(pair)
            pairs.append(pair)

    try:
        catalog = TypicalScenarioService().load()
        copied = EventTreeImageService().copy_to_project(
            project, pairs=set(pairs)
        )
    except (TypicalScenarioError, EventTreeImageError) as exc:
        raise ReportEventTreesError(str(exc)) from exc
    paths = {path.name: path for path in copied.files}
    result: list[EventTreeReportItem] = []
    for equipment_type, kind in pairs:
        filename = f"event_tree_eq{equipment_type:02d}_kind{kind:02d}.png"
        path = paths.get(filename)
        if path is None:
            raise ReportEventTreesError(f"Не найдено дерево событий: {filename}")
        result.append(
            EventTreeReportItem(
                equipment_type=equipment_type,
                kind=kind,
                equipment_name=catalog.equipment_types[equipment_type],
                kind_name=catalog.kinds[kind],
                path=path,
            )
        )
    return tuple(result)


def _paragraph_section(document: DocumentType, element: Any) -> Any:
    section_index = 0
    for child in document.element.body:
        if child is element:
            break
        if child.tag == qn("w:p") and child.find(
            f"./{qn('w:pPr')}/{qn('w:sectPr')}"
        ) is not None:
            section_index += 1
    return document.sections[min(section_index, len(document.sections) - 1)]


def _set_font(run: Any, size: float, *, bold: bool = False) -> None:
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.font.bold = bold
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), "Times New Roman")


def _short_kind_name(value: str) -> str:
    base, separator, suffix = value.rpartition(" (")
    if not separator or not suffix.endswith(")"):
        return value
    parenthetical = suffix[:-1].strip()
    if parenthetical.isupper() and len(parenthetical) <= 10:
        return parenthetical
    return base.strip()


def _picture_width(path: Path, available_width: int, max_height: int) -> int:
    try:
        with Image.open(path) as image:
            width_px, height_px = image.size
    except (OSError, ValueError) as exc:
        raise ReportEventTreesError(
            f"Не удалось прочитать PNG-дерево: {path.name}"
        ) from exc
    if width_px <= 0 or height_px <= 0:
        raise ReportEventTreesError(f"Некорректный PNG-файл: {path.name}")
    return min(available_width, int(max_height * width_px / height_px))


def render_event_trees_section(
    document: DocumentType,
    items: tuple[EventTreeReportItem, ...],
) -> bool:
    marker_paragraph = next(
        (paragraph for paragraph in document.paragraphs if MARKER in paragraph.text),
        None,
    )
    if marker_paragraph is None:
        return False
    if not items:
        raise ReportEventTreesError("Не выбрано ни одного дерева событий")
    section = _paragraph_section(document, marker_paragraph._p)
    available_width = section.page_width - section.left_margin - section.right_margin
    max_height = Inches(5.5)
    anchor = marker_paragraph._p
    for item in items:
        picture_paragraph = document.add_paragraph()
        picture_paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        picture_paragraph.paragraph_format.page_break_before = True
        picture_paragraph.paragraph_format.keep_with_next = True
        picture_paragraph.paragraph_format.space_before = Pt(0)
        picture_paragraph.paragraph_format.space_after = Pt(3)
        picture_run = picture_paragraph.add_run()
        picture_run.add_picture(
            str(item.path),
            width=_picture_width(item.path, available_width, max_height),
        )
        anchor.addnext(picture_paragraph._p)
        anchor = picture_paragraph._p

        caption = document.add_paragraph()
        caption.alignment = WD_ALIGN_PARAGRAPH.CENTER
        caption.paragraph_format.keep_together = True
        caption.paragraph_format.space_before = Pt(0)
        caption.paragraph_format.space_after = Pt(6)
        run = caption.add_run(
            "Рисунок – Дерево событий для типа оборудования "
            f"«{item.equipment_name}» и вида опасного вещества "
            f"«{_short_kind_name(item.kind_name)}»"
        )
        _set_font(run, 12)
        anchor.addnext(caption._p)
        anchor = caption._p
    marker_paragraph._element.getparent().remove(marker_paragraph._element)
    return True
