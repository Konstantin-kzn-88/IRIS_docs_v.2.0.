import json
from pathlib import Path


DONE = "done"
PENDING = "pending"
NOT_REQUIRED = "not_required"


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
        ("risk_button", "risk_results.json", ("damage_results.json", "frequency_results.json", "project_common.json"), ("damage_button", "frequency_button", "project_common_button")),
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

    chart_directory = project / "output" / "charts"
    chart_steps = (
        ("risk_charts_button", ("fn_chart.png", "fg_chart.png"), ("risk_summary.json",), "risk_summary_button"),
        ("risk_matrices_button", ("risk_matrix.png", "risk_matrix_damage.png"), ("risk_results.json",), "risk_button"),
        ("pareto_charts_button", ("pareto_fatalities.png", "pareto_injured.png", "pareto_damage.png", "pareto_environmental_damage.png"), ("risk_results.json",), "risk_button"),
        ("component_damage_chart_button", ("damage_by_component.png",), ("risk_summary.json",), "risk_summary_button"),
    )
    for button, output_names, inputs, prerequisite in chart_steps:
        outputs = tuple(str(Path("output") / "charts" / name) for name in output_names)
        statuses[button] = (
            DONE
            if statuses[prerequisite] == DONE and _fresh(project, outputs, inputs)
            else PENDING
        )

    report = project / "output" / "template_report_out.docx"
    report_inputs = [path for path in project.glob("*.json") if path.is_file()]
    report_inputs.extend(path for path in chart_directory.glob("*.png") if path.is_file())
    template = project / "default" / "template_report.docx"
    if template.is_file():
        report_inputs.append(template)
    statuses["report_generation_button"] = (
        DONE
        if report.is_file()
        and report_inputs
        and report.stat().st_mtime_ns
        >= max(path.stat().st_mtime_ns for path in report_inputs)
        else PENDING
    )
    return statuses
