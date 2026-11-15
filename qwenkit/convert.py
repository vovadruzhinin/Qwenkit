"""Конвертер проекта Claude Code -> Qwen Code.

Переносит:
  * CLAUDE.md            -> QWEN.md            (+ CLAUDE.local.md -> .qwen/QWEN.local.md)
  * .claude/commands/**  -> .qwen/commands/**  (Markdown + YAML frontmatter)
  * .claude/agents/**    -> .qwen/agents/**    (с заменой имён инструментов)
  * .mcp.json            -> .qwen/.mcp.json    (формат идентичен)
  * .claude/settings.json: mcpServers/hooks/env -> .qwen/settings.json,
                           остальное -> MIGRATION_TODO.md

Безопасность: ничего не перезаписывает молча. Существующие файлы уезжают в
`.qwen-backup-<timestamp>/`. Есть --dry-run.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import shutil
import sys
from pathlib import Path

try:
    import yaml
except ImportError:                                            # pragma: no cover
    yaml = None

from .maps import (
    AGENT_COLORS,
    AGENT_NATIVE_FIELDS,
    AGENT_PENDING_FIELDS,
    CLAUDE_DIR,
    COMMAND_PASSTHROUGH_FIELDS,
    COMMAND_UNSUPPORTED_FIELDS,
    ENV_VAR_MAP,
    HARMLESS_METADATA_FIELDS,
    HOOK_EVENTS_QWEN_ONLY,
    HOOK_EVENTS_SHARED,
    MEMORY_FILES,
    MODEL_MAP,
    PERMISSION_MODE_MAP,
    QWEN_DIR,
    QWEN_TOOLS,
    SETTINGS_AUTO_KEYS,
    SETTINGS_MANUAL_KEYS,
    TOOL_DROP,
    TOOL_MAP,
)

C_RESET = C_RED = C_GRN = C_YEL = C_DIM = C_BOLD = ""
if sys.stdout.isatty():
    C_RESET, C_RED, C_GRN = "\033[0m", "\033[31m", "\033[32m"
    C_YEL, C_DIM, C_BOLD = "\033[33m", "\033[2m", "\033[1m"


class Report:
    """Журнал действий конвертера: что сделано, что пропущено, что чинить руками."""

    def __init__(self) -> None:
        self.done: list[str] = []
        self.skipped: list[str] = []
        self.warnings: list[tuple[str, str]] = []   # (файл, текст)
        self.manual: list[str] = []
        self.meta_fields: set = set()               # безобидные метаданные из чужих наборов

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append((where, msg))

    def add_manual(self, msg: str) -> None:
        self.manual.append(msg)

    # --- печать -------------------------------------------------------------
    def print_summary(self) -> None:
        print()
        print(f"{C_BOLD}=== Итог конвертации ==={C_RESET}")
        print(f"  {C_GRN}создано/изменено:{C_RESET} {len(self.done)}")
        for d in self.done:
            print(f"    {C_GRN}+{C_RESET} {d}")
        if self.skipped:
            print(f"  {C_DIM}пропущено:{C_RESET} {len(self.skipped)}")
            for s in self.skipped:
                print(f"    {C_DIM}-{C_RESET} {s}")
        if self.warnings:
            print(f"  {C_YEL}предупреждений:{C_RESET} {len(self.warnings)}")
            seen = set()
            for where, msg in self.warnings:
                key = (where, msg)
                if key in seen:
                    continue
                seen.add(key)
                print(f"    {C_YEL}!{C_RESET} {where}: {msg}")
        if self.meta_fields:
            print(f"  {C_DIM}перенесены молча (Qwen Code их игнорирует):{C_RESET} "
                  f"{', '.join(sorted(self.meta_fields))}")
        if self.manual:
            print(f"  {C_RED}нужно сделать руками:{C_RESET} {len(self.manual)}")
            for m in self.manual[:20]:
                print(f"    {C_RED}>{C_RESET} {m}")
            if len(self.manual) > 20:
                print(f"    {C_RED}>{C_RESET} ... и ещё {len(self.manual) - 20} (см. MIGRATION_TODO.md)")

    def write_todo(self, path: Path) -> None:
        if not self.manual and not self.warnings:
            return
        lines = [
            "# Что перенести вручную после конвертации в Qwen Code",
            "",
            f"Сформировано qwenkit {_dt.datetime.now().strftime('%Y-%m-%d %H:%M')}.",
            "",
            "Qwen Code нативно принимает большинство полей Claude Code 2.1.168",
            "(см. docs/users/features/sub-agents.md, раздел «Claude Code",
            "Compatibility Fields»), поэтому список короткий.",
            "",
            "## Ручные задачи",
            "",
        ]
        lines += [f"- [ ] {m}" for m in dict.fromkeys(self.manual)] or ["- [x] всё перенесено автоматически"]
        lines += ["", "## Предупреждения конвертера", ""]
        if self.warnings:
            for where, msg in dict.fromkeys(self.warnings):
                lines.append(f"- `{where}` — {msg}")
        else:
            lines.append("- нет")
        lines += [
            "",
            "## Справка",
            "",
            "| Было (Claude Code) | Стало (Qwen Code) |",
            "| --- | --- |",
            "| `CLAUDE.md` | `QWEN.md` (или оставьте `AGENTS.md` — Qwen читает его сам) |",
            "| `.claude/commands/*.md` | `.qwen/commands/*.md` |",
            "| `.claude/agents/*.md` | `.qwen/agents/*.md` |",
            "| `.claude/settings.json` | `.qwen/settings.json` |",
            "| `$ARGUMENTS` | `{{args}}` |",
            "| `` !`cmd` `` | `!{cmd}` |",
            "| `@file` в промпте | `@{file}` |",
            "| `permissionMode: acceptEdits` | `approvalMode: auto-edit` |",
            "| `model: haiku` | `model: fast` |",
            "| `Task` (инструмент) | `agent` |",
            "",
            "Переменная `$CLAUDE_PROJECT_DIR` в хуках продолжает работать —",
            "Qwen Code выставляет `$QWEN_PROJECT_DIR`, `$CLAUDE_PROJECT_DIR` и",
            "`$GEMINI_PROJECT_DIR` одновременно.",
            "",
            f"События хуков, которых нет в Claude Code, но есть в Qwen: "
            f"{', '.join(sorted(HOOK_EVENTS_QWEN_ONLY))}.",
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# YAML frontmatter
# ---------------------------------------------------------------------------
FM_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.S)


def split_frontmatter(text: str) -> tuple[dict | None, str, bool]:
    """Вернуть (frontmatter-словарь, тело, был ли frontmatter).

    Если PyYAML не установлен или frontmatter не распознан — словарь None,
    тело возвращается как есть (конвертер при этом только копирует файл).
    """
    m = FM_RE.match(text)
    if not m:
        return None, text, False
    raw = m.group(1)
    body = text[m.end():]
    if yaml is None:
        return None, text, True
    try:
        data = yaml.safe_load(raw)
    except Exception:                                          # noqa: BLE001
        return None, text, True
    if not isinstance(data, dict):
        return None, text, True
    return data, body, True


def dump_frontmatter(data: dict) -> str:
    if not data:
        return ""
    block = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=100
    ).strip()
    return f"---\n{block}\n---\n\n"


# ---------------------------------------------------------------------------
# Замена синтаксиса в теле промпта
# ---------------------------------------------------------------------------
BACKTICK_BANG_RE = re.compile(r"!`([^`\n]+)`")
AT_FILE_RE = re.compile(r"(?<![@\w{])@([A-Za-z0-9_./\-]+(?:\.[A-Za-z0-9]+))")
DOLLAR_ARGS_RE = re.compile(r"\$ARGUMENTS|\$ARG\b")
POSITIONAL_RE = re.compile(r"\$(\d)\b")


AT_FILE_SUFFIXES = (".md", ".txt", ".json", ".py", ".ts", ".tsx", ".js", ".jsx",
                    ".yaml", ".yml", ".toml", ".sh", ".rs", ".go", ".java", ".c",
                    ".h", ".cpp", ".sql", ".csv", ".env", ".cfg", ".ini", ".xml")


def _at_files(text: str, count: bool = False):
    """Заменить `@path/to/file` на `@{path/to/file}` вне защищённых зон.

    Возвращает текст, либо (текст, число замен) при count=True.
    """
    n = 0

    def sub(m: re.Match) -> str:
        nonlocal n
        p = m.group(1)
        if p.lower().endswith(AT_FILE_SUFFIXES) or "/" in p:
            n += 1
            return "@{" + p + "}"
        return m.group(0)

    out = AT_FILE_RE.sub(sub, text)
    return (out, n) if count else out


def _map_hook_matcher(matcher, where: str, rep: Report):
    """Матчер хука CC (имя инструмента или regex `Edit|Write`) -> имена Qwen Code."""
    if not isinstance(matcher, str) or not matcher.strip():
        return matcher
    parts = [p.strip() for p in matcher.split("|")]
    out, changed = [], False
    for part in parts:
        if part in ("", "*", ".*"):
            out.append(part)
            continue
        if part in TOOL_MAP:
            out.append(TOOL_MAP[part])
            changed = True
        elif part in QWEN_TOOLS or part.startswith("mcp__"):
            out.append(part)
        else:
            out.append(part)
    if changed:
        new = "|".join(out)
        rep.warn(where, f"матчер хука `{matcher}` -> `{new}` (имена инструментов Qwen Code)")
        return new
    return matcher


def _fix_hooks(hooks, where: str, rep: Report):
    """Привести блок hooks к Qwen Code: матчеры, env-переменные, таймауты."""
    if not isinstance(hooks, dict):
        return hooks
    fixed: dict = {}
    for event, groups in hooks.items():
        if event not in HOOK_EVENTS_SHARED:
            rep.warn(where, f"событие хука `{event}` не входит в общий набор CC/Qwen — проверьте "
                            f"(в Qwen есть и другие: {', '.join(sorted(HOOK_EVENTS_QWEN_ONLY))})")
        if not isinstance(groups, list):
            fixed[event] = groups
            continue
        new_groups = []
        for g in groups:
            if not isinstance(g, dict):
                new_groups.append(g)
                continue
            g = dict(g)
            if "matcher" in g:
                g["matcher"] = _map_hook_matcher(g["matcher"], where, rep)
            inner = []
            for h in (g.get("hooks") or []):
                if not isinstance(h, dict):
                    inner.append(h)
                    continue
                h = dict(h)
                if isinstance(h.get("timeout"), (int, float)) and h["timeout"] >= 1000:
                    rep.warn(where, f"hooks.{event}: timeout={h['timeout']} прочитается как "
                                    "миллисекунды (обратная совместимость). В Qwen таймаут "
                                    "command-хуков задаётся в секундах — лучше поставить "
                                    f"{int(h['timeout'] // 1000)}")
                if isinstance(h.get("command"), str):
                    cmd = h["command"]
                    orig = cmd
                    for old, new in ENV_VAR_MAP.items():
                        cmd = cmd.replace(old, new)
                    if cmd != orig:
                        rep.warn(where, f"hooks.{event}: $CLAUDE_PROJECT_DIR заменён на "
                                        "$QWEN_PROJECT_DIR (старое имя Qwen Code тоже выставляет)")
                    # скрипты хуков, лежавшие в .claude/, уезжают в .qwen/
                    if ".claude/" in cmd:
                        cmd = cmd.replace(".claude/", ".qwen/")
                        rep.warn(where, f"hooks.{event}: путь .claude/ заменён на .qwen/ — "
                                        f"ПРОВЕРЬТЕ, что скрипт действительно перенесён "
                                        f"(каталог .claude/hooks автоматически не копируется)")
                        rep.add_manual(f"Перенести скрипты хуков из .claude/ в .qwen/ "
                                       f"(в хуке {event} путь уже переписан)")
                    h["command"] = cmd
                inner.append(h)
            if inner or "hooks" not in g:
                g["hooks"] = inner
            new_groups.append(g)
        fixed[event] = new_groups
    return fixed


def convert_body(body: str, where: str, rep: Report) -> str:
    """Claude Code prompt syntax -> Qwen Code prompt syntax."""
    out = body

    # 1) $ARGUMENTS -> {{args}}
    if DOLLAR_ARGS_RE.search(out):
        out = DOLLAR_ARGS_RE.sub("{{args}}", out)
        rep.warn(where, "$ARGUMENTS заменён на {{args}}")

    # 2) позиционные $1 $2 ... -> {{args}}
    pos = sorted(set(POSITIONAL_RE.findall(out)))
    if pos:
        out = POSITIONAL_RE.sub("{{args}}", out)
        nums = ", ".join("$" + p for p in pos)
        rep.warn(
            where,
            "позиционные аргументы " + nums + " заменены на {{args}} — "
            "в Qwen Code нет нумерованных аргументов, опишите формат в тексте команды",
        )

    # 3) !`cmd` -> !{cmd}
    if BACKTICK_BANG_RE.search(out):
        out = BACKTICK_BANG_RE.sub(lambda m: "!{" + m.group(1) + "}", out)
        rep.warn(where, "!`cmd` заменён на !{cmd}")

    # 4) @file -> @{file}. Не трогаем защищённые зоны: содержимое !{...} (это shell-код,
    #    там @ может быть частью команды) и уже сконвертированные @{...}.
    PROTECT = re.compile(r"!\{[^}]*\}|@\{[^}]*\}")
    pieces: list[str] = []
    last = 0
    changed = False
    for m in PROTECT.finditer(out):
        pieces.append(_at_files(out[last:m.start()]))
        pieces.append(m.group(0))
        last = m.end()
    tail, n = _at_files(out[last:], count=True)
    pieces.append(tail)
    if n:
        changed = True
    new_out = "".join(pieces)
    if changed and new_out != out:
        out = new_out
        rep.warn(where, "ссылки @file заменены на @{file} (Qwen Code так inject'ит содержимое)")

    # 5) переменные окружения в командах хуков
    for old, new in ENV_VAR_MAP.items():
        if old in out:
            out = out.replace(old, new)
            rep.warn(where, f"${old} заменён на ${new} (старое имя Qwen Code тоже выставляет)")

    return out


# ---------------------------------------------------------------------------
# Команды
# ---------------------------------------------------------------------------
def convert_command_file(src: Path, dst: Path, rep: Report, dry: bool, cmdname: str = "") -> None:
    text = src.read_text(encoding="utf-8", errors="replace")
    fm, body, had_fm = split_frontmatter(text)
    where = str(src)
    label = f"/{cmdname}" if cmdname else f"/{dst.stem}"

    if not had_fm:
        # TOML-команды старого Qwen или просто текст без frontmatter
        if src.suffix.lower() == ".toml":
            rep.warn(where, "TOML-команды в Qwen Code deprecated — конвертируйте в Markdown "
                            "с YAML frontmatter (подсказка: prompt -> тело, description -> frontmatter)")
            _copy(src, dst, rep, dry)
            return
        new_body = convert_body(text, where, rep)
        _write(dst, new_body.lstrip("\n"), rep, dry)
        rep.done.append(f"{dst}  (команда {label} без frontmatter)")
        return

    # fm is None при наличии frontmatter означает, что разобрать его не удалось:
    # либо не установлен PyYAML, либо YAML невалиден. Раньше здесь стоял assert,
    # и конвертер падал на первом же битом файле вместо внятного предупреждения.
    if fm is None:
        if yaml is None:
            rep.warn(where, "не установлен PyYAML — frontmatter не разобран, файл скопирован как есть. "
                            "Установите: pip install pyyaml")
        else:
            rep.warn(where, "frontmatter есть, но это НЕВАЛИДНЫЙ YAML — файл скопирован без изменений. "
                            "Исправьте синтаксис и запустите конвертацию заново")
            rep.add_manual(f"{src}: исправить невалидный YAML во frontmatter и конвертировать повторно")
        _write(dst, convert_body(text, where, rep), rep, dry)
        return

    new_fm = {}
    for k, v in fm.items():
        kl = str(k).lower()
        if kl in COMMAND_PASSTHROUGH_FIELDS:
            new_fm[kl] = v
        elif kl in COMMAND_UNSUPPORTED_FIELDS:
            rep.warn(where, f"поле `{k}` не поддерживается в Qwen Code: {COMMAND_UNSUPPORTED_FIELDS[kl]}")
        elif kl in ("allowed_tools", "allowedtools"):
            rep.warn(where, f"поле `{k}` (список инструментов) игнорируется: в Qwen Code "
                            "инструменты ограничиваются только у субагентов (tools/disallowedTools)")
        else:
            rep.warn(where, f"неизвестное поле frontmatter `{k}` — перенесено как есть, проверьте")
            new_fm[kl] = v

    new_body = convert_body(body, where, rep)
    content = dump_frontmatter(new_fm) + new_body.lstrip("\n")
    _write(dst, content, rep, dry)
    rep.done.append(f"{dst}  (команда {label})")


# ---------------------------------------------------------------------------
# Субагенты
# ---------------------------------------------------------------------------
def _map_tool_name(t: str, where: str, rep: Report) -> str | None:
    """Один элемент списка tools/disallowedTools -> имя Qwen Code (None = отбросить)."""
    t = str(t).strip()
    if not t:
        return None
    # MCP-паттерны: mcp__server или mcp__server__tool — формат совпадает
    if t.startswith("mcp__"):
        return t
    base = t.split("(")[0].strip()
    if base in TOOL_DROP:
        rep.warn(where, f"инструмент `{t}` отброшен: {TOOL_DROP[base]}. "
                        f"ВАЖНО: если он был в disallowedTools, ограничение снято — "
                        f"перепроверьте список вручную")
        return None
    if t in TOOL_MAP:
        return TOOL_MAP[t]
    if t in QWEN_TOOLS:
        return t
    # wildcard вида Bash(*) -> run_shell_command
    if base in TOOL_MAP:
        rep.warn(where, f"`{t}` -> `{TOOL_MAP[base]}` (уточнение в скобках отброшено: "
                        "Qwen Code не поддерживает такой синтаксис в списках инструментов")
        return TOOL_MAP[base]
    rep.warn(where, f"неизвестный инструмент `{t}` — оставлен как есть, проверьте вручную. "
                    f"Канонические имена: read_file, write_file, edit, run_shell_command, "
                    f"grep_search, glob, list_directory, web_fetch, web_search, agent, todo_write")
    return t


def convert_agent_file(src: Path, dst: Path, rep: Report, dry: bool) -> None:
    text = src.read_text(encoding="utf-8", errors="replace")
    fm, body, had_fm = split_frontmatter(text)
    where = str(src)

    if fm is None:
        if had_fm and yaml is None:
            rep.warn(where, "не установлен PyYAML — frontmatter не разобран, файл скопирован как есть. "
                            "Установите: pip install pyyaml")
        elif had_fm:
            rep.warn(where, "frontmatter есть, но это НЕВАЛИДНЫЙ YAML — файл скопирован без изменений. "
                            "Исправьте синтаксис и запустите конвертацию заново")
            rep.add_manual(f"{src}: исправить невалидный YAML во frontmatter и конвертировать повторно")
        else:
            rep.warn(where, "нет frontmatter — субагент без name/description не запустится")
        _write(dst, convert_body(text, where, rep), rep, dry)
        return

    new_fm: dict = {}

    # name / description
    name = fm.get("name") or src.stem
    new_fm["name"] = str(name)
    if "description" in fm:
        new_fm["description"] = fm["description"]
    else:
        rep.warn(where, "нет `description` — Qwen Code использует его для автоделегирования, добавьте")

    # permissionMode -> approvalMode
    if "permissionMode" in fm:
        pm = str(fm["permissionMode"]).strip()
        mapped = PERMISSION_MODE_MAP.get(pm)
        if mapped:
            new_fm["approvalMode"] = fm.get("approvalMode") or mapped
            if mapped != pm:
                rep.warn(where, f"permissionMode: {pm} -> approvalMode: {mapped}")
        else:
            rep.warn(where, f"неизвестный permissionMode `{pm}` — оставлен как есть")
            new_fm["permissionMode"] = fm["permissionMode"]
    if "approvalMode" in fm:
        new_fm["approvalMode"] = fm["approvalMode"]

    # model
    if "model" in fm:
        m = str(fm["model"]).strip()
        if m in MODEL_MAP:
            new_fm["model"] = MODEL_MAP[m]
            if MODEL_MAP[m] != m:
                rep.warn(where, f"model: {m} -> {MODEL_MAP[m]} "
                                "(в Qwen: inherit | fast | <modelId> | <authType>:<modelId>)")
        elif ":" in m or m == "fast":
            new_fm["model"] = m
        else:
            # имя модели Claude — оставляем, но предупреждаем
            new_fm["model"] = "inherit"
            rep.warn(where, f"model: `{m}` (имя модели Claude) -> inherit; "
                            "укажите конкретный id, если нужна другая модель")

    # tools / disallowedTools
    for field in ("tools", "disallowedTools"):
        if field in fm:
            val = fm[field]
            if isinstance(val, str):
                # CC позволяет строку через запятую
                val = [x.strip() for x in val.split(",") if x.strip()]
            if isinstance(val, list):
                mapped_list, seen = [], set()
                for t in val:
                    nt = _map_tool_name(t, where, rep)
                    if nt and nt not in seen:
                        seen.add(nt)
                        mapped_list.append(nt)
                new_fm[field] = mapped_list
                if mapped_list != list(val):
                    rep.warn(where, f"{field}: {list(val)} -> {mapped_list}")
            else:
                rep.warn(where, f"{field} не список — перенесено как есть")
                new_fm[field] = val

    # нативно поддерживаемые поля CC.
    # `color` здесь намеренно НЕ копируем: он проходит валидацию отдельным блоком
    # ниже (иначе недопустимое значение проскочило бы в выходной файл).
    for field in sorted(AGENT_NATIVE_FIELDS - {"color"}):
        if field in fm:
            new_fm[field] = fm[field]

    # задокументированы, но ещё не реализованы
    for field in sorted(AGENT_PENDING_FIELDS):
        if field in fm:
            new_fm[field] = fm[field]
            rep.warn(where, f"поле `{field}` сохранено, но в Qwen Code оно ещё не реализовано "
                            "(см. docs) — фактически будет проигнорировано")

    # color
    if "color" in fm:
        c = str(fm["color"]).lower()
        if c in AGENT_COLORS or c == "auto":
            new_fm["color"] = c
        else:
            rep.warn(where, f"color `{fm['color']}` вне списка {sorted(AGENT_COLORS)} — отброшен")

    # background / run_in_background
    if "background" in fm:
        new_fm["background"] = fm["background"]
    if "run_in_background" in fm:
        new_fm["run_in_background"] = fm["run_in_background"]

    # executor (ACP/codex) — переносим как есть
    if "executor" in fm:
        new_fm["executor"] = fm["executor"]
        rep.warn(where, "перенесён `executor` (внешний ACP/codex-агент): для claude-agent-acp "
                        "нужен установленный и аутентифицированный Claude Code, для codex — "
                        "исполняемый файл codex в PATH. Windows нативно не поддерживается.")

    # всё остальное — с предупреждением.
    # ВАЖНО: сюда должны входить ВСЕ ключи, которые мы уже разобрали выше,
    # иначе отброшенное значение (например недопустимый color) вернётся обратно.
    known = {"name", "description", "permissionMode", "approvalMode", "model", "tools",
             "disallowedTools", "color", "background", "run_in_background", "executor",
             "disable-model-invocation", "user-invocable", "allowed-tools", "argument-hint",
             *AGENT_NATIVE_FIELDS, *AGENT_PENDING_FIELDS}
    # Безобидные метаданные из чужих наборов. Qwen Code их просто игнорирует,
    # поэтому предупреждаем один раз на все файлы, а не по разу на каждое поле:
    # иначе установка набора из 30 агентов тонет в бессмысленном шуме.
    meta: list[str] = []
    for k, v in fm.items():
        if k in known or k in new_fm:
            continue
        if k.lower() in HARMLESS_METADATA_FIELDS:
            new_fm[k] = v
            meta.append(k)
        else:
            new_fm[k] = v
            rep.warn(where, f"неизвестное поле `{k}` перенесено как есть")
    if meta:
        rep.meta_fields.update(meta)

    # env-переменные и матчеры внутри hooks во frontmatter
    if "hooks" in new_fm:
        new_fm["hooks"] = _fix_hooks(new_fm["hooks"], where, rep)

    new_body = convert_body(body, where, rep)
    _write(dst, dump_frontmatter(new_fm) + new_body.lstrip("\n"), rep, dry)
    rep.done.append(f"{dst}  (субагент {new_fm.get('name')})")


# ---------------------------------------------------------------------------
# Файлы памяти
# ---------------------------------------------------------------------------
def convert_memory_file(src: Path, project: Path, rep: Report, dry: bool) -> None:
    text = src.read_text(encoding="utf-8", errors="replace")
    where = src.name
    body = convert_body(text, where, rep)

    # упоминания самого Claude
    n = len(re.findall(r"\bClaude Code\b", body))
    if n:
        body = re.sub(r"\bClaude Code\b", "Qwen Code", body)
        rep.warn(where, f"«Claude Code» заменён на «Qwen Code» ({n} шт.) — проверьте контекст")
    n2 = len(re.findall(r"\bCLAUDE\.md\b", body))
    if n2:
        body = body.replace("CLAUDE.md", "QWEN.md")
        rep.warn(where, f"упоминания CLAUDE.md заменены на QWEN.md ({n2} шт.)")
    n3 = len(re.findall(r"\.claude/", body))
    if n3:
        body = body.replace(".claude/", ".qwen/")
        rep.warn(where, f"пути .claude/ заменены на .qwen/ ({n3} шт.)")

    if src.name == "CLAUDE.local.md":
        dst = project / QWEN_DIR / "QWEN.local.md"
        gi = project / ".gitignore"
        if not dry:
            existing = gi.read_text(encoding="utf-8") if gi.exists() else ""
            if ".qwen/QWEN.local.md" not in existing:
                with gi.open("a", encoding="utf-8") as fh:
                    fh.write(("\n" if existing and not existing.endswith("\n") else "")
                             + "# qwenkit: личные инструкции не коммитим\n.qwen/QWEN.local.md\n")
                rep.done.append(f"{gi}  (добавлено .qwen/QWEN.local.md)")
        rep.warn(where, "Qwen Code НЕ создаёт .gitignore сам — правило добавлено в .gitignore")
    else:
        dst = project / "QWEN.md"

    _write(dst, body, rep, dry)
    rep.done.append(f"{dst}  (файл памяти)")


# ---------------------------------------------------------------------------
# settings.json / .mcp.json
# ---------------------------------------------------------------------------
def convert_settings(src: Path, dst: Path, rep: Report, dry: bool) -> None:
    where = str(src)
    try:
        data = json.loads(src.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:                                      # noqa: BLE001
        rep.warn(where, f"не удалось разобрать JSON ({e}) — файл не перенесён")
        rep.add_manual(f"Разобрать {src} вручную: {e}")
        return
    if not isinstance(data, dict):
        rep.warn(where, "JSON не объект — пропущено")
        return

    out: dict = {}
    for key in SETTINGS_AUTO_KEYS:
        if key in data:
            out[key] = data[key]

    # env-переменные $CLAUDE_PROJECT_DIR во всём файле (env-блок, команды хуков и т.д.)
    raw_all = json.dumps(out, ensure_ascii=False)
    fixed_all = raw_all
    for old, new in ENV_VAR_MAP.items():
        fixed_all = fixed_all.replace(old, new)
    if fixed_all != raw_all:
        out = json.loads(fixed_all)
        rep.warn(where, "$CLAUDE_PROJECT_DIR заменён на $QWEN_PROJECT_DIR "
                        "(Qwen Code выставляет оба имени, так что старый вариант тоже работал бы)")

    # hooks: матчеры, события, таймауты — одной функцией с субагентскими хуками
    if "hooks" in out:
        out["hooks"] = _fix_hooks(out["hooks"], where, rep)

    # permissions и прочее -> ручные задачи
    for key, hint in SETTINGS_MANUAL_KEYS.items():
        if key in data and key not in SETTINGS_AUTO_KEYS:
            rep.add_manual(f"settings.json → `{key}`: {hint}")

    unknown = set(data) - set(SETTINGS_AUTO_KEYS) - set(SETTINGS_MANUAL_KEYS)
    for key in sorted(unknown):
        out[key] = data[key]
        rep.warn(where, f"ключ `{key}` перенесён как есть — сверьте с docs/users/configuration/settings.md")

    if not out:
        rep.skipped.append(f"{src} (нечего переносить автоматически)")
        return

    merged: dict = {}
    if dst.exists():
        try:
            merged = json.loads(dst.read_text(encoding="utf-8"))
        except Exception:                                       # noqa: BLE001
            merged = {}
    # существующие значения dst имеют приоритет для скаляров, словари объединяем
    for k, v in out.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k] = {**v, **merged[k]}
        elif k not in merged:
            merged[k] = v

    _write_json(dst, merged, rep, dry)
    rep.done.append(f"{dst}  (settings: {', '.join(sorted(out))})")


def convert_mcp_json(src: Path, dst: Path, rep: Report, dry: bool) -> None:
    """`.mcp.json` у Claude Code и Qwen Code одинаковый по форме (mcpServers)."""
    where = str(src)
    try:
        data = json.loads(src.read_text(encoding="utf-8", errors="replace"))
    except Exception as e:                                      # noqa: BLE001
        rep.warn(where, f"не удалось разобрать JSON ({e})")
        return
    servers = data.get("mcpServers", data if "command" in data else {})
    if not servers:
        rep.skipped.append(f"{src} (нет mcpServers)")
        return
    raw = json.dumps(servers, ensure_ascii=False)
    for old, new in ENV_VAR_MAP.items():
        raw = raw.replace(old, new)
    servers = json.loads(raw)

    merged: dict = {}
    if dst.exists():
        try:
            merged = json.loads(dst.read_text(encoding="utf-8")).get("mcpServers", {})
        except Exception:                                       # noqa: BLE001
            merged = {}
    merged = {**servers, **merged}
    _write_json(dst, {"mcpServers": merged}, rep, dry)
    rep.done.append(f"{dst}  ({len(servers)} MCP-сервер(ов): {', '.join(sorted(servers))})")
    rep.warn(where, "MCP-серверы продублированы в .qwen/.mcp.json; Qwen Code также читает "
                    "mcpServers из .qwen/settings.json — оставьте одно место, чтобы не плодить копии")


# ---------------------------------------------------------------------------
# Запись / бэкап
# ---------------------------------------------------------------------------
def _backup_dir(project: Path) -> Path:
    return project / f".qwen-backup-{_dt.datetime.now().strftime('%Y%m%d-%H%M%S')}"


def _write(dst: Path, content: str, rep: Report, dry: bool) -> None:
    if dry:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        bk = _backup_dir(dst.parent) / dst.name
        bk.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), str(bk))
        rep.warn(str(dst), f"существовавший файл перемещён в {bk}")
    dst.write_text(content, encoding="utf-8")


def _write_json(dst: Path, data: dict, rep: Report, dry: bool) -> None:
    _write(dst, json.dumps(data, ensure_ascii=False, indent=2) + "\n", rep, dry)


def _copy(src: Path, dst: Path, rep: Report, dry: bool) -> None:
    if dry:
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


# ---------------------------------------------------------------------------
# Обход проекта
# ---------------------------------------------------------------------------
IGNORE_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".idea", ".vscode",
               "dist", "build", ".qwen-backup", ".claude-backup", ".next", ".cache"}


def find_claude_roots(project: Path) -> list[Path]:
    """Корни, где есть что конвертировать: сам проект + вложенные (монорепо)."""
    roots = []
    if (project / CLAUDE_DIR).exists() or (project / "CLAUDE.md").exists() or (project / ".mcp.json").exists():
        roots.append(project)
    for dirpath, dirnames, filenames in os.walk(project):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".qwen-backup")]
        p = Path(dirpath)
        if p == project:
            continue
        if (p / CLAUDE_DIR).exists() or "CLAUDE.md" in filenames or ".mcp.json" in filenames:
            roots.append(p)
    return roots


def convert_root(root: Path, rep: Report, dry: bool) -> None:
    cdir = root / CLAUDE_DIR
    qdir = root / QWEN_DIR

    # 1. файлы памяти
    for src_name in MEMORY_FILES:
        src = root / src_name
        if src.exists():
            convert_memory_file(src, root, rep, dry)
        local = cdir / src_name
        if local.exists():
            convert_memory_file(local, root, rep, dry)

    # 2. команды
    ccmd = cdir / "commands"
    if ccmd.is_dir():
        files = sorted(p for p in ccmd.rglob("*") if p.is_file() and p.suffix.lower() in (".md", ".toml", ".txt"))
        for src in files:
            rel = src.relative_to(ccmd)
            # .qwen/commands/git/commit.md -> /git:commit
            cmdname = str(rel.with_suffix("")).replace(os.sep, ":")
            convert_command_file(src, qdir / "commands" / rel, rep, dry, cmdname)
        if not files:
            rep.skipped.append(f"{ccmd} (пусто)")
    # команды также могут лежать в ~/.claude/commands — их обрабатывает --global

    # 3. субагенты
    cag = cdir / "agents"
    if cag.is_dir():
        files = sorted(p for p in cag.rglob("*.md"))
        for src in files:
            rel = src.relative_to(cag)
            convert_agent_file(src, qdir / "agents" / rel, rep, dry)
        if not files:
            rep.skipped.append(f"{cag} (пусто)")

    # 4. settings
    for name in ("settings.json", "settings.local.json"):
        src = cdir / name
        if src.exists():
            convert_settings(src, qdir / name, rep, dry)

    # 5. .mcp.json
    mcp = root / ".mcp.json"
    if mcp.exists():
        convert_mcp_json(mcp, qdir / ".mcp.json", rep, dry)

    # 6. прочие каталоги .claude, которые стоит перенести вручную
    if cdir.is_dir():
        for sub in sorted(p.name for p in cdir.iterdir() if p.is_dir()):
            if sub not in {"commands", "agents"}:
                rep.add_manual(f"{cdir / sub}/ — каталог не конвертируется автоматически "
                               f"(в Qwen Code нет прямого аналога); при необходимости перенесите в {qdir}/")
        for f in sorted(p.name for p in cdir.iterdir() if p.is_file()):
            if f not in MEMORY_FILES and f not in ("settings.json", "settings.local.json"):
                rep.add_manual(f"{cdir / f} — файл не перенесён автоматически")


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="qwenkit convert",
        description="Конвертировать проект Claude Code в формат Qwen Code",
    )
    ap.add_argument("path", nargs="?", default=".", help="корень проекта (по умолчанию текущий каталог)")
    ap.add_argument("--global", dest="global_", action="store_true",
                    help="конвертировать ~/.claude (commands, agents, CLAUDE.md, settings.json) в ~/.qwen")
    ap.add_argument("--dry-run", action="store_true", help="только показать, что будет сделано")
    ap.add_argument("--no-report", action="store_true", help="не создавать MIGRATION_TODO.md")
    args = ap.parse_args(argv)

    if yaml is None:
        print(f"{C_YEL}!{C_RESET} PyYAML не установлен — frontmatter не будет разобран. "
              f"Установите: {C_BOLD}pip install pyyaml{C_RESET}", file=sys.stderr)

    rep = Report()
    targets: list[Path] = []

    if args.global_:
        home = Path.home()
        targets.append(home)
        print(f"{C_BOLD}Глобальная конвертация:{C_RESET} {home / CLAUDE_DIR} -> {home / QWEN_DIR}")
    else:
        project = Path(args.path).expanduser().resolve()
        if not project.is_dir():
            print(f"{C_RED}ошибка:{C_RESET} нет каталога {project}", file=sys.stderr)
            return 2
        roots = find_claude_roots(project)
        if not roots:
            print(f"{C_YEL}В {project} не найдено ничего от Claude Code{C_RESET} "
                  f"(ожидал: CLAUDE.md, {CLAUDE_DIR}/ или .mcp.json).")
            print("Подсказка: `qwenkit convert --global` конвертирует ~/.claude")
            return 1
        targets = roots
        print(f"{C_BOLD}Проект:{C_RESET} {project}")
        if len(roots) > 1:
            print(f"  найдено корней с конфигурацией Claude Code: {len(roots)} (монорепо)")

    if args.dry_run:
        print(f"{C_YEL}--- DRY RUN: файлы не изменяются ---{C_RESET}")

    for t in targets:
        convert_root(t, rep, args.dry_run)

    if not args.dry_run and not args.no_report and targets:
        todo = targets[0] / "MIGRATION_TODO.md"
        rep.write_todo(todo)
        if rep.manual or rep.warnings:
            rep.done.append(f"{todo}  (отчёт)")

    rep.print_summary()
    if not rep.done:
        print(f"\n{C_YEL}Нечего конвертировать.{C_RESET}")
    print(f"\nДальше: {C_BOLD}qwenkit doctor{C_RESET} — проверить окружение, "
          f"{C_BOLD}qwenkit setup{C_RESET} — подключить бесплатный API.")
    return 0
