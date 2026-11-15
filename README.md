# qwenkit

Обвязка для **Qwen Code** (CLI-агент `@qwen-code/qwen-code`): подключить бесплатный API,
перенести проект с Claude Code и поставить готовый набор команд и субагентов.

Один Python-скрипт, одна зависимость (`pyyaml`). Работает на Windows, macOS и Linux.

> 👉 **Впервые здесь?** Начните с **[руководства пользователя](docs/GUIDE.md)** —
> оно написано для тех, кто хочет пользоваться, а не разрабатывать: пошаговая
> настройка с нуля, разбор каждой команды, лечение типовых проблем и ответы на
> вопросы. Этот README — справочник по устройству и таблицам соответствий.
>
> English: **[README.en.md](README.en.md)**

```
qwenkit doctor      диагностика окружения
qwenkit providers   справочник бесплатных провайдеров
qwenkit setup       установка Qwen Code + генерация ~/.qwen/settings.json
qwenkit probe       живой тест: какие модели реально работают с tool-calling
qwenkit convert     миграция проекта с Claude Code на Qwen Code
qwenkit pack        стартовый набор: 8 команд + 6 субагентов
qwenkit install     поставить чужой набор агентов/команд с GitHub
qwenkit search      найти такие наборы на GitHub
```

---

## Функционал

Восемь команд закрывают весь путь: от «нет ни ключа, ни настроек» до рабочего
агента с набором команд и субагентов.

| Задача | Команда | Что получается |
| --- | --- | --- |
| Понять, что сломано | `doctor` | отчёт по Node.js, `qwen`, сети, ключам и `settings.json` — с подсказкой, что именно чинить |
| Выбрать бесплатного провайдера | `providers` | лимиты, ссылки на ключи и модели + живой каталог бесплатных моделей OpenRouter с tool-calling |
| Подключить модель | `setup` | установка Qwen Code (флаг `--install`) и `~/.qwen/settings.json` под выбранного провайдера |
| Убедиться, что модель годится агенту | `probe` | реальный запрос с объявленным инструментом: поддерживает ли модель tool-calling |
| Перейти с Claude Code | `convert` | `CLAUDE.md` → `QWEN.md`, команды, субагенты, `.mcp.json`, `settings.json`; спорное — в `MIGRATION_TODO.md`, старое — в бэкап |
| Получить готовый набор | `pack` | 8 команд и 6 субагентов в `~/.qwen` или `./.qwen` |
| Взять чужой набор с GitHub | `search`, `install` | поиск и установка с конвертацией в формат Qwen Code и манифестом для точного удаления |

**Три типичных сценария**

- **С нуля:** `doctor` → ключ ModelScope → `setup --provider modelscope --install --refresh-models` → `probe` → `pack`.
- **Переход с Claude Code:** `convert --dry-run .` → `convert .` → `convert --global`.
- **Готовые команды:** `search` → `install owner/repo --dry-run` → `install owner/repo`.

Подробнее про каждую команду — в разделах ниже, пошаговое руководство с нуля —
в [docs/GUIDE.md](docs/GUIDE.md).

---

## Главная новость, из-за которой это вообще понадобилось

**Бесплатный тариф Qwen OAuth (2000 запросов в день) отключён 15 апреля 2026 года.**

Почти все статьи и видео в интернете до сих пор советуют `qwen` → `/auth` → Qwen OAuth.
Это больше не работает: в официальной документации раздел так и называется —
«Option 2: Qwen OAuth (Discontinued)». Сейчас `/auth` предлагает четыре варианта:
QwenCloud, Alibaba ModelStudio, сторонние провайдеры и свой провайдер — все платные
или требующие ключа.

**Что реально бесплатно сейчас:**

| Провайдер | Что бесплатно | Ключ |
| --- | --- | --- |
| **ModelScope API-Inference** ⭐ | ~2000 запросов/день, каталог ~37 моделей: Qwen3.5/Qwen3.8, DeepSeek-V4, GLM-4.7/5.2 | [modelscope.cn/my/myaccesstoken](https://www.modelscope.cn/my/myaccesstoken) |
| **OpenRouter** | 50 запросов/день (1000/день при кредитах от ~9$), 20 RPM | [openrouter.ai/settings/keys](https://openrouter.ai/settings/keys) |
| **Groq** | ~1000 запросов/день, ~200K токенов/день, 30 RPM | [console.groq.com/keys](https://console.groq.com/keys) |
| **Cloudflare Workers AI** | 10 000 «нейронов»/день, 300 RPM | [dash.cloudflare.com](https://dash.cloudflare.com/profile/api-tokens) |
| **Cerebras** | разовые ~5$ на 30 дней (нужна карта) | [cloud.cerebras.ai](https://cloud.cerebras.ai/) |
| **Ollama** | полностью бесплатно, без лимитов и без интернета | не нужен |

⭐ = рекомендация по умолчанию: единственный вариант с большой дневной квотой
и родными моделями Qwen.

Лимиты меняются — `qwenkit providers` печатает справку, а `qwenkit probe` проверяет
фактическое состояние дел живым запросом.

### Важно про tool-calling

Qwen Code — **агент**: он вызывает инструменты (чтение файлов, shell, поиск).
Если модель не поддерживает function calling, агент не запустится, даже если чат
отвечает нормально. `qwenkit probe` проверяет именно это — шлёт запрос с объявленным
инструментом и смотрит, вернула ли модель `tool_calls`.

---

## Установка

Нужны Python 3.9+ и (для самого Qwen Code) Node.js 20+.

```bash
git clone https://github.com/vovadruzhinin/qwenkit.git
cd qwenkit
pip install -r requirements.txt        # единственная зависимость — pyyaml
```

**`pyyaml` обязателен для `convert` и `install`.** Без него конвертер не падает,
но и не разбирает frontmatter: файлы копируются как есть с предупреждением, то
есть имена инструментов и режимы останутся кловдовскими. `doctor`, `setup`,
`probe` и `pack` работают без него.

Дальше можно запускать напрямую:

```bash
python3 qwenkit-cli doctor
```

или сделать короткую команду (Linux/macOS):

```bash
ln -s "$PWD/qwenkit-cli" ~/.local/bin/qwenkit && chmod +x qwenkit-cli
qwenkit doctor
```

Windows (PowerShell), запуск из папки проекта:

```powershell
python qwenkit-cli doctor
```

---

## Быстрый старт за 5 шагов

```bash
# 1. Диагностика: Node.js, сеть, доступность провайдеров, текущий конфиг
qwenkit doctor

# 2. Получить бесплатный ключ ModelScope (ссылка выше) и экспортировать его
export MODELSCOPE_API_KEY='ms-xxxxxxxxxxxxxxxx'        # Linux/macOS
# $env:MODELSCOPE_API_KEY='ms-xxxx'                    # Windows PowerShell

# 3. Установить Qwen Code и сгенерировать конфиг
qwenkit setup --provider modelscope --install --refresh-models \
            --fast-model "Qwen/Qwen3.5-27B"

# 4. Убедиться, что API отвечает и tool-calling работает
qwenkit probe --provider modelscope

# 5. Поставить команды и субагентов, затем идти в проект
qwenkit pack
cd ваш-проект && qwen
```

Внутри `qwen`:

| Команда | Что делает |
| --- | --- |
| `/model` | сменить модель (все настроенные провайдеры одним списком) |
| `/agents manage` | список и настройка субагентов |
| `/mcp` | управление MCP-серверами |
| `/init` | сгенерировать `QWEN.md` по кодовой базе |
| `/memory` | посмотреть загруженную память |
| `/` | ваши команды из `.qwen/commands/` |

---

## Локальный вариант без интернета (Ollama)

Полностью бесплатно и без дневных лимитов — ценой качества модели и требования к железу.

```bash
# 1. поставить Ollama: https://ollama.com/download
# 2. скачать модель
ollama pull qwen3-coder:30b        # 24+ ГБ RAM/VRAM — лучший вариант для агента
ollama pull qwen3:14b              # ~16 ГБ RAM — разумный минимум
ollama pull qwen2.5-coder:7b       # ~8 ГБ RAM — слабый, но запустится везде

# 3. настроить Qwen Code
qwenkit setup --provider ollama --install
qwenkit probe --provider ollama    # проверит tool-calling локально
```

Ollama не проверяет ключ, но поле `envKey` обязательно — `qwenkit` подставит
заглушку `ollama` сам.

---

## Миграция с Claude Code

`qwenkit convert` переносит проект. Он **не ломает исходники**: существующие файлы
уезжают в `.qwen-backup-<timestamp>/`, а всё спорное попадает в `MIGRATION_TODO.md`.

```bash
qwenkit convert --dry-run .     # посмотреть, что будет
qwenkit convert .               # сконвертировать проект
qwenkit convert --global        # ~/.claude -> ~/.qwen (ваши личные команды и агенты)
```

### Что переносится

| Claude Code | Qwen Code | Как |
| --- | --- | --- |
| `CLAUDE.md` | `QWEN.md` | автоматически; `AGENTS.md` Qwen читает и так — дублировать не нужно |
| `CLAUDE.local.md` | `.qwen/QWEN.local.md` | автоматически + правило в `.gitignore` (Qwen его сам не создаёт) |
| `.claude/commands/**.md` | `.qwen/commands/**.md` | автоматически, с конвертацией синтаксиса |
| `.claude/agents/**.md` | `.qwen/agents/**.md` | автоматически, с заменой имён инструментов |
| `.mcp.json` | `.qwen/.mcp.json` | формат идентичен — копируется |
| `.claude/settings.json` | `.qwen/settings.json` | `mcpServers`, `hooks`, `env` — автоматически |

### Конвертация синтаксиса в промптах

| Claude Code | Qwen Code |
| --- | --- |
| `$ARGUMENTS` | `{{args}}` |
| `$1`, `$2` | `{{args}}` + предупреждение (нумерованных аргументов в Qwen нет) |
| `` !`git status` `` | `!{git status}` |
| `@docs/file.md` | `@{docs/file.md}` |
| `$CLAUDE_PROJECT_DIR` | `$QWEN_PROJECT_DIR` (старое имя Qwen тоже выставляет) |

Конвертер не трогает `@` внутри `!{...}` — это shell-код, а не ссылка на файл.

### Субагенты

Qwen Code нативно принимает поля Claude Code 2.1.168: `maxTurns`, `color`,
`mcpServers`, `hooks`. Остальное конвертер маппит:

| Claude Code | Qwen Code |
| --- | --- |
| `permissionMode: acceptEdits` | `approvalMode: auto-edit` |
| `permissionMode: bypassPermissions` | `approvalMode: yolo` |
| `permissionMode: dontAsk` | `approvalMode: auto` |
| `model: haiku` | `model: fast` |
| `model: sonnet` / `opus` | `model: inherit` |
| `Read` / `Write` / `Edit` | `read_file` / `write_file` / `edit` |
| `Bash` | `run_shell_command` |
| `Grep` / `Glob` / `LS` | `grep_search` / `glob` / `list_directory` |
| `WebFetch` / `WebSearch` | `web_fetch` / `web_search` |
| `TodoWrite` | `todo_write` |
| `Task` | `agent` |
| `mcp__server__tool` | без изменений |

Поля `effort`, `skills`, `initialPrompt`, `memory`, `isolation` в Qwen Code
задокументированы, но **ещё не реализованы** — конвертер их сохраняет и предупреждает.

### Три вещи, за которыми нужен глаз

1. **`disallowedTools`.** У Claude Code есть `BashOutput` и `KillShell`, у Qwen Code
   отдельных инструментов для этого нет — всем управляет `run_shell_command`.
   Наивный конвертер заменил бы `disallowedTools: [KillShell]` на
   `disallowedTools: [run_shell_command]` и **полностью заблокировал агенту терминал**.
   `qwenkit` такие инструменты отбрасывает и loudly предупреждает — список надо
   перепроверить вручную.

2. **Матчеры хуков.** `matcher: "Edit|Write"` превращается в `"edit|write_file"`,
   потому что хуки в Qwen Code матчатся по каноническим именам инструментов.

3. **Таймауты хуков.** В Qwen Code `timeout` у command-хуков задаётся в **секундах**,
   но значения ≥ 1000 читаются как миллисекунды для обратной совместимости.
   Конвертер оставляет значение и подсказывает, на что заменить.

### Что придётся перенести руками

`permissions` (allow/deny/ask правила вида `Bash(npm run test:*)`), `apiKeyHelper`,
`statusLine`, `outputStyle`, `includeCoAuthoredBy`, каталог `.claude/hooks/`.
Полный список — в `MIGRATION_TODO.md`, который создаётся при конвертации.

---

## Стартовый набор (`qwenkit pack`)

```bash
qwenkit pack --list                    # показать состав
qwenkit pack                           # в ~/.qwen — видно во всех проектах
qwenkit pack --target project          # в ./.qwen — только этот проект (имеет приоритет)
qwenkit pack --only agents             # только субагентов
qwenkit pack --overwrite               # заменить существующие (делает .bak)
```

**Команды** (внутри `qwen` набираете `/`):

| Команда | Назначение |
| --- | --- |
| `/git:commit` | сообщение коммита по staged-изменениям (Conventional Commits) |
| `/review` | код-ревью с вердиктом и severity |
| `/tests` | тесты под существующий фреймворк проекта, с прогоном |
| `/explain` | объяснение кода: зачем → как → карта → подводные камни |
| `/refactor` | рефакторинг без изменения поведения, мелкими шагами |
| `/security` | аудит безопасности по категориям с severity |
| `/doc` | точечное обновление документации под текущий код |
| `/fix-ci` | разбор падения CI: первопричина, а не симптом |

**Субагенты** (Qwen Code вызывает их сам по описанию, либо явно — «запусти агента reviewer»):

| Агент | Модель | Инструменты | Режим |
| --- | --- | --- | --- |
| `reviewer` | inherit | только чтение + shell | `plan` — ничего не меняет |
| `tester` | inherit | чтение, запись, shell | `auto-edit` |
| `researcher` | fast | чтение, поиск, сеть | `plan` |
| `documenter` | inherit | чтение, запись, поиск | `auto-edit` |
| `refactorer` | inherit | чтение, запись, shell | `auto-edit` |
| `python-expert` | inherit | чтение, запись, shell, сеть | `auto-edit` |

Все промпты на русском, идентификаторы и код — на английском.
Агенты построены по принципу единственной ответственности и содержат явные
запреты на «ослабить тест, чтобы позеленело» и «заодно исправить баг при рефакторинге».

---

## Чужие наборы агентов и команд с GitHub

В интернете лежат сотни наборов под Claude Code — папки с `.md`-агентами и
командами. `qwenkit` ставит их одной командой, сразу конвертируя в формат
Qwen Code.

```bash
qwenkit search                                  # найти наборы
qwenkit install owner/repo --dry-run            # посмотреть план, ничего не меняя
qwenkit install owner/repo                      # поставить в ~/.qwen
qwenkit install owner/repo/agents               # только подкаталог
qwenkit install owner/repo --only commands      # только команды
qwenkit install owner/repo --prefix mypack-     # префикс имён, чтобы наборы не пересекались
qwenkit install --list                          # что установлено через qwenkit
qwenkit install x --uninstall owner/repo        # удалить набор
```

Принимаются разные формы адреса: `owner/repo`, полная ссылка на GitHub
(включая `/tree/<ветка>/<путь>` и `/blob/.../file.md`) и ссылки на
`raw.githubusercontent.com`.

### Как это устроено и почему не упирается в лимиты

GitHub без токена даёт всего **60 запросов к API в час**. Поэтому:

1. список всех файлов репозитория берётся **одним** запросом к `git/trees?recursive=1`;
2. сами файлы качаются с `raw.githubusercontent.com` — этот хост **не тратит**
   лимит `api.github.com`;
3. `search` использует Search API (10 запросов/минуту без токена) и поэтому
   делает между запросами паузу.

Если ставите много — задайте токен, лимит станет 5000/час:

```bash
export GITHUB_TOKEN=ghp_...     # публичных репозиториев достаточно токена без прав
```

### Что устанавливается, а что нет

| Содержимое репозитория | Поведение |
| --- | --- |
| `agents/**.md`, `subagents/**.md` | конвертируются и ставятся в `.qwen/agents/` |
| `commands/**.md`, `commands/**.toml` | конвертируются и ставятся в `.qwen/commands/` |
| `.mcp.json`, `mcp.json` | сливается с вашим, с предупреждением |
| `CLAUDE.md`, `AGENTS.md` | **не подмешивается** в ваш `QWEN.md`; сохраняется в `.qwen/imported-notes/` для просмотра |
| `.claude/settings.json` | **не устанавливается** — там могут быть хуки, запускающие произвольные команды. Только ссылка, чтобы посмотреть руками |
| `README`, `CHANGELOG`, `LICENSE`, исходники | игнорируются |

Вложенная структура каталогов репозитория сохраняется относительно `agents/`
или `commands/`, но лишний префикс отрезается: `awesome-pack/v2/src/agents/core/rev.md`
станет `.qwen/agents/core/rev.md`. Если имена из разных разделов совпадают,
к одному из них добавляется родительский каталог — файлы не перезатрут друг друга.

### Определение по содержимому

Не все наборы хранят агентов в папке `agents/`. Крупнейшие лежат так:

```
categories/01-core-development/api-designer.md
categories/03-infrastructure/backend-developer.md
```

По пути их не отличить от документации. Поэтому если по путям нашлось меньше
трёх агентов/команд, `qwenkit` скачивает `.md`-файлы (параллельно, до 250 штук)
и смотрит внутрь frontmatter: `name` + `description` + любое из полей агента
(`tools`, `model`, `permissionMode`, `color`, `maxTurns`, …) — значит, это агент.
Наличие `allowed-tools` или `argument-hint` перевешивает: это признак команды.

На репозитории из 198 файлов такой досмотр занимает ~10 секунд и находит 157 агентов.
Если структура нормальная, досмотр не запускается вовсе.

Каждая установка пишется в манифест `.qwen/.qwenkit-installed.json`, поэтому
`--uninstall` удаляет ровно то, что поставил qwenkit, не трогая ваши файлы.

### Безопасность

Агенты и команды — это **промпты, которые будет выполнять агент с доступом к
вашим файлам и терминалу**. Чужой набор = чужие инструкции.

`qwenkit` снижает риск, но не заменяет чтение:

- чужие `settings.json` с хуками не устанавливаются вообще;
- чужой `CLAUDE.md` не подмешивается в вашу память;
- на каждую shell-вставку `!{...}` внутри команды конвертер выдаёт
  предупреждение;
- установленное удаляется одной командой.

Перед первым запуском прочитайте файлы в `.qwen/agents/` и `.qwen/commands/`.

---

## Как это устроено внутри

```
qwenkit-cli                 исполняемая обёртка
qwenkit/
  cli.py                    диспетчер команд
  maps.py                   таблицы соответствий CC -> Qwen (имена инструментов,
                            режимы, модели, события хуков, пути)
  providers.py              каталог провайдеров + живой запрос списка моделей
  doctor.py                 диагностика
  setup_cmd.py              генерация settings.json (формат qwen-code 0.26+)
  probe.py                  проверка tool-calling реальным запросом
  convert.py                конвертер проекта
  pack.py                   стартовый набор команд и агентов
  install.py                установка наборов с GitHub + манифест для удаления
  search.py                 поиск наборов через GitHub Search API
tests/
  test_qwenkit.py           155 проверок, запускается без pytest
  fixture-cc/               учебный проект Claude Code со всеми граблями
docs/
  GUIDE.md                  руководство пользователя: настройка, команды, troubleshooting, FAQ
SOURCES.md                  ссылки на первоисточники всех таблиц и схем
CONTRIBUTING.md             как дорабатывать проект
PUBLISH.md                  как опубликовать свою копию на GitHub
```

Запуск тестов:

```bash
python3 tests/test_qwenkit.py
```

### Формат `settings.json`, который генерирует `setup`

Проверен на реальном `qwen` 0.26.0 — доходит до API провайдера и падает только
на невалидном ключе, значит конфиг распознан.

```json
{
  "modelProviders": {
    "openai": [
      {
        "id": "Qwen/Qwen3.8-27B",
        "name": "Qwen/Qwen3.8-27B",
        "envKey": "MODELSCOPE_API_KEY",
        "baseUrl": "https://api-inference.modelscope.cn/v1",
        "description": "ModelScope API-Inference (Alibaba)"
      }
    ]
  },
  "security": { "auth": { "selectedType": "openai" } },
  "model": { "name": "Qwen/Qwen3.8-27B" },
  "fastModel": "Qwen/Qwen3.5-27B"
}
```

Две ловушки, которые `qwenkit` обходит:

- значение ключа провайдера — **голый массив** моделей. Формат
  `{"protocol": …, "models": […]}` из ранних превью **молча игнорируется**;
- ключи никогда не пишутся в `settings.json`, если явно не передан `--store-key`.
  `qwenkit` ссылается на env-переменную через `envKey`.

---

## Источники и актуальность

Все таблицы соответствий и схемы конфигов взяты из первоисточников — документации
и кода `QwenLM/qwen-code` версии **0.26.0**, проверено **2026-10-24**.
Полный перечень файлов, что откуда взято и как обновить таблицы под новую версию, —
в [`SOURCES.md`](SOURCES.md).

Лимиты бесплатных тарифов меняются. `qwenkit providers` печатает справку со
ссылками, а `qwenkit probe` проверяет фактическое положение дел живым запросом.

---

## Лицензия

MIT — см. [LICENSE](LICENSE).

qwenkit — независимый сторонний инструмент. Он не является частью Qwen Code,
не модифицирует его и не связан с Alibaba Group. Qwen Code и Qwen — торговые
марки Alibaba Group, упоминаются в информационных целях.

---

## Тесты

Если qwen-code изменит схему конфигов или имена инструментов, тесты это поймают:

```bash
python3 tests/test_qwenkit.py     # 155 проверок, pytest не нужен
```
