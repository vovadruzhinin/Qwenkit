# Как залить qwenkit на GitHub

Репозиторий уже подготовлен: автор всех коммитов `vovadruzhinin`, ветка `main`,
рабочее дерево чистое, тесты зелёные. Осталось создать пустой репозиторий на
GitHub и запушить.

Время: ~10 минут. Ничего платного не требуется.

---

## Шаг 0. Забрать файлы

Архив **`qwenkit-github.zip`** содержит проект **вместе с историей git**
(папка `.git` внутри). Распакуй его — и можно пушить сразу, коммиты пересоздавать
не нужно.

Автор всех коммитов — `vovadruzhinin <vovadruzhinin@users.noreply.github.com>`.
Хеши сверять не обязательно: достаточно того, что `git status` чистый.

### Как распаковывать, чтобы не слетели права доступа

**Windows** — просто правый клик → «Извлечь всё». Права файлов там не имеют
значения, а `qwenkit.cmd` и так запускается двойным щелчком.

**macOS** — двойной клик по архиву в Finder сохраняет права. Либо в терминале:

```bash
unzip qwenkit-github.zip
```

**Linux** — нужен `unzip`, он восстанавливает бит исполняемости:

```bash
sudo apt install unzip        # если ещё не стоит
unzip qwenkit-github.zip
```

Если `unzip` ставить не хочется, распакуй питоном — он права **не** восстанавливает,
поэтому добавь их одной командой:

```bash
python3 - <<'EOF'
import zipfile, os
z = zipfile.ZipFile("qwenkit-github.zip")
for i in z.infolist():
    z.extract(i, ".")
    if not i.is_dir():
        os.chmod(i.filename, (i.external_attr >> 16) & 0o7777)
print("готово")
EOF
```

### Всё равно можно ничего не чинить

Бит исполняемости нужен только чтобы запускать `./qwenkit-cli` и `./publish.sh`
напрямую. Через интерпретатор работает всегда, независимо от прав:

```bash
python3 qwenkit-cli doctor
bash publish.sh
```

### Проверка после распаковки

```bash
cd qwenkit
git log --oneline
# несколько строк, все от автора vovadruzhinin
git status
# "nothing to commit, working tree clean"
python3 tests/test_qwenkit.py
# "пройдено: 155   провалено: 0"
```

Если `git status` показывает изменения `qwenkit-cli` или `publish.sh` — слетели
права. Лечится одной командой, ничего пересоздавать не нужно:

```bash
chmod +x qwenkit-cli publish.sh
git status        # должно стать чисто
```

Если `.git` потерялся при распаковке (некоторые архиваторы прячут имена,
начинающиеся с точки) — не страшно, на шаге 3 есть вариант «с нуля».

---

## Шаг 1. Завести GitHub-аккаунт и способ авторизации

### Вариант A — GitHub CLI (проще всего, рекомендую)

**Windows** (в PowerShell от администратора):

```powershell
winget install --id GitHub.cli
```

Потом **закрой и открой терминал заново** (иначе `gh` не найдётся).

**macOS:**

```bash
brew install gh
```

**Linux (Debian/Ubuntu):**

```bash
sudo apt update && sudo apt install gh
```

Авторизация — одна команда, откроется браузер:

```bash
gh auth login
```

Отвечай так: `GitHub.com` → `HTTPS` → `Y` (authenticating Git with your GitHub
credentials) → `Login with a web browser` → скопируй одноразовый код → вставь
в браузере.

Проверка:

```bash
gh auth status
```

### Вариант B — обычный git через браузер

Никаких программ ставить не нужно. Git спросит логин и пароль; **паролем должен
быть не твой пароль от GitHub, а Personal Access Token**:

1. открой https://github.com/settings/tokens
2. `Generate new token (classic)`
3. галочка только на `repo`
4. срок — 90 дней, сгенерируй и **сразу скопируй** (показывается один раз)
5. при `git push` в поле username — `vovadruzhinin`, в поле password — этот токен

---

## Шаг 2. Создать пустой репозиторий

### Если ставил GitHub CLI — одной командой

```bash
cd qwenkit
gh repo create qwenkit --public --source=. --remote=origin \
  --description "Free API setup, Claude Code migration and a starter pack for Qwen Code CLI" \
  --push
```

Готово, можно прыгать к шагу 4. Флаг `--push` сам добавит remote и зальёт код.

### Если без GitHub CLI — через браузер

1. открой https://github.com/new
2. **Repository name:** `qwenkit`
3. **Public** или **Private** — на твой выбор
4. **ВАЖНО:** не ставь ни одной галочки — ни «Add a README file», ни
   «Add .gitignore», ни «Choose a license». Репозиторий должен родиться
   абсолютно пустым, иначе первый push потребует слияния и начнётся возня.
5. жми `Create repository`

---

## Шаг 3. Запушить

### Если `.git` на месте (обычный случай)

```bash
cd qwenkit
git remote add origin https://github.com/vovadruzhinin/qwenkit.git
git push -u origin main
```

### Если `.git` потерялся — создать историю заново

Получится один коммит вместо трёх. На функциональность не влияет никак.

```bash
cd qwenkit
git init -b main
git add -A
git -c user.name="vovadruzhinin" \
    -c user.email="vovadruzhinin@users.noreply.github.com" \
    commit -m "qwenkit 1.0.0 — free API setup, Claude Code migration and a starter pack for Qwen Code"
git remote add origin https://github.com/vovadruzhinin/qwenkit.git
git push -u origin main
```

### Если push отклоняется

| Ошибка | Что делать |
| --- | --- |
| `remote contains work that you do not have` | Репозиторий создан не пустым. Либо удали его и создай заново без галочек, либо `git pull --rebase origin main` и снова push |
| `Authentication failed` / `403` | Протух или неверный токен. Перевыпусти: https://github.com/settings/tokens |
| `error: src refspec main does not match` | Ветка называется не `main`. Посмотри `git branch` и пушь её: `git push -u origin <имя>` |
| `Permission denied (publickey)` | Remote настроен на SSH, а ключей нет. Переключи на HTTPS: `git remote set-url origin https://github.com/vovadruzhinin/qwenkit.git` |

---

## Шаг 4. Причесать репозиторий на GitHub

Открой https://github.com/vovadruzhinin/qwenkit и справа в блоке **About**
нажми на шестерёнку:

- **Description:** `Free API setup, Claude Code migration and a starter pack for Qwen Code CLI`
- **Website:** можно оставить пустым
- **Topics** (это сильно влияет на находимость через поиск):

```
qwen  qwen-code  claude-code  ai  cli  coding-agent  migration
llm  developer-tools  mcp  subagents  free-api
```

- **Include in the home page:** поставь галочки на `Releases` и `Packages` — не
  мешает.

---

## Шаг 5. Проверить, что CI зелёный

Через минуту после пуша открой вкладку **Actions**. Там запустится workflow
`tests`: 9 задач — 3 операционные системы (ubuntu, macos, windows) × 3 версии
Python (3.9, 3.11, 3.13).

```bash
gh run list            # список запусков
gh run watch           # следить за текущим
```

Ожидаемый результат — все зелёные. Если какая-то упадёт:

```bash
gh run view --log-failed
```

---

## Шаг 6. (по желанию) Релиз

```bash
gh release create v1.0.0 --title "qwenkit 1.0.0" --notes "Первый релиз: бесплатный API, миграция с Claude Code, установка наборов с GitHub, стартовый набор команд и агентов."
```

---

## Быстрая шпаргалка всего процесса

```bash
# распаковал qwenkit-github.zip
cd qwenkit
gh auth login                                              # один раз
gh repo create qwenkit --public --source=. --remote=origin --push
# готово: https://github.com/vovadruzhinin/qwenkit
```

---

## Если захочешь опубликовать и в PyPI

Чтобы люди могли ставить через `pip install qwenkit`:

```bash
PYPI=1 OWNER=vovadruzhinin ./publish.sh
```

Скрипт соберёт sdist и wheel, прогонит `twine check`, а загрузку оставит тебе
(нужен токен PyPI, он сознательно не автоматизирован):

```bash
python3 -m twine upload dist/*
```

Проверь, что имя `qwenkit` свободно: https://pypi.org/project/qwenkit/

---

## Локальная проверка перед публикацией

Если хочешь убедиться, что всё работает, прежде чем пушить:

```bash
pip install -r requirements.txt
python3 tests/test_qwenkit.py     # ожидаем: пройдено 151, провалено 0
python3 qwenkit-cli --help
python3 qwenkit-cli doctor
```
