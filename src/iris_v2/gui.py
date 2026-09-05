import sys
import copy
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from iris_v2.service import CreateProjectData, ProjectError, ProjectInfo, ProjectService
from iris_v2.catalog import CatalogError, Organization, load_organizations
from iris_v2.developer_catalog import (
    Developer,
    DeveloperCatalogError,
    load_developers,
)
from iris_v2.equipment import EXCEL_FILE_NAME, EquipmentError, EquipmentService
from iris_v2.evaporation_calculation import (
    EvaporationCalculationError,
    EvaporationCalculationResult,
    EvaporationCalculationService,
)
from iris_v2.hazard_factor_calculation import (
    HazardFactorCalculationError,
    HazardFactorCalculationResult,
    HazardFactorCalculationService,
)
from iris_v2.pool_fire_calculation import (
    PoolFireCalculationError,
    PoolFireCalculationResult,
    PoolFireCalculationService,
)
from iris_v2.amount_calculation import (
    AmountCalculationError,
    AmountCalculationResult,
    AmountCalculationService,
)
from iris_v2.calculation_cases import (
    CalculationCasesError,
    CalculationCasesResult,
    CalculationCasesService,
)
from iris_v2.calculation_config import (
    CalculationConfigError,
    CalculationConfigService,
)
from iris_v2.frequency_calculation import (
    FrequencyCalculationError,
    FrequencyCalculationResult,
    FrequencyCalculationService,
)
from iris_v2.release_calculation import (
    ReleaseCalculationError,
    ReleaseCalculationResult,
    ReleaseCalculationService,
)
from iris_v2.spill_calculation import (
    SpillCalculationError,
    SpillCalculationResult,
    SpillCalculationService,
)
from iris_v2.project_common import ProjectCommonError, ProjectCommonService
from iris_v2.project_validation import ProjectValidationService, ValidationReport
from iris_v2.substances import (
    KIND_NAMES,
    Substance,
    SubstanceError,
    SubstanceService,
    substance_fingerprint,
)
from iris_v2.typical_scenarios import (
    TypicalScenarioCatalog,
    TypicalScenarioError,
    TypicalScenarioService,
)


class ProjectCommonDialog(QDialog):
    EXECUTOR_FIELDS = (
        ("name", "Наименование разработчика"),
        ("address", "Адрес"),
        ("sro", "СРО"),
        ("inn", "ИНН"),
        ("ogrn", "ОГРН"),
        ("tel", "Телефон"),
        ("head_position", "Должность руководителя"),
        ("head_full_name", "Ф.И.О. руководителя"),
        ("specialist_info", "Сведения о специалисте"),
        ("email", "Электронная почта"),
        ("website", "Сайт"),
    )

    def __init__(
        self,
        project_directory: Path,
        project: ProjectInfo,
        developers: tuple[Developer, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_directory = project_directory
        self.service = ProjectCommonService()
        self.data = self.service.load(
            project_directory, project.name, project.code
        )
        self.setWindowTitle("Данные проекта")
        self.resize(760, 620)

        self.year_edit = QSpinBox()
        self.year_edit.setRange(2000, 2100)
        self.year_edit.setValue(int(self.data["year"]))
        self.project_name_edit = QLineEdit(str(self.data["project_name"]))
        self.project_code_edit = QLineEdit(str(self.data["project_code"]))
        self.dpb_code_edit = QLineEdit(str(self.data["dpb_code"]))
        self.gochs_code_edit = QLineEdit(str(self.data["gochs_code"]))
        self.pb_code_edit = QLineEdit(str(self.data["pb_code"]))

        project_form = QFormLayout()
        project_form.addRow("Год:", self.year_edit)
        project_form.addRow("Название проекта:", self.project_name_edit)
        project_form.addRow("Шифр проекта:", self.project_code_edit)
        project_form.addRow("Шифр ДПБ:", self.dpb_code_edit)
        project_form.addRow("Шифр ГОЧС:", self.gochs_code_edit)
        project_form.addRow("Шифр ПБ:", self.pb_code_edit)
        project_page = QWidget()
        project_page.setLayout(project_form)

        executor = self.data["executor"]
        self.executor_edits: dict[str, QLineEdit | QPlainTextEdit] = {}
        executor_form = QFormLayout()
        self.developer_combo = QComboBox()
        self.developer_combo.addItem("— Ввести вручную —", None)
        for developer in developers:
            self.developer_combo.addItem(developer.name, developer)
        executor_form.addRow("Постоянный разработчик:", self.developer_combo)
        for key, label in self.EXECUTOR_FIELDS:
            if key in {"address", "specialist_info"}:
                edit = QPlainTextEdit(str(executor.get(key, "")))
                edit.setMaximumHeight(100)
            else:
                edit = QLineEdit(str(executor.get(key, "")))
            self.executor_edits[key] = edit
            executor_form.addRow(f"{label}:", edit)
        self.developer_combo.currentIndexChanged.connect(self._fill_executor)
        for index, developer in enumerate(developers, start=1):
            if developer.name == str(executor.get("name", "")).strip():
                self.developer_combo.blockSignals(True)
                self.developer_combo.setCurrentIndex(index)
                self.developer_combo.blockSignals(False)
                break
        executor_page = QWidget()
        executor_page.setLayout(executor_form)

        tabs = QTabWidget()
        tabs.addTab(project_page, "Проект и шифры")
        tabs.addTab(executor_page, "Разработчик")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(
            self._save
        )
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    def _fill_executor(self) -> None:
        developer = self.developer_combo.currentData()
        if developer is None:
            return
        values = developer.snapshot()
        for key, edit in self.executor_edits.items():
            value = str(values.get(key, ""))
            if isinstance(edit, QPlainTextEdit):
                edit.setPlainText(value)
            else:
                edit.setText(value)

    def _save(self) -> None:
        data = copy.deepcopy(self.data)
        data.update(
            {
                "year": self.year_edit.value(),
                "project_name": self.project_name_edit.text().strip(),
                "project_code": self.project_code_edit.text().strip(),
                "dpb_code": self.dpb_code_edit.text().strip(),
                "gochs_code": self.gochs_code_edit.text().strip(),
                "pb_code": self.pb_code_edit.text().strip(),
            }
        )
        executor = dict(data.get("executor", {}))
        for key, edit in self.executor_edits.items():
            value = edit.toPlainText() if isinstance(edit, QPlainTextEdit) else edit.text()
            executor[key] = value.strip()
        data["executor"] = executor
        try:
            self.service.save(self.project_directory, data)
        except ProjectCommonError as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return
        self.accept()


class CalculationConfigDialog(QDialog):
    def __init__(
        self, project_directory: Path, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.project_directory = project_directory
        self.service = CalculationConfigService()
        self.data = self.service.load(project_directory)
        self.setWindowTitle("Настройки расчёта")
        self.resize(720, 480)

        self.edits: dict[str, QDoubleSpinBox] = {}
        fractions_form = QFormLayout()
        for key, label in (
            ("partial_release_fraction", "Доля частичной разгерметизации:"),
            ("flammable_cloud_fraction", "Доля вещества в облаке:"),
            ("bleve_fraction", "Доля вещества в огненном шаре:"),
            ("partial_spill_fraction", "Доля частичного пролива:"),
        ):
            edit = self._spin(self.data[key], 1.0, 0.005)
            self.edits[key] = edit
            fractions_form.addRow(label, edit)
        fractions_page = QWidget()
        fractions_page.setLayout(fractions_form)

        model_form = QFormLayout()
        for key, label, maximum in (
            ("wind_speed_m_s", "Скорость ветра, м/с:", 100.0),
            (
                "evaporation_coefficient",
                "Коэффициент испарения η:",
                100.0,
            ),
            (
                "liquid_leak_hole_diameter_mm",
                "Отверстие истечения жидкости, мм:",
                10000.0,
            ),
            (
                "gas_leak_hole_diameter_mm",
                "Отверстие истечения газа, мм:",
                10000.0,
            ),
            ("damage_scale", "Масштаб ущерба:", 1000000.0),
        ):
            edit = self._spin(self.data[key], maximum, 0.1)
            self.edits[key] = edit
            model_form.addRow(label, edit)
        model_page = QWidget()
        model_page.setLayout(model_form)

        multipliers = self.data["frequency_multipliers"]
        frequency_form = QFormLayout()
        frequency_form.addRow("Стандартный расчёт:", QLabel("1,0"))
        self.without_compensation_edit = self._spin(
            multipliers["without_compensation"], 10.0, 0.05
        )
        self.with_compensation_edit = self._spin(
            multipliers["with_compensation"], 10.0, 0.05
        )
        frequency_form.addRow(
            "Расчёт без компенсирующих мероприятий:",
            self.without_compensation_edit,
        )
        frequency_form.addRow(
            "Расчёт с компенсирующими мероприятиями:",
            self.with_compensation_edit,
        )
        example = QLabel(
            "Множитель определяется отдельно для каждой строки по окончанию "
            "hazard_component:\n\n"
            "Участок трубопроводов — стандартный расчёт (×1,0)\n"
            "Участок трубопроводов (без КМ) — расчёт без КМ\n"
            "Участок трубопроводов (с КМ) — расчёт с КМ"
        )
        example.setWordWrap(True)
        frequency_layout = QVBoxLayout()
        frequency_layout.addLayout(frequency_form)
        frequency_layout.addWidget(example)
        frequency_layout.addStretch()
        frequency_page = QWidget()
        frequency_page.setLayout(frequency_layout)

        tabs = QTabWidget()
        tabs.addTab(fractions_page, "Масса и пролив")
        tabs.addTab(model_page, "Истечение и ущерб")
        tabs.addTab(frequency_page, "Частота и КМ")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(
            self._save
        )
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(tabs)
        layout.addWidget(buttons)

    @staticmethod
    def _spin(value: float, maximum: float, step: float) -> QDoubleSpinBox:
        edit = QDoubleSpinBox()
        edit.setDecimals(3)
        edit.setRange(0.001, maximum)
        edit.setSingleStep(step)
        edit.setValue(float(value))
        return edit

    def _save(self) -> None:
        data = copy.deepcopy(self.data)
        for key, edit in self.edits.items():
            data[key] = edit.value()
        data["frequency_multipliers"] = {
            "standard": 1.0,
            "without_compensation": self.without_compensation_edit.value(),
            "with_compensation": self.with_compensation_edit.value(),
        }
        try:
            self.service.save(self.project_directory, data)
        except CalculationConfigError as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return
        self.accept()


class TypicalScenariosDialog(QDialog):
    def __init__(
        self,
        catalog: TypicalScenarioCatalog,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle("Типовые сценарии аварий")
        self.resize(1180, 680)

        self.equipment_combo = QComboBox()
        for code, name in sorted(catalog.equipment_types.items()):
            self.equipment_combo.addItem(f"{code} — {name}", code)
        self.kind_combo = QComboBox()
        for code, name in sorted(catalog.kinds.items()):
            self.kind_combo.addItem(f"{code} — {name}", code)

        filters = QFormLayout()
        filters.addRow("Тип оборудования:", self.equipment_combo)
        filters.addRow("Вид опасного вещества:", self.kind_combo)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            [
                "№",
                "Сценарий",
                "Базовая частота",
                "Вероятность",
                "Частота сценария",
                "Расчёт",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(0, 50)
        self.table.setColumnWidth(2, 125)
        self.table.setColumnWidth(3, 100)
        self.table.setColumnWidth(4, 135)
        self.table.setColumnWidth(5, 180)

        source_label = QLabel(f"Источник: {catalog.source_path}")
        source_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(filters)
        layout.addWidget(self.status_label)
        layout.addWidget(self.table)
        layout.addWidget(source_label)
        layout.addWidget(close_buttons)

        self.equipment_combo.currentIndexChanged.connect(self._refresh)
        self.kind_combo.currentIndexChanged.connect(self._refresh)
        self._refresh()

    def _refresh(self) -> None:
        equipment_type = self.equipment_combo.currentData()
        kind = self.kind_combo.currentData()
        scenarios = self.catalog.scenarios_for(equipment_type, kind)
        reason = self.catalog.forbidden_reason(equipment_type, kind)
        self.table.setRowCount(len(scenarios))
        if reason is not None:
            self.status_label.setText(f"Сочетание запрещено: {reason}")
            self.status_label.setStyleSheet("color: #B42318; font-weight: bold;")
        else:
            self.status_label.setText(f"Найдено сценариев: {len(scenarios)}")
            self.status_label.setStyleSheet("color: #16803A; font-weight: bold;")
        for row, scenario in enumerate(scenarios):
            values = (
                str(scenario.line),
                scenario.text,
                f"{scenario.base_frequency:.3e}",
                f"{scenario.event_probability:.6g}",
                f"{scenario.frequency:.3e}",
                f"{scenario.calc_code} — "
                f"{self.catalog.calculation_types[scenario.calc_code]}",
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                self.table.setItem(row, column, item)


class CalculationCasesDialog(QDialog):
    def __init__(
        self,
        result: CalculationCasesResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Расчётные сценарии проекта")
        self.resize(1280, 720)

        status = QLabel(
            f"Оборудование: {result.equipment_count}. "
            f"Сформировано сценариев: {result.case_count}."
        )
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.cases), 8)
        self.table.setHorizontalHeaderLabels(
            [
                "Код",
                "Оборудование",
                "Вещество",
                "Составляющая ОПО",
                "Режим",
                "Расчёт",
                "Типовая частота",
                "Сценарий",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            7, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(0, 60)
        self.table.setColumnWidth(1, 210)
        self.table.setColumnWidth(2, 140)
        self.table.setColumnWidth(3, 190)
        self.table.setColumnWidth(4, 85)
        self.table.setColumnWidth(5, 150)
        self.table.setColumnWidth(6, 120)

        for row, case in enumerate(result.cases):
            values = (
                case["scenario_code"],
                case["equipment_name"],
                case["substance_name"],
                case["hazard_component"],
                case["frequency_mode_name"],
                case["calc_name"],
                f'{case["unit_scenario_frequency"]:.3e}',
                case["scenario_text"],
            )
            for column, value in enumerate(values):
                text = str(value)
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                self.table.setItem(row, column, item)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class AmountCalculationDialog(QDialog):
    def __init__(
        self,
        result: AmountCalculationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Количество опасного вещества")
        self.resize(1180, 680)

        status = QLabel(f"Рассчитано строк оборудования: {result.equipment_count}.")
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.results), 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Оборудование",
                "Вещество",
                "Тип",
                "Объём, м³",
                "Dвн, мм",
                "Жидкость, т",
                "Газ, т",
                "Всего, т",
                "Формула",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            8, QHeaderView.ResizeMode.Stretch
        )
        for column, width in enumerate((210, 150, 165, 90, 80, 90, 80, 90)):
            self.table.setColumnWidth(column, width)

        for row, item_data in enumerate(result.results):
            internal_diameter = item_data["internal_diameter_mm"]
            values = (
                item_data["equipment_name"],
                item_data["substance_name"],
                item_data["equipment_type_name"],
                f'{item_data["volume_m3"]:.6g}',
                "" if internal_diameter is None else f"{internal_diameter:.6g}",
                f'{item_data["liquid_mass_t"]:.6g}',
                f'{item_data["gas_mass_t"]:.6g}',
                f'{item_data["amount_t"]:.6g}',
                item_data["formula"],
            )
            for column, value in enumerate(values):
                text = str(value)
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.table.setItem(row, column, cell)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class FrequencyCalculationDialog(QDialog):
    def __init__(
        self,
        result: FrequencyCalculationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Расчёт частот аварий")
        self.resize(1280, 720)

        status = QLabel(
            f"Рассчитано сценариев: {result.case_count}. "
            f"Суммарная частота: {result.total_frequency:.3e} 1/год."
        )
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.results), 10)
        self.table.setHorizontalHeaderLabels(
            [
                "Код",
                "Оборудование",
                "Составляющая ОПО",
                "Режим",
                "Базовая частота",
                "Вероятность",
                "Основа",
                "КМ",
                "Итоговая частота",
                "Сценарий",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            9, QHeaderView.ResizeMode.Stretch
        )
        for column, width in enumerate(
            (60, 190, 180, 80, 115, 90, 85, 60, 125)
        ):
            self.table.setColumnWidth(column, width)

        for row, item_data in enumerate(result.results):
            values = (
                item_data["scenario_code"],
                item_data["equipment_name"],
                item_data["hazard_component"],
                item_data["frequency_mode_name"],
                f'{item_data["base_frequency"]:.3e}',
                f'{item_data["accident_event_probability"]:.6g}',
                f'{item_data["frequency_basis"]:g} '
                f'{item_data["frequency_basis_unit"]}',
                f'{item_data["frequency_multiplier"]:g}',
                f'{item_data["scenario_frequency"]:.3e}',
                item_data["scenario_text"],
            )
            for column, value in enumerate(values):
                text = str(value)
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.table.setItem(row, column, cell)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class ReleaseCalculationDialog(QDialog):
    def __init__(
        self,
        result: ReleaseCalculationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Масса вещества в аварии")
        self.resize(1280, 720)

        status = QLabel(f"Рассчитано сценариев: {result.case_count}.")
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.results), 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Код",
                "Оборудование",
                "Вещество",
                "Строка",
                "Режим выброса",
                "В оборудовании, т",
                "Расход, кг/с",
                "В аварии, т",
                "Сценарий",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            8, QHeaderView.ResizeMode.Stretch
        )
        for column, width in enumerate(
            (60, 190, 140, 60, 230, 110, 105, 105)
        ):
            self.table.setColumnWidth(column, width)

        for row, item_data in enumerate(result.results):
            values = (
                item_data["scenario_code"],
                item_data["equipment_name"],
                item_data["substance_name"],
                item_data["typical_scenario_line"],
                item_data["release_mode_name"],
                f'{item_data["amount_t"]:.6g}',
                f'{item_data["flow_kg_s"]:.6g}',
                f'{item_data["ov_in_accident_t"]:.6g}',
                item_data["scenario_text"],
            )
            for column, value in enumerate(values):
                text = str(value)
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.table.setItem(row, column, cell)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class SpillCalculationDialog(QDialog):
    def __init__(
        self,
        result: SpillCalculationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Площадь пролива")
        self.resize(1280, 720)

        status = QLabel(
            f"Сценариев: {result.case_count}. "
            f"Пролив рассчитан для: {result.spill_count}."
        )
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.results), 9)
        self.table.setHorizontalHeaderLabels(
            [
                "Код",
                "Оборудование",
                "Вещество",
                "Масса, т",
                "Пролив",
                "Источник площади",
                "Коэффициент",
                "Площадь, м²",
                "Сценарий",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            8, QHeaderView.ResizeMode.Stretch
        )
        for column, width in enumerate(
            (60, 190, 140, 90, 75, 190, 100, 105)
        ):
            self.table.setColumnWidth(column, width)

        for row, item_data in enumerate(result.results):
            area = item_data["spill_area_m2"]
            coefficient = item_data["spill_coefficient"]
            values = (
                item_data["scenario_code"],
                item_data["equipment_name"],
                item_data["substance_name"],
                f'{item_data["ov_in_accident_t"]:.6g}',
                "Да" if item_data["spill_applicable"] else "Нет",
                item_data["spill_source_name"],
                "" if coefficient is None else f"{coefficient:g}",
                "" if area is None else f"{area:.6g}",
                item_data["scenario_text"],
            )
            for column, value in enumerate(values):
                text = str(value)
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.table.setItem(row, column, cell)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class EvaporationCalculationDialog(QDialog):
    def __init__(
        self,
        result: EvaporationCalculationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Испарившаяся масса")
        self.resize(1280, 720)

        status = QLabel(
            f"Сценариев: {result.case_count}. "
            f"Испарение рассчитано для: {result.evaporation_count}."
        )
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.results), 10)
        self.table.setHorizontalHeaderLabels(
            [
                "Код",
                "Оборудование",
                "Вещество",
                "Статус",
                "Pнас, кПа",
                "W, кг/(м²·с)",
                "Площадь, м²",
                "Время, с",
                "Испарилось, т",
                "Сценарий",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            9, QHeaderView.ResizeMode.Stretch
        )
        for column, width in enumerate(
            (60, 180, 135, 180, 90, 110, 95, 80, 100)
        ):
            self.table.setColumnWidth(column, width)

        for row, item_data in enumerate(result.results):
            pressure = item_data["saturated_vapor_pressure_kpa"]
            intensity = item_data["evaporation_intensity_kg_m2_s"]
            area = item_data["spill_area_m2"]
            duration = item_data["evaporation_time_s"]
            mass = item_data["evaporated_mass_t"]
            values = (
                item_data["scenario_code"],
                item_data["equipment_name"],
                item_data["substance_name"],
                item_data["evaporation_status_name"],
                "" if pressure is None else f"{pressure:.6g}",
                "" if intensity is None else f"{intensity:.6g}",
                "" if area is None else f"{area:.6g}",
                "" if duration is None else f"{duration:g}",
                "" if mass is None else f"{mass:.6g}",
                item_data["scenario_text"],
            )
            for column, value in enumerate(values):
                text = str(value)
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.table.setItem(row, column, cell)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class HazardFactorCalculationDialog(QDialog):
    def __init__(
        self,
        result: HazardFactorCalculationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Масса вещества в поражающем факторе")
        self.resize(1320, 720)

        status = QLabel(
            f"Сценариев: {result.case_count}. "
            f"С поражающим фактором: {result.active_count}."
        )
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.results), 10)
        self.table.setHorizontalHeaderLabels(
            [
                "Код",
                "Оборудование",
                "Вещество",
                "Расчёт",
                "Источник массы",
                "В аварии, т",
                "Испарилось, т",
                "В факторе, т",
                "Расход, кг/с",
                "Сценарий",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            9, QHeaderView.ResizeMode.Stretch
        )
        for column, width in enumerate(
            (60, 175, 135, 135, 190, 90, 95, 95, 100)
        ):
            self.table.setColumnWidth(column, width)

        for row, item_data in enumerate(result.results):
            evaporated = item_data["evaporated_mass_t"]
            factor_flow = item_data["hazard_factor_flow_kg_s"]
            values = (
                item_data["scenario_code"],
                item_data["equipment_name"],
                item_data["substance_name"],
                item_data["calc_name"],
                item_data["hazard_factor_source_name"],
                f'{item_data["ov_in_accident_t"]:.6g}',
                "" if evaporated is None else f"{evaporated:.6g}",
                f'{item_data["ov_in_hazard_factor_t"]:.6g}',
                "" if factor_flow is None else f"{factor_flow:.6g}",
                item_data["scenario_text"],
            )
            for column, value in enumerate(values):
                text = str(value)
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.table.setItem(row, column, cell)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class PoolFireCalculationDialog(QDialog):
    def __init__(
        self,
        result: PoolFireCalculationResult,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Пожар пролива")
        self.resize(1320, 720)

        status = QLabel(
            f"Сценариев: {result.case_count}. "
            f"Пожаров пролива рассчитано: {result.pool_fire_count}."
        )
        status.setStyleSheet("color: #16803A; font-weight: bold;")

        self.table = QTableWidget(len(result.results), 11)
        self.table.setHorizontalHeaderLabels(
            [
                "Код",
                "Оборудование",
                "Вещество",
                "Статус",
                "Площадь, м²",
                "mсг, кг/(м²·с)",
                "Ветер, м/с",
                "10,5 кВт/м²",
                "7,0 кВт/м²",
                "4,2 кВт/м²",
                "1,4 кВт/м²",
            ]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed
        )
        self.table.verticalHeader().setDefaultSectionSize(30)
        self.table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        for column, width in enumerate(
            (60, 180, 135, 190, 95, 115, 85, 100, 100, 100, 100)
        ):
            if column != 3:
                self.table.setColumnWidth(column, width)

        for row, item_data in enumerate(result.results):
            applicable = item_data["pool_fire_applicable"]

            def formatted(key: str) -> str:
                value = item_data[key]
                return "" if value is None else f"{value:.6g}"

            values = (
                item_data["scenario_code"],
                item_data["equipment_name"],
                item_data["substance_name"],
                item_data["pool_fire_status_name"],
                formatted("pool_fire_spill_area_m2"),
                formatted("pool_fire_burning_rate_kg_m2_s"),
                formatted("pool_fire_wind_speed_m_s") if applicable else "",
                formatted("q_10_5_m"),
                formatted("q_7_0_m"),
                formatted("q_4_2_m"),
                formatted("q_1_4_m"),
            )
            for column, value in enumerate(values):
                text = str(value)
                cell = QTableWidgetItem(text)
                cell.setToolTip(text)
                self.table.setItem(row, column, cell)

        path_label = QLabel(f"Файл: {result.path}")
        path_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(status)
        layout.addWidget(self.table)
        layout.addWidget(path_label)
        layout.addWidget(close_buttons)


class SubstanceDialog(QDialog):
    def __init__(
        self,
        project_directory: Path,
        substances: tuple[Substance, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.project_directory = project_directory
        self.substances = substances
        self.service = SubstanceService()
        selected_fingerprints = {
            substance_fingerprint(item)
            for item in self.service.load_project(project_directory)
        }
        self.setWindowTitle("Вещества проекта")
        self.resize(980, 650)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText("Поиск по группе, названию или виду вещества")
        self.filter_edit.textChanged.connect(self._apply_filter)

        self.table = QTableWidget(len(substances), 5)
        self.table.setHorizontalHeaderLabels(
            ["Выбрать", "Группа", "Исходный ID", "Название", "Вид вещества"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        remaining = set(selected_fingerprints)
        for row, substance in enumerate(substances):
            selected = substance.fingerprint in remaining
            if selected:
                remaining.remove(substance.fingerprint)
            check_item = QTableWidgetItem()
            check_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable
            )
            check_item.setCheckState(
                Qt.CheckState.Checked if selected else Qt.CheckState.Unchecked
            )
            self.table.setItem(row, 0, check_item)
            self.table.setItem(row, 1, QTableWidgetItem(substance.group))
            self.table.setItem(row, 2, QTableWidgetItem(str(substance.source_id)))
            self.table.setItem(row, 3, QTableWidgetItem(substance.name))
            self.table.setItem(row, 4, QTableWidgetItem(KIND_NAMES[substance.kind]))

        select_all_button = QPushButton("Выбрать все")
        select_all_button.clicked.connect(lambda: self._set_visible_checked(True))
        clear_button = QPushButton("Снять выделение")
        clear_button.clicked.connect(lambda: self._set_visible_checked(False))
        selection_layout = QHBoxLayout()
        selection_layout.addWidget(select_all_button)
        selection_layout.addWidget(clear_button)
        selection_layout.addStretch()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Сохранить")
        buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(self.filter_edit)
        layout.addLayout(selection_layout)
        layout.addWidget(self.table)
        layout.addWidget(buttons)

    def _apply_filter(self, text: str) -> None:
        search = text.strip().lower()
        for row in range(self.table.rowCount()):
            row_text = " ".join(
                self.table.item(row, column).text()
                for column in range(1, self.table.columnCount())
            ).lower()
            self.table.setRowHidden(row, search not in row_text)

    def _set_visible_checked(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for row in range(self.table.rowCount()):
            if not self.table.isRowHidden(row):
                self.table.item(row, 0).setCheckState(state)

    def _save(self) -> None:
        selected = [
            substance
            for row, substance in enumerate(self.substances)
            if self.table.item(row, 0).checkState() == Qt.CheckState.Checked
        ]
        try:
            self.service.save_project(self.project_directory, selected)
        except SubstanceError as exc:
            QMessageBox.critical(self, "Ошибка", str(exc))
            return
        self.accept()


class ProjectValidationDialog(QDialog):
    def __init__(
        self, report: ValidationReport, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.report = report
        self.setWindowTitle("Проверка исходных данных")
        self.resize(900, 440)

        self.table = QTableWidget(len(report.items), 3)
        self.table.setHorizontalHeaderLabels(["Статус", "Раздел", "Результат"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.table.setColumnWidth(0, 90)
        self.table.setColumnWidth(1, 170)

        for row, item in enumerate(report.items):
            color = QColor("#16803A" if item.ok else "#B42318")
            status = QTableWidgetItem("Готово" if item.ok else "Ошибка")
            section = QTableWidgetItem(item.section)
            message = QTableWidgetItem(item.message)
            for cell in (status, section, message):
                cell.setForeground(color)
            self.table.setItem(row, 0, status)
            self.table.setItem(row, 1, section)
            self.table.setItem(row, 2, message)
            self.table.setRowHeight(row, max(32, 20 * (item.message.count("\n") + 1)))

        result_label = QLabel(
            "Проект готов к расчёту"
            if report.ready
            else "Расчёт невозможен: исправьте отмеченные ошибки"
        )
        result_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: "
            + ("#16803A;" if report.ready else "#B42318;")
        )

        self.open_button = QPushButton("Открыть файл или папку")
        self.open_button.setEnabled(False)
        self.open_button.clicked.connect(self._open_selected)
        self.table.itemSelectionChanged.connect(self._update_open_button)

        close_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_buttons.button(QDialogButtonBox.StandardButton.Close).setText("Закрыть")
        close_buttons.rejected.connect(self.reject)

        button_layout = QHBoxLayout()
        button_layout.addWidget(self.open_button)
        button_layout.addStretch()
        button_layout.addWidget(close_buttons)

        layout = QVBoxLayout(self)
        layout.addWidget(result_label)
        layout.addWidget(self.table)
        layout.addLayout(button_layout)

    def _selected_path(self) -> Path | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        return self.report.items[row].path

    def _update_open_button(self) -> None:
        path = self._selected_path()
        self.open_button.setEnabled(path is not None and path.parent.exists())

    def _open_selected(self) -> None:
        path = self._selected_path()
        if path is None:
            return
        target = path if path.exists() else path.parent
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target.resolve())))


class CreateProjectDialog(QDialog):
    def __init__(
        self,
        organizations: tuple[Organization, ...],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Создание проекта")
        self.setMinimumWidth(600)

        self.path_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit()
        self.organization_combo = QComboBox()
        self.opo_combo = QComboBox()
        self.registration_edit = QLineEdit()
        self.registration_edit.setReadOnly(True)

        for organization in organizations:
            self.organization_combo.addItem(organization.name, organization)
        self.organization_combo.currentIndexChanged.connect(self._update_facilities)
        self.opo_combo.currentIndexChanged.connect(self._update_registration_number)
        self._update_facilities()

        browse_button = QPushButton("Выбрать…")
        browse_button.clicked.connect(self._select_project_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_button)

        form = QFormLayout()
        form.addRow("Папка проекта:", path_layout)
        form.addRow("Название проекта:", self.name_edit)
        form.addRow("Шифр проекта:", self.code_edit)
        form.addRow("Организация:", self.organization_combo)
        form.addRow("Наименование ОПО:", self.opo_combo)
        form.addRow("Регистрационный номер ОПО:", self.registration_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Создать")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _select_project_path(self) -> None:
        parent_directory = QFileDialog.getExistingDirectory(
            self, "Выберите папку для проектов"
        )
        if not parent_directory:
            return
        folder_name = self.code_edit.text().strip() or "Новый проект"
        self.path_edit.setText(str(Path(parent_directory) / folder_name))

    def _update_facilities(self) -> None:
        organization = self.organization_combo.currentData()
        self.opo_combo.clear()
        if organization is not None:
            for facility in organization.facilities:
                self.opo_combo.addItem(facility.name, facility)
        self._update_registration_number()

    def _update_registration_number(self) -> None:
        facility = self.opo_combo.currentData()
        self.registration_edit.setText(
            facility.registration_number if facility is not None else ""
        )

    def project_path(self) -> str:
        return self.path_edit.text().strip()

    def project_data(self) -> CreateProjectData:
        organization = self.organization_combo.currentData()
        facility = self.opo_combo.currentData()
        return CreateProjectData(
            name=self.name_edit.text(),
            code=self.code_edit.text(),
            organization_name=organization.name if organization else "",
            opo_name=facility.name if facility else "",
            opo_registration_number=(
                facility.registration_number if facility else ""
            ),
            organization_snapshot=(
                organization.snapshot() if organization else None
            ),
            opo_snapshot=facility.snapshot() if facility else None,
        )


class MainWindow(QMainWindow):
    def __init__(
        self,
        service: ProjectService | None = None,
        organizations: tuple[Organization, ...] | None = None,
    ) -> None:
        super().__init__()
        self.service = service or ProjectService()
        self.current_project: ProjectInfo | None = None
        self.current_project_directory: Path | None = None
        try:
            self.organizations = organizations or load_organizations()
        except CatalogError as exc:
            self.organizations = ()
            QMessageBox.critical(self, "Ошибка справочника", str(exc))
        try:
            self.developers = load_developers()
        except DeveloperCatalogError as exc:
            self.developers = ()
            QMessageBox.warning(self, "Ошибка справочника разработчиков", str(exc))
        self.setWindowTitle("IRIS v2")
        self.resize(1320, 360)

        title = QLabel("IRIS v2")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size: 24px; font-weight: bold;")

        self.project_label = QLabel("Проект не открыт")
        self.project_label.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.project_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        create_button = QPushButton("Создать проект")
        create_button.setObjectName("create_project_button")
        create_button.clicked.connect(self.create_project)

        open_button = QPushButton("Открыть проект")
        open_button.setObjectName("open_project_button")
        open_button.clicked.connect(self.open_project)

        self.project_common_button = QPushButton("Данные проекта")
        self.project_common_button.setObjectName("project_common_button")
        self.project_common_button.setEnabled(False)
        self.project_common_button.clicked.connect(self.edit_project_common)

        self.substances_button = QPushButton("Вещества")
        self.substances_button.setObjectName("substances_button")
        self.substances_button.setEnabled(False)
        self.substances_button.clicked.connect(self.edit_substances)

        self.equipment_button = QPushButton("Оборудование")
        self.equipment_button.setObjectName("equipment_button")
        self.equipment_button.setEnabled(False)
        self.equipment_button.clicked.connect(self.import_equipment)

        self.amount_button = QPushButton("Количество ОВ")
        self.amount_button.setObjectName("amount_button")
        self.amount_button.setEnabled(False)
        self.amount_button.clicked.connect(self.calculate_amounts)

        self.calculation_config_button = QPushButton("Настройки расчёта")
        self.calculation_config_button.setObjectName("calculation_config_button")
        self.calculation_config_button.setEnabled(False)
        self.calculation_config_button.clicked.connect(
            self.edit_calculation_config
        )

        self.typical_scenarios_button = QPushButton("Типовые сценарии")
        self.typical_scenarios_button.setObjectName("typical_scenarios_button")
        self.typical_scenarios_button.clicked.connect(self.show_typical_scenarios)

        self.calculation_cases_button = QPushButton("Расчётные сценарии")
        self.calculation_cases_button.setObjectName("calculation_cases_button")
        self.calculation_cases_button.setEnabled(False)
        self.calculation_cases_button.clicked.connect(
            self.generate_calculation_cases
        )

        self.frequency_button = QPushButton("Расчёт частот")
        self.frequency_button.setObjectName("frequency_button")
        self.frequency_button.setEnabled(False)
        self.frequency_button.clicked.connect(self.calculate_frequencies)

        self.release_button = QPushButton("Масса в аварии")
        self.release_button.setObjectName("release_button")
        self.release_button.setEnabled(False)
        self.release_button.clicked.connect(self.calculate_releases)

        self.spill_button = QPushButton("Площадь пролива")
        self.spill_button.setObjectName("spill_button")
        self.spill_button.setEnabled(False)
        self.spill_button.clicked.connect(self.calculate_spills)

        self.evaporation_button = QPushButton("Испарение")
        self.evaporation_button.setObjectName("evaporation_button")
        self.evaporation_button.setEnabled(False)
        self.evaporation_button.clicked.connect(self.calculate_evaporation)

        self.hazard_factor_button = QPushButton("Масса ПФ")
        self.hazard_factor_button.setObjectName("hazard_factor_button")
        self.hazard_factor_button.setEnabled(False)
        self.hazard_factor_button.clicked.connect(self.calculate_hazard_factors)

        self.pool_fire_button = QPushButton("Пожар пролива")
        self.pool_fire_button.setObjectName("pool_fire_button")
        self.pool_fire_button.setEnabled(False)
        self.pool_fire_button.clicked.connect(self.calculate_pool_fires)

        self.validation_button = QPushButton("Проверка данных")
        self.validation_button.setObjectName("validation_button")
        self.validation_button.setEnabled(False)
        self.validation_button.clicked.connect(self.validate_project)

        data_button_layout = QHBoxLayout()
        data_button_layout.addWidget(create_button)
        data_button_layout.addWidget(open_button)
        data_button_layout.addWidget(self.project_common_button)
        data_button_layout.addWidget(self.substances_button)
        data_button_layout.addWidget(self.equipment_button)
        data_button_layout.addWidget(self.amount_button)

        calculation_button_layout = QHBoxLayout()
        calculation_button_layout.addWidget(self.typical_scenarios_button)
        calculation_button_layout.addWidget(self.calculation_config_button)
        calculation_button_layout.addWidget(self.calculation_cases_button)
        calculation_button_layout.addWidget(self.release_button)
        calculation_button_layout.addWidget(self.spill_button)
        calculation_button_layout.addWidget(self.evaporation_button)
        calculation_button_layout.addWidget(self.hazard_factor_button)
        calculation_button_layout.addWidget(self.pool_fire_button)
        calculation_button_layout.addWidget(self.frequency_button)
        calculation_button_layout.addWidget(self.validation_button)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addLayout(data_button_layout)
        layout.addLayout(calculation_button_layout)
        layout.addWidget(self.project_label, 1)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def create_project(self) -> None:
        if not self.organizations:
            self._show_error("Справочник организаций пуст или повреждён")
            return
        dialog = CreateProjectDialog(self.organizations, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.project_path():
            self._show_error("Не выбрана папка проекта")
            return
        try:
            project = self.service.create(dialog.project_path(), dialog.project_data())
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.show_project(project, Path(dialog.project_path()).resolve())

    def open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Открыть проект IRIS v2")
        if not directory:
            return
        try:
            project = self.service.open(directory)
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.show_project(project, Path(directory).resolve())

    def show_project(self, project: ProjectInfo, directory: Path) -> None:
        self.current_project = project
        self.current_project_directory = directory
        self.project_common_button.setEnabled(True)
        self.substances_button.setEnabled(True)
        self.equipment_button.setEnabled(True)
        self.amount_button.setEnabled(True)
        self.calculation_config_button.setEnabled(True)
        self.calculation_cases_button.setEnabled(True)
        self.release_button.setEnabled(True)
        self.spill_button.setEnabled(True)
        self.evaporation_button.setEnabled(True)
        self.hazard_factor_button.setEnabled(True)
        self.pool_fire_button.setEnabled(True)
        self.frequency_button.setEnabled(True)
        self.validation_button.setEnabled(True)
        self.project_label.setText(
            f"Проект: {project.name}\n"
            f"Шифр: {project.code}\n"
            f"Организация: {project.organization_name}\n"
            f"ОПО: {project.opo_name}\n"
            f"Регистрационный номер: {project.opo_registration_number}"
        )

    def edit_project_common(self) -> None:
        if self.current_project is None or self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            dialog = ProjectCommonDialog(
                self.current_project_directory,
                self.current_project,
                self.developers,
                self,
            )
        except ProjectCommonError as exc:
            self._show_error(str(exc))
            return
        dialog.exec()

    def edit_substances(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            substances = SubstanceService().load_archive()
            dialog = SubstanceDialog(
                self.current_project_directory, substances, self
            )
        except SubstanceError as exc:
            self._show_error(str(exc))
            return
        dialog.exec()

    def import_equipment(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        service = EquipmentService()
        expected_template = (
            self.current_project_directory / "input" / EXCEL_FILE_NAME
        )
        template_existed = expected_template.is_file()

        if template_existed:
            choice = QMessageBox(self)
            choice.setIcon(QMessageBox.Icon.Question)
            choice.setWindowTitle("Оборудование")
            choice.setText("Файл equipment_data.xlsx уже существует")
            choice.setInformativeText("Выберите, что с ним сделать.")
            import_button = choice.addButton(
                "Импортировать существующий",
                QMessageBox.ButtonRole.AcceptRole,
            )
            create_button = choice.addButton(
                "Создать новый шаблон",
                QMessageBox.ButtonRole.DestructiveRole,
            )
            choice.addButton(QMessageBox.StandardButton.Cancel)
            choice.exec()

            if choice.clickedButton() is create_button:
                confirmation = QMessageBox.warning(
                    self,
                    "Замена шаблона",
                    "Текущее содержимое input/equipment_data.xlsx будет "
                    "полностью заменено новым типовым заполнением.\n\n"
                    "Продолжить?",
                    QMessageBox.StandardButton.Yes
                    | QMessageBox.StandardButton.Cancel,
                    QMessageBox.StandardButton.Cancel,
                )
                if confirmation != QMessageBox.StandardButton.Yes:
                    return
                try:
                    template_path = service.ensure_template(
                        self.current_project_directory,
                        replace_existing=True,
                    )
                except EquipmentError as exc:
                    self._show_error(str(exc))
                    return
                QMessageBox.information(
                    self,
                    "Шаблон создан заново",
                    f"Новый файл готов:\n{template_path}",
                )
                return

            if choice.clickedButton() is not import_button:
                return

        try:
            template_path = service.ensure_template(self.current_project_directory)
        except EquipmentError as exc:
            self._show_error(str(exc))
            return
        if not template_existed:
            QMessageBox.information(
                self,
                "Шаблон создан",
                f"Заполните файл Excel и повторно нажмите «Оборудование»:\n{template_path}",
            )
            return

        excel_path, _ = QFileDialog.getOpenFileName(
            self,
            "Выберите заполненный equipment_data.xlsx",
            str(template_path),
            "Excel (*.xlsx)",
        )
        if not excel_path:
            return
        try:
            result = service.import_excel(
                self.current_project_directory, excel_path
            )
        except EquipmentError as exc:
            self._show_error(str(exc))
            return
        QMessageBox.information(
            self,
            "Импорт завершён",
            f"Импортировано строк оборудования: {result.count}\n{result.json_path}",
        )

    def calculate_amounts(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = AmountCalculationService().calculate(
                self.current_project_directory
            )
        except AmountCalculationError as exc:
            self._show_error(str(exc))
            return
        AmountCalculationDialog(result, self).exec()

    def validate_project(self) -> None:
        if self.current_project is None or self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        report = ProjectValidationService().check(
            self.current_project_directory, self.current_project
        )
        ProjectValidationDialog(report, self).exec()

    def edit_calculation_config(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            dialog = CalculationConfigDialog(
                self.current_project_directory, self
            )
        except CalculationConfigError as exc:
            self._show_error(str(exc))
            return
        dialog.exec()

    def show_typical_scenarios(self) -> None:
        try:
            catalog = TypicalScenarioService().load()
        except TypicalScenarioError as exc:
            self._show_error(str(exc))
            return
        TypicalScenariosDialog(catalog, self).exec()

    def generate_calculation_cases(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = CalculationCasesService().generate(
                self.current_project_directory
            )
        except CalculationCasesError as exc:
            self._show_error(str(exc))
            return
        CalculationCasesDialog(result, self).exec()

    def calculate_frequencies(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = FrequencyCalculationService().calculate(
                self.current_project_directory
            )
        except FrequencyCalculationError as exc:
            self._show_error(str(exc))
            return
        FrequencyCalculationDialog(result, self).exec()

    def calculate_releases(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = ReleaseCalculationService().calculate(
                self.current_project_directory
            )
        except ReleaseCalculationError as exc:
            self._show_error(str(exc))
            return
        ReleaseCalculationDialog(result, self).exec()

    def calculate_spills(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = SpillCalculationService().calculate(
                self.current_project_directory
            )
        except SpillCalculationError as exc:
            self._show_error(str(exc))
            return
        SpillCalculationDialog(result, self).exec()

    def calculate_evaporation(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = EvaporationCalculationService().calculate(
                self.current_project_directory
            )
        except EvaporationCalculationError as exc:
            self._show_error(str(exc))
            return
        EvaporationCalculationDialog(result, self).exec()

    def calculate_hazard_factors(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = HazardFactorCalculationService().calculate(
                self.current_project_directory
            )
        except HazardFactorCalculationError as exc:
            self._show_error(str(exc))
            return
        HazardFactorCalculationDialog(result, self).exec()

    def calculate_pool_fires(self) -> None:
        if self.current_project_directory is None:
            self._show_error("Сначала создайте или откройте проект")
            return
        try:
            result = PoolFireCalculationService().calculate(
                self.current_project_directory
            )
        except PoolFireCalculationError as exc:
            self._show_error(str(exc))
            return
        PoolFireCalculationDialog(result, self).exec()

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Ошибка", message)


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
