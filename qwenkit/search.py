"""`qwenkit search` — найти на GitHub наборы команд и агентов для Claude Code.

Найденное ставится одной командой:  qwenkit install <owner/repo>

Лимит GitHub Search API без токена — 10 запросов в минуту, поэтому по
умолчанию выполняется небольшое число заранее подобранных запросов.
С GITHUB_TOKEN лимит выше (30/мин).
"""

from __future__ import annotations

import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

C_RESET = C_RED = C_GRN = C_YEL = C_DIM = C_BOLD = ""
if sys.stdout.isatty():
    C_RESET, C_RED, C_GRN = "\033[0m", "\033[31m", "\033[32m"
    C_YEL, C_DIM, C_BOLD = "\033[33m", "\033[2m", "\033[1m"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# Подобранные запросы: ищем именно наборы .md-агентов/команд, а не «упоминания»
DEFAULT_QUERIES = [
    "claude code agents collection",
    "awesome claude code",
    "claude code subagents",
    "claude code slash commands",
    "agents.md claude code repository",
]


def search_repos(query: str, per_page: int = 8, timeout: int = 30) -> list[dict]:
    url = ("https://api.github.com/search/repositories?q="
           + urllib.parse.quote(query)
           + f"&per_page={per_page}&sort=stars&order=desc")
    headers = {
        "User-Agent": "qwenkit/1.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        req = urllib.request.Request(url, headers=headers)
        data = json.load(urllib.request.urlopen(req, timeout=timeout, context=_CTX))
    except urllib.error.HTTPError as e:
        if e.code in (403, 429):
            print(f"  {C_YEL}!{C_RESET} GitHub Search API: превышен лимит "
                  f"(10 запросов/минуту без токена). Подождите минуту или задайте "
                  f"GITHUB_TOKEN.", file=sys.stderr)
        else:
            print(f"  {C_YEL}!{C_RESET} поиск не удался: HTTP {e.code}", file=sys.stderr)
        return []
    except Exception as e:                                          # noqa: BLE001
        print(f"  {C_YEL}!{C_RESET} поиск не удался: {type(e).__name__}: {e}", file=sys.stderr)
        return []

    out = []
    for it in data.get("items", []):
        out.append({
            "full_name": it["full_name"],
            "stars": it.get("stargazers_count", 0),
            "description": (it.get("description") or "").strip(),
            "updated": (it.get("pushed_at") or "")[:10],
            "url": it.get("html_url", ""),
        })
    return out


def run(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="qwenkit search",
        description="Найти на GitHub наборы команд и агентов для Claude Code",
    )
    ap.add_argument("query", nargs="*", help="своя строка поиска (иначе — подобранные запросы)")
    ap.add_argument("--limit", type=int, default=8, help="сколько репозиториев на запрос (по умолчанию 8)")
    ap.add_argument("--min-stars", type=int, default=20, help="порог звёзд (по умолчанию 20)")
    args = ap.parse_args(argv)

    queries = [" ".join(args.query)] if args.query else DEFAULT_QUERIES
    print(f"\n{C_BOLD}qwenkit search{C_RESET} {C_DIM}— наборы для Claude Code на GitHub{C_RESET}")
    print(f"{C_DIM}Найденное ставится так: qwenkit install <owner/repo>{C_RESET}\n")

    seen: set[str] = set()
    rows: list[dict] = []
    for i, q in enumerate(queries):
        if i:
            time.sleep(7)          # бережём лимит 10 запросов/минуту
        print(f"  {C_DIM}поиск: {q}{C_RESET}")
        for r in search_repos(q, per_page=max(args.limit, 10)):
            key = r["full_name"].lower()
            if key in seen or r["stars"] < args.min_stars:
                continue
            seen.add(key)
            rows.append(r)

    if not rows:
        print(f"\n  {C_YEL}Ничего не нашлось (или кончился лимит поиска).{C_RESET}")
        print(f"  Попробуйте: qwenkit search \"claude agents\"  или задайте GITHUB_TOKEN")
        return 1

    rows.sort(key=lambda r: -r["stars"])
    rows = rows[: max(args.limit * 2, 15)]

    print(f"\n  {C_BOLD}{'РЕПОЗИТОРИЙ':<44s} {'ЗВЁЗД':>7s}  {'ОБНОВЛЁН':<10s}  ОПИСАНИЕ{C_RESET}")
    print(f"  {C_DIM}{'-' * 100}{C_RESET}")
    for r in rows:
        name = r["full_name"]
        if len(name) > 43:
            name = name[:40] + "…"
        desc = r["description"].replace("\n", " ")
        if len(desc) > 62:
            desc = desc[:59] + "…"
        print(f"  {C_GRN}{name:<44s}{C_RESET} {r['stars']:>7d}  {r['updated']:<10s}  {C_DIM}{desc}{C_RESET}")

    print(f"""
{C_BOLD}Как ставить{C_RESET}
  qwenkit install <owner/repo>                  весь репозиторий
  qwenkit install <owner/repo> --dry-run        сначала посмотреть план
  qwenkit install <owner/repo>/agents           только подкаталог
  qwenkit install <ссылка на .md-файл>          один файл
  qwenkit install --list                        что установлено
  qwenkit install x --uninstall <owner/repo>    удалить

{C_BOLD}На что смотреть при выборе{C_RESET}
  · дата обновления — наборы под старые версии Claude Code могут не конвертироваться
  · структура: нужны каталоги agents/ и commands/ с .md-файлами
  · звёзды — косвенный признак, что набор хоть кто-то использовал

{C_DIM}Перед установкой чужого набора помните: это промпты, которые будет выполнять
агент с доступом к вашим файлам и терминалу. qwenkit показывает предупреждения
на каждый shell-вызов внутри команды (!{{...}}), но прочитать файлы стоит самому.{C_RESET}
""")
    return 0
