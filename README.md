# IRIS v2 — минимальное ядро

Поддерживается Python 3.10.

## Установка

```powershell
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

Первая команда устанавливает зависимости, вторая подключает сам проект в
режиме разработки без повторной загрузки пакетов.

## Создание проекта

```powershell
iris-v2 create "D:\IRIS_projects\Test" `
  --name "Тестовый проект" `
  --code "TEST-001" `
  --organization "АО Пример" `
  --opo "Тестовый ОПО" `
  --registration-number "А00-00000-0000"
```

## Открытие проекта

```powershell
iris-v2 open "D:\IRIS_projects\Test"
```

Папка проекта содержит `project.sqlite3`, `project.json`, `input` и `output`.

## Окно программы

```powershell
python main.py
```

Также окно можно запустить командой `iris-v2-gui`.

## Организации и ОПО

Для каждой организации создайте отдельную папку и скопируйте в неё справочник:

```powershell
New-Item -ItemType Directory .\organizations\Example
Copy-Item .\src\iris_v2\data\organization.json `
  .\organizations\Example\organization.json
```

Структура справочников:

```text
organizations/
├─ Orenburgneft/organization.json
├─ Tatneft/organization.json
└─ Другие организации/organization.json
```

Программа автоматически загружает все файлы `organizations/*/organization.json`.
В каждом файле используется исходная вложенная структура: сведения об
организации находятся в `organization`, а список её ОПО — в `sites`.
После изменения файлов перезапустите программу.

Папка `organizations` исключена из Git. Если в ней нет справочников, программа использует
обезличенный пример `src/iris_v2/data/organization.json`.

При создании проекта в его базу копируются все разделы организации и все поля
выбранного ОПО без распрямления. Список остальных ОПО в снимок не попадает.

Значение `sanitary_protection_zone_m: 0` означает, что санитарно-защитная
зона у ОПО отсутствует. `employees_other_opo_count` — суммарная численность
людей на соседних ОПО в возможной зоне воздействия.
