from pathlib import Path

from iris_v2.component_impact_zones_chart import (
    ComponentImpactZonesChartError,
    ComponentImpactZonesChartService,
    read_component_zone_maxima,
)


MARKER = "{{MAX_IMPACT_ZONES_BY_COMPONENT_CHART}}"
EMPTY_TEXT = "Диаграмма максимальных зон не построена: радиусы отсутствуют."


def prepare_component_impact_zones_chart(
    project_directory: Path | str,
) -> Path | None:
    project = Path(project_directory)
    if not read_component_zone_maxima(project / "impact_zones.json"):
        return None
    return ComponentImpactZonesChartService().calculate(project).path


__all__ = [
    "ComponentImpactZonesChartError",
    "EMPTY_TEXT",
    "MARKER",
    "prepare_component_impact_zones_chart",
]
