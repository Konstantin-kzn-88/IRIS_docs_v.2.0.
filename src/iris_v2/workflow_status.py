import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from iris_v2.impact_types import IMPACT_TYPE_NAMES


DONE = "done"
PENDING = "pending"
NOT_REQUIRED = "not_required"


REFRESH_STEP_ORDER = (
    ("amount_button", "Количество ОВ"),
    ("calculation_cases_button", "Расчётные сценарии"),
    ("frequency_button", "Расчёт частот"),
    ("release_button", "Масса в аварии"),
    ("spill_button", "Площадь пролива"),
    ("evaporation_button", "Испарение"),
    ("hazard_factor_button", "Масса поражающего фактора"),
    ("pool_fire_button", "Пожар пролива"),
    ("explosion_button", "Взрыв ТВС"),
    ("flash_fire_button", "Пожар-вспышка"),
    ("toxic_button", "Токсическое поражение"),
    ("jet_fire_button", "Факельное горение"),
    ("fireball_button", "Огненный шар"),
    ("chemical_spill_button", "Химически опасный пролив"),
    ("impact_zones_button", "Свод зон"),
    ("people_button", "Расчёт пострадавших"),
    ("damage_button", "Расчёт ущерба"),
    ("risk_button", "Расчёт риска"),
    ("risk_summary_button", "Свод риска"),
    ("key_scenarios_button", "Ключевые сценарии"),
    ("risk_charts_button", "Диаграммы риска"),
    ("risk_matrices_button", "Матрицы риска"),
    ("pareto_charts_button", "Диаграммы Парето"),
    ("component_damage_chart_button", "Ущерб по ОПО"),
    ("component_impact_zones_chart_button", "Максимальные зоны по ОПО"),
    ("report_generation_button", "Формирование Word-отчёта"),
)


class WorkflowRefreshError(RuntimeError):
    """A refresh stage failed."""


@dataclass(frozen=True)
class WorkflowRefreshResult:
    completed: tuple[str, ...]
    skipped: tuple[str, ...]
    cancelled: bool


def refresh_workflow(
    project_directory: Path,
    runners: dict[str, Callable[[], object]],
    *,
    status_provider: Callable[[Path], dict[str, str]] | None = None,
    on_step: Callable[[int, int, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> WorkflowRefreshResult:
    """Run stale calculation stages in dependency order."""
    provider = status_provider or workflow_statuses
    completed: list[str] = []
    skipped: list[str] = []
    total = len(REFRESH_STEP_ORDER)

    for index, (button_name, label) in enumerate(REFRESH_STEP_ORDER, start=1):
        if is_cancelled is not None and is_cancelled():
            return WorkflowRefreshResult(tuple(completed), tuple(skipped), True)
        if on_step is not None:
            on_step(index, total, label)

        status = provider(Path(project_directory)).get(button_name, PENDING)
        if status != PENDING:
            skipped.append(button_name)
            continue
        runner = runners.get(button_name)
        if runner is None:
            raise WorkflowRefreshError(
                f"Этап «{label}» не подключён к автоматическому обновлению"
            )
        try:
            runner()
        except Exception as exc:
            raise WorkflowRefreshError(f"Этап «{label}»: {exc}") from exc
        completed.append(button_name)

    return WorkflowRefreshResult(tuple(completed), tuple(skipped), False)


_EFFECTS = {
    "pool_fire_button": (1, "pool_fire_results.json"),
    "explosion_button": (2, "explosion_results.json"),
    "flash_fire_button": (3, "flash_fire_results.json"),
    "toxic_button": (4, "toxic_results.json"),
    "jet_fire_button": (5, "jet_fire_results.json"),
    "fireball_button": (6, "fireball_results.json"),
    "chemical_spill_button": (7, "chemical_spill_results.json"),
}


def _fresh(project: Path, outputs: tuple[str, ...], inputs: tuple[str, ...]) -> bool:
    output_paths = tuple(project / name for name in outputs)
    input_paths = tuple(project / name for name in inputs)
    if not all(path.is_file() for path in output_paths + input_paths):
        return False
    return min(path.stat().st_mtime_ns for path in output_paths) >= max(
        path.stat().st_mtime_ns for path in input_paths
    )


def _calculation_codes(project: Path) -> set[int] | None:
    path = project / "hazard_factor_results.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        results = data.get("results")
        if not isinstance(results, list):
            return None
        return {
            value["calc_code"]
            for value in results
            if isinstance(value, dict)
            and isinstance(value.get("calc_code"), int)
            and not isinstance(value.get("calc_code"), bool)
        }
    except (OSError, json.JSONDecodeError):
        return None


def _impact_types_current(project: Path) -> bool:
    path = project / "impact_zones.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list) or not results:
        return False
    return all(
        isinstance(item, dict)
        and item.get("calc_code") in IMPACT_TYPE_NAMES
        and item.get("impact_type") == IMPACT_TYPE_NAMES[item["calc_code"]]
        for item in results
    )


def workflow_statuses(project_directory: Path) -> dict[str, str]:
    """Return persistent GUI step states derived from project artifacts."""
    project = Path(project_directory)
    statuses: dict[str, str] = {}

    source_files = {
        "project_common_button": "project_common.json",
        "substances_button": "substances.json",
        "equipment_button": "equipments.json",
        "calculation_config_button": "calculation_config.json",
    }
    for button, file_name in source_files.items():
        statuses[button] = DONE if (project / file_name).is_file() else PENDING

    steps = (
        ("amount_button", "amount_results.json", ("equipments.json", "substances.json"), ("equipment_button", "substances_button")),
        ("calculation_cases_button", "calculation_cases.json", ("equipments.json", "substances.json"), ("equipment_button", "substances_button")),
        ("frequency_button", "frequency_results.json", ("calculation_cases.json", "calculation_config.json"), ("calculation_cases_button", "calculation_config_button")),
        ("release_button", "release_results.json", ("calculation_cases.json", "amount_results.json", "calculation_config.json"), ("calculation_cases_button", "amount_button", "calculation_config_button")),
        ("spill_button", "spill_results.json", ("release_results.json", "equipments.json"), ("release_button", "equipment_button")),
        ("evaporation_button", "evaporation_results.json", ("spill_results.json", "release_results.json", "substances.json", "calculation_config.json"), ("spill_button", "release_button", "substances_button", "calculation_config_button")),
        ("hazard_factor_button", "hazard_factor_results.json", ("evaporation_results.json", "calculation_config.json"), ("evaporation_button", "calculation_config_button")),
    )
    for button, output, inputs, prerequisites in steps:
        statuses[button] = (
            DONE
            if all(statuses[name] == DONE for name in prerequisites)
            and _fresh(project, (output,), inputs)
            else PENDING
        )

    statuses["validation_button"] = (
        DONE
        if all(statuses[name] == DONE for name in (*source_files, "amount_button"))
        else PENDING
    )

    codes = (
        _calculation_codes(project)
        if statuses["hazard_factor_button"] == DONE
        else None
    )
    required_effect_outputs: list[str] = []
    for button, (code, output) in _EFFECTS.items():
        if codes is not None and code not in codes:
            statuses[button] = NOT_REQUIRED
        else:
            statuses[button] = (
                DONE
                if _fresh(project, (output,), ("hazard_factor_results.json",))
                else PENDING
            )
            if codes is not None and code in codes:
                required_effect_outputs.append(output)

    required_effect_buttons = tuple(
        button for button, (code, _) in _EFFECTS.items() if codes and code in codes
    )
    consequence_steps = (
        ("impact_zones_button", "impact_zones.json", ("hazard_factor_results.json", *required_effect_outputs), ("hazard_factor_button", *required_effect_buttons)),
        ("people_button", "people_results.json", ("impact_zones.json", "equipments.json"), ("impact_zones_button", "equipment_button")),
        ("damage_button", "damage_results.json", ("people_results.json", "amount_results.json", "calculation_config.json"), ("people_button", "amount_button", "calculation_config_button")),
        ("risk_button", "risk_results.json", ("damage_results.json", "frequency_results.json", "project_common.json", "project.sqlite3"), ("damage_button", "frequency_button", "project_common_button")),
        ("risk_summary_button", "risk_summary.json", ("risk_results.json",), ("risk_button",)),
        ("key_scenarios_button", "key_scenarios.json", ("risk_results.json",), ("risk_button",)),
    )
    for button, output, inputs, prerequisites in consequence_steps:
        statuses[button] = (
            DONE
            if all(statuses[name] == DONE for name in prerequisites)
            and _fresh(project, (output,), inputs)
            else PENDING
        )
        if (
            button == "impact_zones_button"
            and statuses[button] == DONE
            and not _impact_types_current(project)
        ):
            statuses[button] = PENDING

    chart_directory = project / "output" / "charts"
    chart_steps = (
        ("risk_charts_button", ("fn_chart.png", "fg_chart.png"), ("risk_summary.json",), "risk_summary_button"),
        ("risk_matrices_button", ("risk_matrix.png", "risk_matrix_damage.png"), ("risk_results.json",), "risk_button"),
        ("pareto_charts_button", ("pareto_fatalities.png", "pareto_injured.png", "pareto_damage.png", "pareto_environmental_damage.png"), ("risk_results.json",), "risk_button"),
        ("component_damage_chart_button", ("damage_by_component.png",), ("risk_summary.json",), "risk_summary_button"),
        ("component_impact_zones_chart_button", ("max_impact_zones_by_component.png",), ("impact_zones.json",), "impact_zones_button"),
    )
    for button, output_names, inputs, prerequisite in chart_steps:
        outputs = tuple(str(Path("output") / "charts" / name) for name in output_names)
        statuses[button] = (
            DONE
            if statuses[prerequisite] == DONE and _fresh(project, outputs, inputs)
            else PENDING
        )

    report_config = project / "report_config.json"
    report_names = ["template_report_out.docx"]
    selected_templates: list[Path] = []
    if report_config.is_file():
        try:
            config = json.loads(report_config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            config = {}
        documents = config.get("documents") if isinstance(config, dict) else None
        if isinstance(documents, list) and documents:
            report_names = []
            for item in documents:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", "")).strip()
                relative_path = str(item.get("path", "")).strip()
                if name == "template_report.docx":
                    report_names.append("template_report_out.docx")
                elif name.lower().endswith(".docx"):
                    stem = Path(name).stem
                    if "_template_" in stem:
                        stem = stem.replace("_template_", "_", 1)
                    elif stem.endswith("_template"):
                        stem = stem.removesuffix("_template")
                    else:
                        stem = f"{stem}_out"
                    report_names.append(f"{stem}.docx")
                if relative_path:
                    selected_templates.append(project / relative_path)
    reports = tuple(project / "output" / name for name in report_names)
    report_inputs = [path for path in project.glob("*.json") if path.is_file()]
    report_inputs.extend(path for path in chart_directory.glob("*.png") if path.is_file())
    report_inputs.extend(path for path in selected_templates if path.is_file())
    if not selected_templates:
        default_template = project / "default" / "template_report.docx"
        if default_template.is_file():
            report_inputs.append(default_template)
    statuses["report_generation_button"] = (
        DONE
        if reports
        and all(report.is_file() for report in reports)
        and report_inputs
        and min(report.stat().st_mtime_ns for report in reports)
        >= max(path.stat().st_mtime_ns for path in report_inputs)
        else PENDING
    )
    return statuses
