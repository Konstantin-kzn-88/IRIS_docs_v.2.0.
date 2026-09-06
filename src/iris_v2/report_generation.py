import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from docx import Document
from docx.oxml.ns import qn
from docx.parts.hdrftr import FooterPart, HeaderPart

from iris_v2.project_common import ProjectCommonError, ProjectCommonService
from iris_v2.report_substances import (
    ReportSubstancesError,
    render_substances_section,
)
from iris_v2.service import DATABASE_NAME, ProjectError, ProjectInfo, ProjectService
from iris_v2.substances import SubstanceError, SubstanceService
from iris_v2.template_catalog import CONFIG_FILE_NAME


OUTPUT_FILE_NAME = "template_report_out.docx"
MARKER_RE = re.compile(r"\{\{\s*([^{}]+?)\s*\}\}")
SUPPORTED_SECTION_MARKERS = frozenset({"SUBSTANCES_SECTION"})

# Эти блоки заполняются отдельными модулями формирования таблиц, выводов и
# диаграмм. На первом этапе их нельзя удалять из документа.
DEFERRED_MARKERS = frozenset(
    {
        "SUBSTANCES_INFO_SECTION",
        "EQUIPMENT_SECTION",
        "DISTRIBUTION_SECTION",
        "SCENARIOS_SECTION",
        "OV_AMOUNT_SECTION",
        "IMPACT_ZONES_SECTION",
        "CASUALTIES_SECTION",
        "DAMAGE_SECTION",
        "FATAL_ACCIDENT_FREQUENCY",
        "COLLECTIVE_RISK_SECTION",
        "INDIVIDUAL_RISK_SECTION",
        "MAX_DAMAGE_BY_COMPONENT_SECTION",
        "FN_CHART",
        "FG_CHART",
        "PARETO_FATALITIES_CHART",
        "PARETO_INJURED_CHART",
        "PARETO_DAMAGE_CHART",
        "PARETO_ENV_DAMAGE_CHART",
        "DAMAGE_BY_COMPONENT_CHART",
        "RISK_MATRIX_CHART",
        "RISK_MATRIX_DAMAGE_CHART",
        "TOP_SCENARIOS_BY_COMPONENT_SECTION",
        "FATALITY_RISK_BY_COMPONENT_SECTION",
        "COMPARATIVE_FATALITY_RISK_TABLE",
        "NGK_BACKGROUND_RISK_COMPARISON",
        "SUBSTANCES_BY_COMPONENT_TABLE",
        "TOP_SCENARIOS_DESC_BY_COMPONENT",
        "TOP_SCENARIOS_PF_BY_COMPONENT",
        "TOP_SCENARIOS_FATALITIES_INJURED",
        "TOP_SCENARIOS_DAMAGE",
        "TOP_SCENARIOS_FINAL_CONCLUSION",
        "MAX_PEOPLE_VICTIMS",
    }
)


class ReportGenerationError(Exception):
    pass


@dataclass(frozen=True)
class ReportGenerationResult:
    output_path: Path
    replaced_count: int
    filled_sections: tuple[str, ...]
    deferred_markers: tuple[str, ...]


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def _sanitary_zone(value: Any) -> str:
    if value in (0, 0.0, "0", "0.0"):
        return "отсутствует"
    return _text(value)


def _build_replacements(
    project: ProjectInfo,
    common: dict[str, Any],
    generated_at: datetime,
) -> dict[str, str]:
    root = _as_dict(project.organization_snapshot)
    organization = _as_dict(root.get("organization"))
    ids = _as_dict(organization.get("ids"))
    contacts = _as_dict(organization.get("contacts"))
    head = _as_dict(organization.get("head"))
    permits = _as_dict(root.get("permits"))
    management = _as_dict(root.get("management_docs"))
    security = _as_dict(root.get("security_and_response"))
    reserves = _as_dict(root.get("reserves"))
    site = _as_dict(project.opo_snapshot)
    personnel = _as_dict(site.get("personnel"))
    executor = _as_dict(common.get("executor"))

    values: dict[str, Any] = {
        "generated_at": generated_at.strftime("%d.%m.%Y %H:%M"),
        "db_path": DATABASE_NAME,
        "PROJECT_YEAR": common.get("year"),
        "PROJECT_NAME": common.get("project_name", project.name),
        "PROJECT_CODE": common.get("project_code", project.code),
        "DPB_CODE": common.get("dpb_code"),
        "GOCHS_CODE": common.get("gochs_code"),
        "PB_CODE": common.get("pb_code"),
        "EXECUTOR_NAME": executor.get("name"),
        "EXECUTOR_ADDRESS": executor.get("address"),
        "EXECUTOR_SRO": executor.get("sro"),
        "EXECUTOR_INN": executor.get("inn"),
        "EXECUTOR_OGRN": executor.get("ogrn"),
        "EXECUTOR_TEL": executor.get("tel"),
        "EXECUTOR_EMAIL": executor.get("email"),
        "EXECUTOR_WEBSITE": executor.get("website"),
        "EXECUTOR_HEAD_POSITION": executor.get("head_position"),
        "EXECUTOR_HEAD_FULL_NAME": executor.get("head_full_name"),
        "EXECUTOR_SPECIALIST_INFO": executor.get("specialist_info"),
        "FULL_NAME": organization.get("full_name"),
        "SHORT_NAME": organization.get("short_name", project.organization_name),
        "OGRN": ids.get("ogrn"),
        "INN": ids.get("inn"),
        "KPP": ids.get("kpp"),
        "ORG_ADDRESS": organization.get("address"),
        "ORG_EMAIL": contacts.get("email"),
        "ORG_PHONE": contacts.get("phone"),
        "ORG_FAX": contacts.get("fax"),
        "HEAD_POSITION": head.get("position"),
        "HEAD_FULL_NAME": head.get("full_name"),
        "HEAD_SHORT_NAME": head.get("short_name"),
        "LICENSE_NUMBER": permits.get("license_number"),
        "INDUSTRIAL_SAFETY_MANAGEMENT_SYSTEM": management.get(
            "industrial_safety_management_system"
        ),
        "INDUSTRIAL_CONTROL_REGULATION": management.get(
            "industrial_control_regulation"
        ),
        "ACCIDENT_INVESTIGATION_REGULATION": management.get(
            "accident_investigation_regulation"
        ),
        "OPO_SECURITY": security.get("opo_security"),
        "NASF_INFORMATION": security.get("nasf_information"),
        "PASF_INFORMATION": security.get("pasf_information"),
        "FINANCIAL_RESERVE_ORDER": reserves.get("financial_reserve_order"),
        "MATERIAL_RESERVE_ORDER": reserves.get("material_reserve_order"),
        "SITE_ID": site.get("site_id"),
        "SITE_NAME": site.get("name", project.opo_name),
        "SITE_REG_NUMBER": site.get(
            "reg_number", project.opo_registration_number
        ),
        "SITE_OBJECT_ID": site.get("object_id"),
        "SITE_OBJECT_ADDRESS": site.get("object_address"),
        "SITE_SANITARY_PROTECTION_ZONE_M": _sanitary_zone(
            site.get("sanitary_protection_zone_m")
        ),
        "SITE_DESCRIPTION": site.get("description"),
        "SITE_AREA_CHARACTERISTICS": site.get("area_characteristics"),
        "SITE_EMPLOYEES_COUNT": personnel.get("employees_count"),
        "SITE_EMPLOYEES_OTHER_OPO_COUNT": personnel.get(
            "employees_other_opo_count"
        ),
        "SITE_EMERGENCY_RESPONSE_PLAN": site.get("emergency_response_plan"),
    }
    return {key: _text(value) for key, value in values.items()}


def _story_elements(document: Any) -> Iterable[Any]:
    """Основной текст, колонтитулы, таблицы и текстовые поля внутри них."""
    yield document.element.body
    for part in document.part.package.parts:
        if isinstance(part, (HeaderPart, FooterPart)):
            yield part.element


def _paragraph_markers(paragraph: Any) -> list[re.Match[str]]:
    text = "".join(node.text or "" for node in paragraph.iter(qn("w:t")))
    return list(MARKER_RE.finditer(text))


def _marker_names(document: Any) -> set[str]:
    result: set[str] = set()
    for story in _story_elements(document):
        for paragraph in story.iter(qn("w:p")):
            result.update(
                match.group(1).strip()
                for match in _paragraph_markers(paragraph)
            )
    return result


def _replace_in_paragraph(paragraph: Any, replacements: dict[str, str]) -> int:
    text_nodes = list(paragraph.iter(qn("w:t")))
    if not text_nodes:
        return 0
    texts = [node.text or "" for node in text_nodes]
    full_text = "".join(texts)
    matches = [
        match for match in MARKER_RE.finditer(full_text)
        if match.group(1).strip() in replacements
    ]
    if not matches:
        return 0

    starts: list[int] = []
    position = 0
    for value in texts:
        starts.append(position)
        position += len(value)

    for match in reversed(matches):
        start, end = match.span()
        start_index = next(
            index
            for index, node_start in enumerate(starts)
            if node_start + len(texts[index]) > start
        )
        end_index = next(
            index
            for index, node_start in enumerate(starts)
            if node_start + len(texts[index]) >= end
        )
        start_offset = start - starts[start_index]
        end_offset = end - starts[end_index]
        before = texts[start_index][:start_offset]
        after = texts[end_index][end_offset:]
        value = replacements[match.group(1).strip()]
        texts[start_index] = before + value + after if start_index == end_index else before + value
        for index in range(start_index + 1, end_index):
            texts[index] = ""
        if end_index != start_index:
            texts[end_index] = after

    xml_space = "{http://www.w3.org/XML/1998/namespace}space"
    for node, value in zip(text_nodes, texts):
        node.text = value
        if value.startswith(" ") or value.endswith(" "):
            node.set(xml_space, "preserve")
    return len(matches)


def _replace_markers(document: Any, replacements: dict[str, str]) -> int:
    count = 0
    for story in _story_elements(document):
        for paragraph in story.iter(qn("w:p")):
            count += _replace_in_paragraph(paragraph, replacements)
    return count


class ReportGenerationService:
    def __init__(self, project_service: ProjectService | None = None) -> None:
        self.project_service = project_service or ProjectService()

    def generate(
        self,
        project_directory: Path | str,
        *,
        generated_at: datetime | None = None,
    ) -> ReportGenerationResult:
        project_root = Path(project_directory).resolve()
        try:
            project = self.project_service.open(project_root)
        except ProjectError as exc:
            raise ReportGenerationError(str(exc)) from exc
        template_path = self._template_path(project_root)
        try:
            common = ProjectCommonService().load(
                project_root, project.name, project.code
            )
        except ProjectCommonError as exc:
            raise ReportGenerationError(str(exc)) from exc

        try:
            document = Document(template_path)
        except Exception as exc:
            raise ReportGenerationError(
                f"Не удалось открыть шаблон: {template_path.name}"
            ) from exc

        replacements = _build_replacements(
            project, common, generated_at or datetime.now()
        )
        marker_names = _marker_names(document)
        unknown = (
            marker_names
            - replacements.keys()
            - DEFERRED_MARKERS
            - SUPPORTED_SECTION_MARKERS
        )
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ReportGenerationError(f"Неизвестные маркеры шаблона: {names}")

        replaced_count = _replace_markers(document, replacements)
        filled_sections: list[str] = []
        if "SUBSTANCES_SECTION" in marker_names:
            try:
                substances = SubstanceService().load_project(project_root)
                if render_substances_section(document, substances):
                    filled_sections.append("SUBSTANCES_SECTION")
            except (SubstanceError, ReportSubstancesError) as exc:
                raise ReportGenerationError(str(exc)) from exc
        remaining = _marker_names(document)
        unexpected = remaining - DEFERRED_MARKERS
        if unexpected:
            names = ", ".join(sorted(unexpected))
            raise ReportGenerationError(f"Не удалось заполнить маркеры: {names}")

        output_directory = project_root / "output"
        output_path = output_directory / OUTPUT_FILE_NAME
        temporary_path = output_directory / f".{OUTPUT_FILE_NAME}.tmp.docx"
        try:
            output_directory.mkdir(parents=True, exist_ok=True)
            document.save(temporary_path)
            temporary_path.replace(output_path)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            raise ReportGenerationError(
                f"Не удалось сохранить отчёт: {output_path}"
            ) from exc

        return ReportGenerationResult(
            output_path=output_path,
            replaced_count=replaced_count,
            filled_sections=tuple(filled_sections),
            deferred_markers=tuple(sorted(remaining)),
        )

    @staticmethod
    def _template_path(project_root: Path) -> Path:
        config_path = project_root / CONFIG_FILE_NAME
        try:
            config = json.loads(config_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReportGenerationError(
                "Файл report_config.json отсутствует или повреждён"
            ) from exc
        documents = config.get("documents")
        if not isinstance(documents, list) or not documents:
            raise ReportGenerationError("В report_config.json не выбран шаблон")
        selected = next(
            (
                item for item in documents
                if isinstance(item, dict)
                and item.get("name") == "template_report.docx"
            ),
            documents[0] if len(documents) == 1 else None,
        )
        if not isinstance(selected, dict):
            raise ReportGenerationError(
                "В комплекте не найден template_report.docx"
            )
        relative_path = selected.get("path")
        checksum = selected.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(checksum, str):
            raise ReportGenerationError("Некорректная запись шаблона в конфигурации")
        template_path = (project_root / relative_path).resolve()
        try:
            template_path.relative_to(project_root)
        except ValueError as exc:
            raise ReportGenerationError("Путь к шаблону выходит за папку проекта") from exc
        if not template_path.is_file():
            raise ReportGenerationError(f"Шаблон не найден: {relative_path}")
        try:
            actual_checksum = _hash_file(template_path)
        except OSError as exc:
            raise ReportGenerationError(
                f"Не удалось прочитать шаблон: {relative_path}"
            ) from exc
        if actual_checksum != checksum:
            raise ReportGenerationError(
                "Шаблон изменён после выбора. Выберите комплект шаблонов заново"
            )
        return template_path
