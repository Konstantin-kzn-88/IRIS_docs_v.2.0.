import json
from dataclasses import asdict, dataclass
from pathlib import Path


class CatalogError(Exception):
    pass


@dataclass(frozen=True)
class HazardousFacility:
    name: str
    registration_number: str
    address: str = ""
    sanitary_protection_zone_m: float = 0
    description: str = ""
    area_characteristics: str = ""
    employees_count: int = 0
    employees_other_opo_count: int = 0
    emergency_response_plan: str = ""

    def snapshot(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Organization:
    short_name: str
    full_name: str = ""
    ogrn: str = ""
    inn: str = ""
    kpp: str = ""
    legal_address: str = ""
    email: str = ""
    phone: str = ""
    fax: str = ""
    head_position: str = ""
    head_full_name: str = ""
    head_short_name: str = ""
    license_number: str = ""
    industrial_safety_management_system: str = ""
    industrial_control_regulation: str = ""
    accident_investigation_regulation: str = ""
    opo_security: str = ""
    nasf_information: str = ""
    pasf_information: str = ""
    financial_reserve_order: str = ""
    material_reserve_order: str = ""
    facilities: tuple[HazardousFacility, ...] = ()

    @property
    def name(self) -> str:
        return self.short_name

    def snapshot(self) -> dict:
        result = asdict(self)
        result.pop("facilities")
        return result


def _facility_from_dict(item: dict) -> HazardousFacility:
    return HazardousFacility(
        name=str(item["name"]).strip(),
        registration_number=str(item["registration_number"]).strip(),
        address=str(item.get("address", "")).strip(),
        sanitary_protection_zone_m=float(
            item.get("sanitary_protection_zone_m", 0)
        ),
        description=str(item.get("description", "")).strip(),
        area_characteristics=str(item.get("area_characteristics", "")).strip(),
        employees_count=int(item.get("employees_count", 0)),
        employees_other_opo_count=int(item.get("employees_other_opo_count", 0)),
        emergency_response_plan=str(
            item.get("emergency_response_plan", "")
        ).strip(),
    )


def _organization_from_dict(item: dict) -> Organization:
    short_name = str(item.get("short_name") or item.get("name") or "").strip()
    return Organization(
        short_name=short_name,
        full_name=str(item.get("full_name") or short_name).strip(),
        ogrn=str(item.get("ogrn", "")).strip(),
        inn=str(item.get("inn", "")).strip(),
        kpp=str(item.get("kpp", "")).strip(),
        legal_address=str(item.get("legal_address", "")).strip(),
        email=str(item.get("email", "")).strip(),
        phone=str(item.get("phone", "")).strip(),
        fax=str(item.get("fax", "")).strip(),
        head_position=str(item.get("head_position", "")).strip(),
        head_full_name=str(item.get("head_full_name", "")).strip(),
        head_short_name=str(item.get("head_short_name", "")).strip(),
        license_number=str(item.get("license_number", "")).strip(),
        industrial_safety_management_system=str(
            item.get("industrial_safety_management_system", "")
        ).strip(),
        industrial_control_regulation=str(
            item.get("industrial_control_regulation", "")
        ).strip(),
        accident_investigation_regulation=str(
            item.get("accident_investigation_regulation", "")
        ).strip(),
        opo_security=str(item.get("opo_security", "")).strip(),
        nasf_information=str(item.get("nasf_information", "")).strip(),
        pasf_information=str(item.get("pasf_information", "")).strip(),
        financial_reserve_order=str(
            item.get("financial_reserve_order", "")
        ).strip(),
        material_reserve_order=str(
            item.get("material_reserve_order", "")
        ).strip(),
        facilities=tuple(_facility_from_dict(value) for value in item["facilities"]),
    )


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
        organizations = tuple(_organization_from_dict(item) for item in items)
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        AttributeError,
    ) as exc:
        raise CatalogError(f"Не удалось прочитать справочник: {catalog_path}") from exc

    if not organizations:
        raise CatalogError("Справочник организаций пуст")
    for organization in organizations:
        if not organization.name or not organization.facilities:
            raise CatalogError("У организации должны быть название и хотя бы одно ОПО")
        for facility in organization.facilities:
            if not facility.name or not facility.registration_number:
                raise CatalogError("У ОПО должны быть название и регистрационный номер")
            if facility.sanitary_protection_zone_m < 0:
                raise CatalogError("Размер СЗЗ не может быть отрицательным")
            if facility.employees_count < 0 or facility.employees_other_opo_count < 0:
                raise CatalogError("Численность людей не может быть отрицательной")
    return organizations
