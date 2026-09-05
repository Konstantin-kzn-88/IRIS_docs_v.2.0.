import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from iris_v2.service import CreateProjectData, ProjectError, ProjectInfo, ProjectService


class CreateProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Создание проекта")
        self.setMinimumWidth(600)

        self.path_edit = QLineEdit()
        self.name_edit = QLineEdit()
        self.code_edit = QLineEdit()
        self.organization_edit = QLineEdit()
        self.opo_edit = QLineEdit()
        self.registration_edit = QLineEdit()

        browse_button = QPushButton("Выбрать…")
        browse_button.clicked.connect(self._select_project_path)
        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(browse_button)

        form = QFormLayout()
        form.addRow("Папка проекта:", path_layout)
        form.addRow("Название проекта:", self.name_edit)
        form.addRow("Шифр проекта:", self.code_edit)
        form.addRow("Организация:", self.organization_edit)
        form.addRow("Наименование ОПО:", self.opo_edit)
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

    def project_path(self) -> str:
        return self.path_edit.text().strip()

    def project_data(self) -> CreateProjectData:
        return CreateProjectData(
            name=self.name_edit.text(),
            code=self.code_edit.text(),
            organization_name=self.organization_edit.text(),
            opo_name=self.opo_edit.text(),
            opo_registration_number=self.registration_edit.text(),
        )


class MainWindow(QMainWindow):
    def __init__(self, service: ProjectService | None = None) -> None:
        super().__init__()
        self.service = service or ProjectService()
        self.setWindowTitle("IRIS v2")
        self.resize(720, 360)

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

        button_layout = QHBoxLayout()
        button_layout.addWidget(create_button)
        button_layout.addWidget(open_button)

        layout = QVBoxLayout()
        layout.addWidget(title)
        layout.addLayout(button_layout)
        layout.addWidget(self.project_label, 1)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def create_project(self) -> None:
        dialog = CreateProjectDialog(self)
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
        self.show_project(project)

    def open_project(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "Открыть проект IRIS v2")
        if not directory:
            return
        try:
            project = self.service.open(directory)
        except (ProjectError, OSError) as exc:
            self._show_error(str(exc))
            return
        self.show_project(project)

    def show_project(self, project: ProjectInfo) -> None:
        self.project_label.setText(
            f"Проект: {project.name}\n"
            f"Шифр: {project.code}\n"
            f"Организация: {project.organization_name}\n"
            f"ОПО: {project.opo_name}\n"
            f"Регистрационный номер: {project.opo_registration_number}"
        )

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Ошибка", message)


def main() -> int:
    application = QApplication.instance() or QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
