"""`qwenkit install` — установка чужих наборов команд и агентов с GitHub.

Схема работы (экономит лимиты GitHub API):
  1. ОДИН запрос к git/trees?recursive=1 — получаем список всех файлов репо.
  2. Классифицируем пути: агенты, команды, MCP, память, хуки, прочее.
  3. Скачиваем нужные файлы с raw.githubusercontent.com — этот хост
     НЕ тратит лимит api.github.com (60 запросов/час без токена).
  4. Конвертируем формат Claude Code -> Qwen Code тем же кодом, что и `convert`.
  5. Ставим в ~/.qwen или ./.qwen и пишем манифест для `qwenkit uninstall`.

Поддерживаемые адреса:
  owner/repo
  https://github.com/owner/repo
  https://github.com/owner/repo/tree/main
  https://github.com/owner/repo/tree/v1.2.0/agents
  https://github.com/owner/repo/tree/main/some/dir
  https://github.com/owner/repo/blob/main/agents/foo.md
  https://raw.githubusercontent.com/owner/repo/main/agents/foo.md
"""

from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import re
import shutil
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from .convert import (
    Report,
    convert_agent_file,
    convert_command_file,
    convert_mcp_json,
    convert_settings,
)
from .maps import CLAUDE_DIR

C_RESET = C_RED = C_GRN = C_YEL = C_DIM = C_BOLD = ""
if sys.stdout.isatty():
    C_RESET, C_RED, C_GRN = "\033[0m", "\033[31m", "\033[32m"
    C_YEL, C_DIM, C_BOLD = "\033[33m", "\033[2m", "\033[1m"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

MANIFEST_NAME = ".qwenkit-installed.json"
MAX_FILE_BYTES = 400_000          # не качаем подозрительно большое
MAX_FILES = 300                   # предохранитель от безумных репозиториев


# ---------------------------------------------------------------------------
# Разбор адреса
# ---------------------------------------------------------------------------
class RepoRef:
    def __init__(self, owner: str, repo: str, ref: str = "HEAD", subdir: str = "",
                 single_file: str = "") -> None:
        self.owner = owner
        self.repo = repo
        self.ref = ref
        self.subdir = subdir.strip("/")
        self.single_file = single_file

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repo}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"

    def __str__(self) -> str:
        s = self.slug
        if self.ref and self.ref != "HEAD":
            s += f"@{self.ref}"
        if self.subdir:
            s += f"/{self.subdir}"
        if self.single_file:
            s += f" -> {self.single_file}"
        return s


_URL_RE = re.compile(
    r"github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"(?:/(?P<kind>tree|blob)/(?P<ref>[^/]+)(?:/(?P<path>.*))?)?"
)


def parse_target(target: str) -> RepoRef:
    """Разобрать то, что ввёл пользователь, в RepoRef."""
    t = target.strip().rstrip("/")

    # raw.githubusercontent.com/owner/repo/ref/path
    if "raw.githubusercontent.com" in t:
        parts = urllib.parse.urlparse(t if "://" in t else "https://" + t).path.strip("/").split("/")
        if len(parts) >= 4:
            owner, repo, ref = parts[0], parts[1], parts[2]
            path = "/".join(parts[3:])
            return RepoRef(owner, repo, ref,
                           single_file=path if path.endswith(".md") else "",
                           subdir="" if path.endswith(".md") else str(Path(path).parent))
        raise ValueError(f"не удалось разобрать raw-ссылку: {target}")

    m = _URL_RE.search(t)
    if m:
        owner, repo = m.group("owner"), m.group("repo").removesuffix(".git")
        kind, ref, path = m.group("kind"), m.group("ref"), m.group("path") or ""
        path = path.strip("/")
        if kind == "blob" and path:
            return RepoRef(owner, repo, ref, single_file=path)
        if kind == "tree" and ref:
            if path.endswith(".md"):
                return RepoRef(owner, repo, ref, single_file=path)
            return RepoRef(owner, repo, ref, subdir=path)
        return RepoRef(owner, repo, "HEAD", subdir=path)

    # owner/repo[/подкаталог]
    if re.fullmatch(r"[\w.\-]+/[\w.\-]+(/[\w./\-]+)?", t):
        parts = t.split("/")
        subdir = "/".join(parts[2:]) if len(parts) > 2 else ""
        return RepoRef(parts[0], parts[1], "HEAD", subdir=subdir)

    raise ValueError(
        f"не понял адрес «{target}». Примеры того, что принимается:\n"
        f"  owner/repo\n"
        f"  https://github.com/owner/repo\n"
        f"  https://github.com/owner/repo/tree/main/agents\n"
        f"  https://github.com/owner/repo/blob/main/agents/foo.md"
    )


# ---------------------------------------------------------------------------
# Сеть
# ---------------------------------------------------------------------------
def _gh(url: str, timeout: int = 30) -> tuple[bytes, dict]:
    headers = {
        "User-Agent": "qwenkit/1.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    r = urllib.request.urlopen(req, timeout=timeout, context=_CTX)
    return r.read(), dict(r.headers)


def list_files(rr: RepoRef) -> list[str]:
    """Список путей файлов репозитория. ОДИН запрос к API."""
    if rr.single_file:
        return [rr.single_file]
    url = f"https://api.github.com/repos/{rr.slug}/git/trees/{urllib.parse.quote(rr.ref, safe='')}?recursive=1"
    try:
        raw, hdr = _gh(url)
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "ignore")[:200]
        except Exception:                                          # noqa: BLE001
            pass
        if e.code == 404:
            raise SystemExit(f"{C_RED}Репозиторий или ветка не найдены:{C_RESET} {rr.slug}@{rr.ref}\n"
                             f"Проверьте адрес. Ответ: {body}") from None
        if e.code in (403, 429):
            raise SystemExit(
                f"{C_RED}GitHub отклонил запрос (HTTP {e.code}).{C_RESET}\n"
                f"Скорее всего, исчерпан лимит 60 запросов/час для анонимного доступа.\n"
                f"Решение: export GITHUB_TOKEN=<ваш токен> — лимит станет 5000/час.\n"
                f"Создать токен (без прав, public repo достаточно): "
                f"https://github.com/settings/tokens\n{C_DIM}{body}{C_RESET}") from None
        raise SystemExit(f"{C_RED}Ошибка GitHub API (HTTP {e.code}):{C_RESET} {body}") from None

    data = json.loads(raw)
    if data.get("truncated"):
        print(f"  {C_YEL}!{C_RESET} список файлов обрезан GitHub (репозиторий очень большой) — "
              f"установятся не все наборы")
    paths = [t["path"] for t in data.get("tree", []) if t.get("type") == "blob"]
    remaining = (hdr.get("X-RateLimit-Remaining") or "?")
    print(f"  {C_DIM}файлов в репозитории: {len(paths)} (лимит API осталось: {remaining}){C_RESET}")
    return paths


def fetch_file(rr: RepoRef, path: str) -> bytes | None:
    """Скачать файл. raw.githubusercontent не тратит лимит API."""
    ref = rr.ref if rr.ref != "HEAD" else "HEAD"
    url = (f"https://raw.githubusercontent.com/{rr.owner}/{rr.repo}/"
           f"{urllib.parse.quote(ref)}/{urllib.parse.quote(path)}")
    try:
        raw, _ = _gh(url, timeout=40)
        if len(raw) > MAX_FILE_BYTES:
            return None
        return raw
    except urllib.error.HTTPError:
        pass
    except Exception:                                              # noqa: BLE001
        return None

    # fallback: contents API (тратит лимит, поэтому только если raw не сработал)
    try:
        url2 = (f"https://api.github.com/repos/{rr.slug}/contents/{urllib.parse.quote(path)}"
                f"?ref={urllib.parse.quote(ref)}")
        raw, _ = _gh(url2)
        data = json.loads(raw)
        if data.get("encoding") == "base64" and data.get("content"):
            return base64.b64decode(data["content"])
    except Exception:                                              # noqa: BLE001
        pass
    return None


# ---------------------------------------------------------------------------
# Классификация
# ---------------------------------------------------------------------------
def classify(path: str) -> str | None:
    """Определить тип файла по пути. None = не интересно."""
    p = path.replace("\\", "/").lower()
    parts = p.split("/")
    name = parts[-1]

    if not name.endswith((".md", ".json", ".toml")):
        return None
    # явный мусор
    if any(x in name for x in ("changelog", "license", "readme", "contributing",
                               "code_of_conduct", "security.md")):
        return None

    # агенты
    if name.endswith(".md") and re.search(r"(^|/)agents?/", p):
        return "agent"
    if name.endswith(".md") and re.search(r"(^|/)subagents?/", p):
        return "agent"
    # команды
    if name.endswith((".md", ".toml")) and re.search(r"(^|/)commands?/", p):
        return "command"
    # память
    if name in ("claude.md", "qwen.md", "agents.md"):
        return "memory"
    if name.endswith(".md") and re.search(r"(^|/)memory/", p):
        return "memory"
    # mcp
    if name in (".mcp.json", "mcp.json"):
        return "mcp"
    # settings
    if name == "settings.json" and CLAUDE_DIR in p:
        return "settings"
    if name == "settings.json" and re.search(r"(^|/)\.qwen/", p):
        return "settings"
    return None


def plan_install(paths: list[str], subdir: str = "",
                 kinds: set[str] | None = None) -> dict[str, list[str]]:
    """Сгруппировать пути по типам. Чистая функция — на ней стоят тесты."""
    kinds = kinds or {"agent", "command", "mcp", "settings", "memory"}
    out: dict[str, list[str]] = {}
    prefix = (subdir.strip("/") + "/") if subdir else ""
    for p in paths:
        if prefix and not p.startswith(prefix):
            continue
        kind = classify(p)
        if kind and kind in kinds:
            out.setdefault(kind, []).append(p)
    for v in out.values():
        v.sort()
    return out


# ---------------------------------------------------------------------------
# Определение типа по содержимому (fallback)
# ---------------------------------------------------------------------------
# Крупные наборы хранят агентов где угодно: `categories/01-core/x.md`,
# `subagents/x.md`, `prompts/x.md`. Путь не всегда говорит правду, поэтому
# при слабом результате смотрим внутрь frontmatter.
SKIP_NAMES = {
    "readme.md", "contributing.md", "changelog.md", "license", "license.md",
    "code_of_conduct.md", "security.md", "install.md", "installation.md",
    "index.md", "overview.md", "agents.md", "claude.md", "qwen.md",
    "pull_request_template.md", "issue_template.md",
}
CONTENT_SCAN_LIMIT = 250        # предохранитель: не качать сотни файлов


def _candidates(paths: list[str], subdir: str = "") -> list[str]:
    """`.md`-файлы, которые имеет смысл открыть и посмотреть."""
    prefix = (subdir.strip("/") + "/") if subdir else ""
    out = []
    for p in paths:
        if prefix and not p.startswith(prefix):
            continue
        if not p.lower().endswith(".md"):
            continue
        name = p.rsplit("/", 1)[-1].lower()
        if name in SKIP_NAMES:
            continue
        low = p.lower()
        if any(x in low for x in ("/.github/", "/docs/", "/node_modules/", "/test",
                                  "/examples/", "/templates/", "/assets/")):
            continue
        out.append(p)
    return out[:CONTENT_SCAN_LIMIT]


def looks_like_agent(fm: dict) -> bool:
    """По frontmatter понять, что это определение субагента.

    Признаки агента Claude Code / Qwen Code: есть name+description и хотя бы
    одно из полей агента (tools, model, permissionMode, approvalMode, color,
    maxTurns, disallowedTools). Плюс «голый» агент: только name+description
    и безобидные метаданные.

    Поля `allowed-tools` и `argument-hint` — признак КОМАНДЫ, а не агента,
    поэтому перевешивают «голое» правило name+description.
    """
    if not isinstance(fm, dict):
        return False
    if not fm.get("name") or not fm.get("description"):
        return False
    agent_fields = {"tools", "disallowedTools", "model", "permissionMode",
                    "approvalMode", "color", "maxTurns", "mcpServers", "hooks",
                    "executor", "isolation", "effort", "skills",
                    "run_in_background", "background"}
    if agent_fields & set(fm):
        return True
    # явные признаки команды
    if {"allowed-tools", "allowed_tools", "argument-hint"} & set(fm):
        return False
    # только name+description плюс безобидные метаданные — считаем агентом
    from .maps import HARMLESS_METADATA_FIELDS
    return set(fm) <= ({"name", "description"} | HARMLESS_METADATA_FIELDS)


def detect_by_content(rr: RepoRef, paths: list[str], subdir: str = "") -> dict[str, list[str]]:
    """Параллельно скачать кандидаты и классифицировать по frontmatter."""
    import concurrent.futures as cf

    try:
        from .convert import split_frontmatter
    except Exception:                                              # noqa: BLE001
        return {}

    cands = _candidates(paths, subdir)
    if not cands:
        return {}
    print(f"  {C_DIM}путь не дал зацепок — смотрю внутрь {len(cands)} .md-файлов…{C_RESET}")

    found: dict[str, list[str]] = {}

    def inspect(path: str) -> tuple[str, str | None]:
        data = fetch_file(rr, path)
        if not data:
            return path, None
        try:
            fm, body, had = split_frontmatter(data.decode("utf-8", "replace"))
        except Exception:                                          # noqa: BLE001
            return path, None
        if not had or not isinstance(fm, dict):
            return path, None
        if looks_like_agent(fm):
            return path, "agent"
        # команда: есть description и тело-промпт с подстановками
        if fm.get("description") and not fm.get("name"):
            if any(tok in body for tok in ("{{args}}", "$ARGUMENTS", "!{", "!`", "@{")):
                return path, "command"
            if len(body.strip()) > 120:
                return path, "command"
        return path, None

    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for path, kind in ex.map(inspect, cands):
            if kind:
                found.setdefault(kind, []).append(path)
    for v in found.values():
        v.sort()
    return found


def plan_install_auto(paths: list[str], rr: RepoRef | None = None, subdir: str = "",
                      kinds: set[str] | None = None) -> dict[str, list[str]]:
    """plan_install + определение по содержимому, если по путям нашлось мало."""
    plan = plan_install(paths, subdir, kinds)
    rich = len(plan.get("agent", [])) + len(plan.get("command", []))
    if rich >= 3 or rr is None:
        return plan
    kinds2 = kinds or {"agent", "command", "mcp", "settings", "memory"}
    if not ({"agent", "command"} & kinds2):
        return plan
    extra = detect_by_content(rr, paths, subdir)
    for kind, files in extra.items():
        if kind not in kinds2:
            continue
        cur = set(plan.get(kind, []))
        cur.update(files)
        plan[kind] = sorted(cur)
    return plan


# ---------------------------------------------------------------------------
# Установка
# ---------------------------------------------------------------------------
def _load_manifest(base: Path) -> dict:
    f = base / MANIFEST_NAME
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:                                          # noqa: BLE001
            return {}
    return {}


def _save_manifest(base: Path, manifest: dict) -> None:
    base.mkdir(parents=True, exist_ok=True)
    (base / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dest_name(path: str, subdir: str, kind: str, keep_parent: bool = False) -> str:
    """Относительное имя файла внутри .qwen/agents или .qwen/commands.

    Отрезаем всё до каталога agents/ или commands/, чтобы вложенная структура
    репозитория не тащила за собой мусор вроде `awesome-pack/v2/src/agents/`.

    Если якоря нет (набор хранит агентов в `categories/01-core/x.md`), берём
    имя файла; при keep_parent добавляем родительский каталог как пространство
    имён — иначе одноимённые агенты из разных разделов перезатрут друг друга.
    """
    norm = path.replace("\\", "/")
    if subdir:
        pref = subdir.strip("/") + "/"
        if norm.startswith(pref):
            norm = norm[len(pref):]
    for anchor in ("agents/", "agent/", "subagents/", "commands/", "command/"):
        idx = norm.rfind(anchor)
        if idx >= 0:
            return norm[idx + len(anchor):]
    if keep_parent and "/" in norm:
        return norm
    return Path(norm).name


def _resolve_collisions(items: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """(path, dest) -> (path, dest) без конфликтов имён.

    При совпадении имён добавляем родительский каталог как префикс.
    """
    counts: dict[str, int] = {}
    for _, dest in items:
        counts[dest] = counts.get(dest, 0) + 1
    dup = {d for d, c in counts.items() if c > 1}
    if not dup:
        return items
    out = []
    seen: set[str] = set()
    for path, dest in items:
        if dest in dup:
            parts = path.replace("\\", "/").split("/")
            dest = "/".join(parts[-2:]) if len(parts) > 1 else dest
        n = 2
        base = dest
        while dest in seen:
            dest = f"{Path(base).stem}-{n}{Path(base).suffix}"
            n += 1
        seen.add(dest)
        out.append((path, dest))
    return out


def install(rr: RepoRef, base: Path, kinds: set[str], dry: bool,
            overwrite: bool, prefix: str) -> Report:
    rep = Report()
    paths = list_files(rr)
    plan = plan_install_auto(paths, rr, rr.subdir, kinds)

    if not plan:
        print(f"\n  {C_YEL}В {rr} не найдено ни агентов, ни команд Claude Code.{C_RESET}")
        print(f"  {C_DIM}Подсказки:{C_RESET}")
        print(f"    · посмотрите структуру: https://github.com/{rr.slug}/tree/{rr.ref}"
              + (f"/{rr.subdir}" if rr.subdir else ""))
        print(f"    · укажите подкаталог явно: qwenkit install {rr.slug}/путь/к/папке")
        print(f"    · наборы ищутся в каталогах agents/ и commands/ (файлы .md/.toml)")
        return rep

    total = sum(len(v) for v in plan.values())
    if total > MAX_FILES:
        print(f"  {C_YEL}!{C_RESET} найдено файлов: {total} — больше предохранителя {MAX_FILES}. "
              f"Уточните подкаталог.")
        for k in plan:
            plan[k] = plan[k][:MAX_FILES]

    # имена назначения считаем заранее, чтобы разрулить совпадения
    dest_map: dict[tuple[str, str], str] = {}
    for kind in ("agent", "command"):
        files = plan.get(kind) or []
        if not files:
            continue
        items = [(f, _dest_name(f, rr.subdir, kind)) for f in files]
        for f, dest in _resolve_collisions(items):
            dest_map[(kind, f)] = dest

    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"qwenkit-dl-{os.getpid()}"
    tmp.mkdir(parents=True, exist_ok=True)
    manifest = _load_manifest(base)
    entry = manifest.setdefault(rr.slug, {
        "ref": rr.ref, "installed": [], "url": f"https://github.com/{rr.slug}",
        "date": _dt.datetime.now().isoformat(timespec="seconds"),
    })
    entry["date"] = _dt.datetime.now().isoformat(timespec="seconds")
    entry["ref"] = rr.ref

    try:
        print(f"\n  {C_BOLD}Установка из {rr}{C_RESET}  {C_DIM}→ {base}{C_RESET}")
        for kind in ("agent", "command", "mcp", "settings", "memory"):
            files = plan.get(kind) or []
            if not files:
                continue
            label = {"agent": "субагенты", "command": "команды", "mcp": "MCP-серверы",
                     "settings": "настройки", "memory": "файлы памяти"}[kind]
            print(f"\n  {C_BOLD}{label}: {len(files)}{C_RESET}")
            for path in files:
                data = fetch_file(rr, path)
                if data is None:
                    print(f"    {C_RED}✗{C_RESET} {path} {C_DIM}(не удалось скачать){C_RESET}")
                    rep.warn(path, "файл не скачался — пропущен")
                    continue
                text = data.decode("utf-8", "replace")
                src = tmp / Path(path).name
                src.write_text(text, encoding="utf-8")

                if kind == "agent":
                    rel = prefix + dest_map[(kind, path)]
                    dst = base / "agents" / rel
                    if dst.exists() and not overwrite:
                        print(f"    {C_DIM}· {rel} уже существует (--overwrite чтобы заменить){C_RESET}")
                        continue
                    if dry:
                        print(f"    {C_GRN}+{C_RESET} {C_DIM}(dry){C_RESET} agents/{rel}")
                        continue
                    convert_agent_file(src, dst, rep, False)
                    print(f"    {C_GRN}+{C_RESET} agents/{rel}")
                    entry["installed"].append(f"agents/{rel}")

                elif kind == "command":
                    rel = prefix + dest_map[(kind, path)]
                    dst = base / "commands" / rel
                    if dst.exists() and not overwrite:
                        print(f"    {C_DIM}· {rel} уже существует (--overwrite чтобы заменить){C_RESET}")
                        continue
                    if dry:
                        print(f"    {C_GRN}+{C_RESET} {C_DIM}(dry){C_RESET} commands/{rel}")
                        continue
                    cmdname = str(Path(rel).with_suffix("")).replace(os.sep, ":")
                    convert_command_file(src, dst, rep, False, cmdname)
                    print(f"    {C_GRN}+{C_RESET} commands/{rel}  {C_DIM}/{cmdname}{C_RESET}")
                    entry["installed"].append(f"commands/{rel}")

                elif kind == "mcp":
                    dst = base / ".mcp.json"
                    print(f"    {C_YEL}!{C_RESET} {path}: MCP-серверы будет слиты в {dst}")
                    if not dry:
                        convert_mcp_json(src, dst, rep, False)
                        entry["installed"].append(".mcp.json")
                    print(f"    {C_DIM}      ОБЯЗАТЕЛЬНО проверьте, какие команды запускаются{C_RESET}")

                elif kind == "settings":
                    print(f"    {C_YEL}!{C_RESET} {path}: чужие настройки — НЕ устанавливаю автоматически")
                    rep.add_manual(
                        f"Посмотреть вручную {rr.url}/blob/{rr.ref}/{path} — там могут быть "
                        f"хуки, которые запускают произвольные команды на вашей машине")

                elif kind == "memory":
                    print(f"    {C_YEL}!{C_RESET} {path}: чужой файл памяти — НЕ подмешиваю в ваш QWEN.md")
                    if not dry:
                        out = base / "imported-notes" / (prefix + Path(path).name)
                        out.parent.mkdir(parents=True, exist_ok=True)
                        out.write_text(text, encoding="utf-8")
                        print(f"    {C_DIM}      сохранён для просмотра: {out}{C_RESET}")
                        entry["installed"].append(str(out.relative_to(base)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if not dry:
        entry["installed"] = sorted(set(entry["installed"]))
        _save_manifest(base, manifest)

    return rep


def uninstall(slug: str, base: Path, dry: bool) -> int:
    manifest = _load_manifest(base)
    if not manifest:
        print(f"  {C_YEL}Манифест установок пуст: {base / MANIFEST_NAME}{C_RESET}")
        return 1
    if slug == "--all":
        targets = list(manifest)
    else:
        targets = [s for s in manifest if s.lower() == slug.lower()]
        if not targets:
            print(f"  {C_RED}Не найдено:{C_RESET} {slug}")
            print(f"  Установлено: {', '.join(sorted(manifest))}")
            return 1
    removed = 0
    for t in targets:
        files = manifest[t].get("installed", [])
        print(f"\n  {C_BOLD}{t}{C_RESET}: {len(files)} файл(ов)")
        for rel in files:
            p = base / rel
            if p.exists():
                removed += 1
                if dry:
                    print(f"    {C_DIM}(dry) удалится {rel}{C_RESET}")
                else:
                    p.unlink()
                    print(f"    {C_GRN}-{C_RESET} {rel}")
                    # подчищаем пустые каталоги
                    parent = p.parent
                    while parent != base and not any(parent.iterdir()):
                        parent.rmdir()
                        parent = parent.parent
        if not dry:
            manifest.pop(t, None)
    if not dry:
        if manifest:
            _save_manifest(base, manifest)
        else:
            f = base / MANIFEST_NAME
            if f.exists():
                f.unlink()
            print(f"  {C_DIM}манифест пуст — {MANIFEST_NAME} удалён{C_RESET}")
    print(f"\n  {'будет ' if dry else ''}удалено: {removed}")
    return 0


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="qwenkit install",
        description="Установить набор команд/агентов с GitHub, сконвертировав его из формата Claude Code",
    )
    ap.add_argument("target", nargs="?", default="",
                    help="owner/repo или ссылка на github.com (можно с веткой и подкаталогом);\nне нужен для --list")
    ap.add_argument("--target-dir", choices=["user", "project"], default="user",
                    help="user = ~/.qwen (везде), project = ./.qwen (только текущий проект)")
    ap.add_argument("--path", default=".", help="корень проекта для --target-dir project")
    ap.add_argument("--only", action="append", choices=["agents", "commands", "mcp", "memory"],
                    help="установить только это (можно повторять)")
    ap.add_argument("--prefix", default="", help="префикс имён, например mypack- "
                                                 "(чтобы наборы из разных репо не пересекались)")
    ap.add_argument("--ref", help="ветка/тег/коммит (если не указаны в ссылке)")
    ap.add_argument("--overwrite", action="store_true", help="заменять существующие файлы (делает .bak)")
    ap.add_argument("--dry-run", action="store_true", help="показать план, ничего не меняя")
    ap.add_argument("--list", action="store_true", help="показать, что установлено через qwenkit")
    ap.add_argument("--uninstall", metavar="OWNER/REPO", help="удалить установленный набор "
                                                              "(или --all)")
    args = ap.parse_args(argv)

    base = (Path.home() / ".qwen") if args.target_dir == "user" else \
           (Path(args.path).expanduser().resolve() / ".qwen")

    if args.list:
        pass  # target не требуется
    elif not args.target and not args.uninstall:
        ap.error("нужно указать репозиторий (owner/repo или ссылку) либо --list/--uninstall")

    if args.list:
        manifest = _load_manifest(base)
        if not manifest:
            print(f"  {C_DIM}Через qwenkit ничего не установлено ({base / MANIFEST_NAME}){C_RESET}")
            return 0
        print(f"\n  {C_BOLD}Установлено через qwenkit{C_RESET} {C_DIM}({base}){C_RESET}")
        for slug, info in sorted(manifest.items()):
            print(f"\n  {C_GRN}{slug}{C_RESET} {C_DIM}@ {info.get('ref', '?')} · "
                  f"{info.get('date', '?')} · {len(info.get('installed', []))} файл(ов){C_RESET}")
            for f in info.get("installed", [])[:12]:
                print(f"    · {f}")
            extra = len(info.get("installed", [])) - 12
            if extra > 0:
                print(f"    {C_DIM}… и ещё {extra}{C_RESET}")
        print(f"\n  Удаление: {C_BOLD}qwenkit install <owner/repo> --uninstall owner/repo{C_RESET}")
        print(f"  Всё сразу:  {C_BOLD}qwenkit install x --uninstall --all{C_RESET}\n")
        return 0

    if args.uninstall:
        return uninstall(args.uninstall, base, args.dry_run)

    try:
        rr = parse_target(args.target)
    except ValueError as e:
        print(f"{C_RED}{e}{C_RESET}", file=sys.stderr)
        return 2
    if args.ref:
        rr.ref = args.ref

    only = set()
    if args.only:
        mapping = {"agents": "agent", "commands": "command", "mcp": "mcp", "memory": "memory"}
        only = {mapping[o] for o in args.only}
    else:
        only = {"agent", "command", "mcp", "memory"}   # settings — никогда автоматически

    print(f"\n{C_BOLD}qwenkit install{C_RESET} {C_DIM}← {rr}{C_RESET}")
    if args.dry_run:
        print(f"{C_YEL}--- DRY RUN ---{C_RESET}")
    if not os.environ.get("GITHUB_TOKEN") and not os.environ.get("GH_TOKEN"):
        print(f"{C_DIM}Без GITHUB_TOKEN лимит GitHub API — 60 запросов/час. "
              f"Список файлов берётся одним запросом, сами файлы качаются без лимита.{C_RESET}")

    rep = install(rr, base, only, args.dry_run, args.overwrite, args.prefix)

    print(f"\n{C_BOLD}Итог{C_RESET}")
    if rep.meta_fields:
        print(f"  {C_DIM}Перенесены молча (Qwen Code их игнорирует):{C_RESET} "
              f"{', '.join(sorted(rep.meta_fields))}")
    if rep.warnings:
        seen = set()
        print(f"  {C_YEL}Предупреждения:{C_RESET}")
        for where, msg in rep.warnings:
            if (where, msg) in seen:
                continue
            seen.add((where, msg))
            print(f"    {C_YEL}!{C_RESET} {Path(where).name}: {msg}")
    if rep.manual:
        print(f"  {C_RED}Сделать руками:{C_RESET}")
        for m in dict.fromkeys(rep.manual):
            print(f"    {C_RED}>{C_RESET} {m}")

    if not args.dry_run:
        print(f"""
{C_BOLD}Важно про безопасность{C_RESET}
  Агенты и команды — это промпты, которые будет выполнять ваш робот с доступом
  к файлам и терминалу. Чужой набор = чужие инструкции. Перед первым запуском:
    1. прочитайте установленные файлы в {base}
    2. обратите внимание на !{{...}} — это shell-команды, они выполняются
       (Qwen Code спросит подтверждение, но лучше знать заранее)
    3. подозрительное удаляйте: qwenkit install x --uninstall {rr.slug}

{C_BOLD}Дальше{C_RESET}
  qwen                            # запустить
  /                               # увидеть новые команды
  /agents manage                  # увидеть новых агентов
""")
    return 0
