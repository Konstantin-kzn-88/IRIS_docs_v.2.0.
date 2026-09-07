import json
from pathlib import Path

from iris_v2.report_impact_zones import LEGEND, ZONE_FIELDS, load_impact_zone_rows


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_zone_designations_and_chemical_spill_area(tmp_path: Path) -> None:
    common = {
        "equipment_name": "Аппарат",
        "hazard_component": "Участок",
    }
    factors = [
        {"id": 1, "scenario_code": "С1", "calc_code": 2, **common},
        {"id": 2, "scenario_code": "С2", "calc_code": 7, **common},
    ]
    impacts = [
        {
            **factors[0],
            "impact_values": {"p_100_m": 10.04, "p_70_m": 20.05},
            "spill_area_m2": 500.0,
        },
        {
            **factors[1],
            "impact_values": {"chemical_spill_area_m2": 125.55},
        },
    ]
    write_json(tmp_path / "hazard_factor_results.json", {"results": factors})
    write_json(tmp_path / "impact_zones.json", {"results": impacts})

    rows = load_impact_zone_rows(tmp_path)

    assert rows[0]["p_100_m"] == "10,0"
    assert rows[0]["p_70_m"] == "20,1"
    assert rows[0]["spill_area_m2"] == "—"
    assert rows[1]["spill_area_m2"] == "125,5"
    assert ("lethal_radius_m", "LD") in ZONE_FIELDS
    assert ("threshold_radius_m", "PD") in ZONE_FIELDS
    assert "Lпт" not in LEGEND
    assert "Pпт" not in LEGEND
