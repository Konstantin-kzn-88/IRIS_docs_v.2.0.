import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class HazardousFacility:
    """ОПО в исходной структуре organization.json."""

    data: dict[str, Any]

    @property
    def name(self) -> str:
        return str(self.data.get("name", "")).strip()

    @property
    def registration_number(self) -> str:
        return str(self.data.get("reg_number", "")).strip()

    @property
    def site_id(self) -> str:
        return str(self.data.get("site_id", "")).strip()

    def snapshot(self) -> dict[str, Any]:
        return copy.deepcopy(self.data)


@dataclass(frozen=True)
class Organization:
    """Организация вместе со всеми разделами исходного JSON."""

    data: dict[str, Any]
    facilities: tuple[HazardousFacility, ...]

    @property
    def name(self) -> str:
        organization = self.data.get("organization", {})
        return str(organization.get("short_name", "")).strip()

    @property
    def full_name(self) -> str:
        organization = self.data.get("organization", {})
        return str(organization.get("full_name", "")).strip()

    def snapshot(self) -> dict[str, Any]:
        """Вернуть организацию без списка ОПО; выбранный ОПО хранится отдельно."""
        result = copy.deepcopy(self.data)
        result.pop("sites", None)
        return result


def _organization_from_dict(item: dict[str, Any]) -> Organization:
    sites = item.get("sites")
    if not isinstance(sites, list):
        raise CatalogError("Поле sites должно быть списком ОПО")
    return Organization(
        data=copy.deepcopy(item),
        facilities=tuple(
            HazardousFacility(copy.deepcopy(site))
            for site in sites
            if isinstance(site, dict)
        ),
    )


def _validate(organizations: tuple[Organization, ...]) -> None:
    if not organizations:
        raise CatalogError("Справочник организаций пуст")

    for organization in organizations:
        if not organization.name:
            raise CatalogError("Не заполнено organization.short_name")
        if not organization.facilities:
            raise CatalogError(
                f"У организации {organization.name} должен быть хотя бы один ОПО"
            )

        for facility in organization.facilities:
            if not facility.site_id:
                raise CatalogError(f"У ОПО {facility.name or 'без названия'} нет site_id")
            if not facility.name:
                raise CatalogError("У ОПО не заполнено поле name")
            if not facility.registration_number:
                raise CatalogError(f"У ОПО {facility.name} не заполнено поле reg_number")

            sanitary_zone = facility.data.get("sanitary_protection_zone_m", 0)
            personnel = facility.data.get("personnel", {})
            try:
                if float(sanitary_zone) < 0:
                    raise CatalogError("Размер СЗЗ не может быть отрицательным")
                if int(personnel.get("employees_count", 0)) < 0:
                    raise CatalogError("Численность работников не может быть отрицательной")
                if int(personnel.get("employees_other_opo_count", 0)) < 0:
                    raise CatalogError(
                        "Численность людей на соседних ОПО не может быть отрицательной"
                    )
            except (TypeError, ValueError, AttributeError) as exc:
                raise CatalogError(
                    f"Некорректные числовые данные у ОПО {facility.name}"
                ) from exc


def load_organizations(path: Path | str | None = None) -> tuple[Organization, ...]:
    if path is not None:
        catalog_path = Path(path)
    else:
        local_catalog = Path.cwd() / "organization.json"
        catalog_path = (
            local_catalog
            if local_catalog.is_file()
            else Path(__file__).parent / "data" / "organization.json"
        )

    try:
        raw = json.loads(catalog_path.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise CatalogError("Корневой элемент organization.json должен быть списком")
        organizations = tuple(
            _organization_from_dict(item) for item in raw if isinstance(item, dict)
        )
        _validate(organizations)
    except CatalogError:
        raise
    except (OSError, json.JSONDecodeError, TypeError, KeyError) as exc:
        raise CatalogError(f"Не удалось прочитать справочник: {catalog_path}") from exc

    return organizations
