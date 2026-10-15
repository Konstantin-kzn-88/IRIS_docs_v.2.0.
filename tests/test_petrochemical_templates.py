import re
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

import pytest

from iris_v2.template_catalog import TemplateCatalogService


TEMPLATES_ROOT = Path(__file__).parents[1] / "templates"
PROFILE = "ДПБ_нефтехимия"
NAMES = (
    "DPB_template_neftekhimiya.docx",
    "IFL_template_neftekhimiya.docx",
    "RPZ_template_neftekhimiya.docx",
)
NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
W = f"{{{NS['w']}}}"


def test_catalog_selects_three_petrochemical_templates(tmp_path: Path) -> None:
    (tmp_path / "project.json").write_text('{"format_version": 1}', encoding="utf-8")

    result = TemplateCatalogService(TEMPLATES_ROOT).select(tmp_path, PROFILE)

    assert tuple(item.name for item in result.documents) == NAMES
    for item in result.documents:
        assert item.path.read_bytes() == (TEMPLATES_ROOT / PROFILE / item.name).read_bytes()


@pytest.mark.parametrize("name", NAMES)
def test_petrochemical_templates_have_no_oil_production_content_or_broken_refs(
    name: str,
) -> None:
    path = TEMPLATES_ROOT / PROFILE / name
    with ZipFile(path) as archive:
        for part in archive.namelist():
            if not part.endswith(".xml"):
                continue
            root = ElementTree.fromstring(archive.read(part))
            text = "".join(root.itertext())
            assert not re.search(
                r"нефтегазодобы\w*|нефтедобы\w*|промыслов\w*|скважин\w*|буров\w*"
                r"|ДНС|УПСВ|ЦППН|месторожд\w*|утечек нефти|свойств нефти",
                text,
                re.IGNORECASE,
            ), (name, part)
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        bookmarks = {
            item.get(W + "name") for item in root.iter(W + "bookmarkStart")
        }
        instructions = [item.text or "" for item in root.iter(W + "instrText")]
        instructions.extend(item.get(W + "instr", "") for item in root.iter(W + "fldSimple"))
        for instruction in instructions:
            reference = re.search(r"\b(?:REF|PAGEREF)\s+([^\s\\]+)", instruction)
            if reference:
                assert reference.group(1) in bookmarks, (name, reference.group(1))
        assert not list(root.iter(W + "ins"))
        assert not list(root.iter(W + "del"))


def test_rpz_discards_production_statistics_and_uses_petrochemical_comparison() -> None:
    with ZipFile(TEMPLATES_ROOT / PROFILE / NAMES[2]) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
        text = "".join(root.itertext())
        assert "{{PETROCHEMICAL_BACKGROUND_RISK_COMPARISON}}" in text
        assert "{{NGK_BACKGROUND_RISK_COMPARISON}}" not in text
        assert "Смертельный травматизм снижен" not in text
        media = [name for name in archive.namelist() if name.startswith("word/media/")]
        assert len(media) == 2  # Only the supplied weather charts remain.
