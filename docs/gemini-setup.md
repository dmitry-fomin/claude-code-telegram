# Настройка Gemini как LLM для проекта

По умолчанию бот использует Claude (через `claude-agent-sdk`). Для любого проекта можно переключить LLM на Google Gemini через `google-genai` SDK.

## Шаг 1 — Получить Gemini API ключ

1. Перейдите на [aistudio.google.com/apikey](https://aistudio.google.com/apikey)
2. Создайте ключ (бесплатный tier включает достаточные лимиты)
3. Добавьте в `.env`:

```bash
GEMINI_API_KEY=ваш_ключ_здесь
```

## Шаг 2 — Установить зависимость

```bash
uv pip install "google-genai>=1.0"
# или через poetry:
poetry install --extras gemini
```

## Шаг 3 — Включить project thread mode

В `.env` добавьте:

```bash
ENABLE_PROJECT_THREADS=true
PROJECT_THREADS_MODE=private
PROJECTS_CONFIG_PATH=config/projects.yaml
```

## Шаг 4 — Создать config/projects.yaml

Файл `config/projects.yaml` не коммитится в git (он в `.gitignore`), создайте его локально:

```yaml
projects:
  - slug: my-project
    name: My Project
    path: my-project          # относительный путь от APPROVED_DIRECTORY
    enabled: true
    cli: gemini
    model: gemini-2.5-pro     # или gemini-2.5-flash для быстрее/дешевле

  - slug: other-project
    name: Other Project
    path: other-project
    enabled: true
    # cli: claude             # по умолчанию — использует claude-agent-sdk
    # model: claude-opus-4-7  # опционально переопределить глобальный CLAUDE_MODEL
```

**Поля проекта:**

| Поле | Обязательно | Описание |
|------|-------------|----------|
| `slug` | да | Уникальный ID (латиница, цифры, дефис) |
| `name` | да | Отображаемое имя |
| `path` | да | Путь относительно `APPROVED_DIRECTORY` |
| `enabled` | нет | `true` по умолчанию |
| `cli` | нет | `claude` (по умолчанию) или `gemini` |
| `model` | нет | Модель LLM, например `gemini-2.5-pro` или `claude-opus-4-7` |

## Шаг 5 — Синхронизировать топики в Telegram

После запуска бота отправьте команду `/sync_threads` — бот создаст отдельный топик (тред) для каждого проекта в `projects.yaml`.

Сообщения в топике проекта будут автоматически маршрутизироваться к нужному LLM.

## Инструменты Gemini

Когда `cli: gemini`, бот использует следующие встроенные инструменты:

| Инструмент | Описание |
|------------|----------|
| `read_file` | Читает файл (относительный путь от корня проекта) |
| `write_file` | Пишет файл (создаёт директории автоматически) |
| `run_bash` | Выполняет bash-команду в директории проекта |
| `list_directory` | Список файлов в директории |

Все операции ограничены директорией проекта — выйти за её пределы невозможно.

## Доступные модели Gemini

| Модель | Описание |
|--------|----------|
| `gemini-3-flash-preview` | Gemini 3 Flash (preview), новейший |
| `gemini-3-pro-preview` | Gemini 3 Pro (preview), самый мощный из третьего поколения |
| `gemini-2.5-pro` | Стабильный, лучший для сложных задач, контекст 1M токенов |
| `gemini-2.5-flash` | Стабильный, быстрее и дешевле Pro, встроенный thinking |
| `gemini-2.5-flash-lite` | Стабильный, самый быстрый и дешёвый |

> **Важно:** модели `gemini-3-*` сейчас в статусе preview — название обязательно с суффиксом `-preview` (например `gemini-3-flash-preview`, а не `gemini-3-flash`).

## Ограничения V1

- Сессии Gemini хранятся в памяти и не переживают перезапуск бота
- MCP серверы для Gemini не поддерживаются
- Стриминг: нотификации о вызовах инструментов отображаются в реальном времени, но итоговый текст приходит после завершения всего агентного цикла
