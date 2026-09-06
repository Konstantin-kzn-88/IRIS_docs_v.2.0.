from dataclasses import dataclass
from pathlib import Path

from iris_v2.pareto_charts import (
    ParetoChartsError,
    ParetoChartsService,
    _read_rows,
)
from iris_v2.risk_calculation import FILE_NAME as RISK_FILE_NAME


FATALITIES_MARKER = "{{PARETO_FATALITIES_CHART}}"
INJURED_MARKER = "{{PARETO_INJURED_CHART}}"
FATALITIES_EMPTY_TEXT = (
    "Диаграмма Парето по коллективному риску гибели не построена: "
    "положительные значения отсутствуют."
)
INJURED_EMPTY_TEXT = (
    "Диаграмма Парето по коллективному риску травмирования не построена: "
    "положительные значения отсутствуют."
)


@dataclass(frozen=True)
class ReportParetoCharts:
    fatalities_path: Path | None
    injured_path: Path | None


def prepare_pareto_risk_charts(
    project_directory: Path | str,
) -> ReportParetoCharts:
    project = Path(project_directory)
    rows = _read_rows(project / RISK_FILE_NAME)
    result = ParetoChartsService().calculate(project)
    return ReportParetoCharts(
        fatalities_path=(
            result.fatalities_path
            if any(row["collective_risk_fatalities"] > 0 for row in rows)
            else None
        ),
        injured_path=(
            result.injured_path
            if any(row["collective_risk_injured"] > 0 for row in rows)
            else None
        ),
    )


__all__ = [
    "FATALITIES_EMPTY_TEXT",
    "FATALITIES_MARKER",
    "INJURED_EMPTY_TEXT",
    "INJURED_MARKER",
    "ParetoChartsError",
    "ReportParetoCharts",
    "prepare_pareto_risk_charts",
]
