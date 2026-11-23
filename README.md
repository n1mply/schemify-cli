# Schemify (консольная версия)

<p align="center">
  <img width="256" height="256" alt="Schemify" src="https://github.com/user-attachments/assets/8b3ae53b-de89-4395-b1a9-31a13ac444da" />
</p>

<!-- <br clear="left" /> -->

## Установка и запуск
Скачайте zip-архив и распакуйте его в любом удобном месте либо клонируйте репозиторий в нужную директорию.

Затем выполните следующие команды в терминале, находясь в директории проекта.

**Windows**
```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # впишите LLM_API_KEY (необязательно)
python main.py
```
**Linux + macOS**
```
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # впишите LLM_API_KEY (необязательно)
python main.py
```

> В Windows для активации venv можно также использовать `venv\Scripts\activate.bat` (cmd) или `.\venv\Scripts\Activate.ps1` (PowerShell). Команда `cp` в Windows доступна в PowerShell; в cmd используйте `copy`.


## Режимы
1. **Вся лаба** - положите файлы в `inputs/`, имя должно заканчиваться номером задания
   (`task1.c`, `lab3_task2.c`). Схемы попадут в `output/lab_<номер>/` как `task1.png`.
   Если в файле несколько функций, для остальных создаётся `task1_<функция>.png`.
2. **Одна схема** - указываете путь к .c файлу (или имя файла из `inputs/`).

Штамп студента (по желанию): предмет, фамилия и инициалы, группа сохраняются в `config.json`
и в следующий раз подставляются автоматически. Вариант, номер лабы и задания запрашиваются каждый раз.

## config.json
| ключ | значение |
|---|---|
| `output_format` | `png` (по умолчанию), `svg`, `drawio` |
| `humanize` | `true/false` - очеловечивать подписи узлов (правила + ИИ при наличии ключа) |
| `inputs_dir`, `output_dir` | папки входных/выходных файлов |
| `student` | сохранённые ФИО, предмет, группа |

## .env
`LLM_API_KEY` — обязателен для работы ИИ; бесплатный API-ключ можно получить на сайте [ai.io.net](https://ai.io.net).
Опционально: LLM_BASE_URL, LLM_MODELS (через запятую), LLM_TIMEOUT.
