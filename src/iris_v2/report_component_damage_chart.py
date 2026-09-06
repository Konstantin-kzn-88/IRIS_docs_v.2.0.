from pathlib import Path

from iris_v2.component_damage_chart import (
    ComponentDamageChartError,
    ComponentDamageChartService,
    _read_components,
)
from iris_v2.report_max_damage import load_max_damage_rows
from iris_v2.risk_summary import FILE_NAME as SUMMARY_FILE_NAME


MARKER = "{{DAMAGE_BY_COMPONENT_CHART}}"
EMPTY_TEXT = (
    "Диаграмма распределения ущерба по составляющим ОПО не построена: "
    "положительные значения отсутствуют."
)


def prepare_component_damage_chart(
    project_directory: Path | str,
) -> Path | None:
    project = Path(project_directory)
    load_max_damage_rows(project)
    if not _read_components(project / SUMMARY_FILE_NAME):
        return None
    return ComponentDamageChartService().calculate(project).path


__all__ = [
    "ComponentDamageChartError",
    "EMPTY_TEXT",
    "MARKER",
    "prepare_component_damage_chart",
]
