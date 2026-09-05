import json
from dataclasses import dataclass
from pathlib import Path


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class HazardousFacility:
    name: str
    registration_number: str


@dataclass(frozen=True)
class Organization:
    name: str
    facilities: tuple[HazardousFacility, ...]


def load_organizations(path: Path | str | None = None) -> tuple[Organization, ...]:
    if path is not None:
        catalog_path = Path(path)
    else:
        local_catalog = Path.cwd() / "organizations.local.json"
        catalog_path = (
            local_catalog
            if local_catalog.is_file()
            else Path(__file__).parent / "data" / "organizations.json"
        )
    try:
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        items = raw["organizations"]
        organizations = tuple(
            Organization(
                name=item["name"].strip(),
                facilities=tuple(
                    HazardousFacility(
                        name=facility["name"].strip(),
                        registration_number=facility["registration_number"].strip(),
                    )
                    for facility in item["facilities"]
                ),
            )
            for item in items
        )
    except (OSError, json.JSONDecodeError, KeyError, TypeError, AttributeError) as exc:
        raise CatalogError(f"Не удалось прочитать справочник: {catalog_path}") from exc

    if not organizations:
        raise CatalogError("Справочник организаций пуст")
    for organization in organizations:
        if not organization.name or not organization.facilities:
            raise CatalogError("У организации должны быть название и хотя бы одно ОПО")
        for facility in organization.facilities:
            if not facility.name or not facility.registration_number:
                raise CatalogError("У ОПО должны быть название и регистрационный номер")
    return organizations
