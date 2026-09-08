import json
from pathlib import Path

from iris_v2.component_impact_zones_chart import (
    ComponentImpactZonesChartService,
    read_component_zone_maxima,
)


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_zone_maxima_are_grouped_by_component(tmp_path: Path) -> None:
    results = [
        {
            "hazard_component": "Участок А",
            "calc_code": 1,
            "impact_values": {"q_1_4_m": 100.0},
        },
        {
            "hazard_component": "Участок А",
            "calc_code": 1,
            "impact_values": {"q_1_4_m": 150.0},
        },
        {
            "hazard_component": "Участок А",
            "calc_code": 2,
            "impact_values": {"p_2_m": 800.0},
        },
        {
            "hazard_component": "Участок Б",
            "calc_code": 4,
            "impact_values": {"threshold_radius_m": 1200.0},
        },
        {
            "hazard_component": "Участок Б",
            "calc_code": 7,
            "impact_values": {"chemical_spill_area_m2": 5000.0},
        },
    ]
    path = tmp_path / "impact_zones.json"
    write_json(path, {"results": results})

    assert read_component_zone_maxima(path) == [
        ("Участок А", (150.0, 800.0, 0.0, 0.0)),
        ("Участок Б", (0.0, 0.0, 0.0, 1200.0)),
    ]


def test_chart_is_saved_as_png(tmp_path: Path) -> None:
    write_json(
        tmp_path / "impact_zones.json",
        {
            "results": [
                {
                    "hazard_component": "Участок А",
                    "calc_code": 3,
                    "impact_values": {"flash_fire_radius_m": 250.0},
                }
            ]
        },
    )

    result = ComponentImpactZonesChartService().calculate(tmp_path)

    assert result.path.name == "max_impact_zones_by_component.png"
    assert result.path.read_bytes().startswith(b"\x89PNG")
