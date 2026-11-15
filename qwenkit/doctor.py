"""`qwenkit doctor` — проверка окружения и доступности бесплатных провайдеров."""

from __future__ import annotations

import json
import os
import platform
import shutil
import ssl
import subprocess
import sys
import urllib.request
from pathlib import Path

from .providers import FREE_ORDER, PAID_ORDER, PROVIDERS, live_models

C_RESET = C_RED = C_GRN = C_YEL = C_DIM = C_BOLD = ""
if sys.stdout.isatty():
    C_RESET, C_RED, C_GRN = "\033[0m", "\033[31m", "\033[32m"
    C_YEL, C_DIM, C_BOLD = "\033[33m", "\033[2m", "\033[1m"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

QWEN_MIN_NODE = 20


def _ok(msg: str) -> None:
    print(f"  {C_GRN}✓{C_RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {C_YEL}!{C_RESET} {msg}")


def _bad(msg: str) -> None:
    print(f"  {C_RED}✗{C_RESET} {msg}")


def _hint(msg: str) -> None:
    print(f"  {C_DIM}→ {msg}{C_RESET}")


def _head(url: str, timeout: int = 12) -> tuple[int | None, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (qwenkit doctor)"})
        r = urllib.request.urlopen(req, timeout=timeout, context=_CTX)
        r.read(64)
        return r.status, ""
    except urllib.error.HTTPError as e:                          # noqa: PERF203
        return e.code, ""
    except Exception as e:                                        # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def check_runtime() -> dict:
    print(f"{C_BOLD}[1/4] Окружение{C_RESET}")
    info = {"os": platform.system(), "node": None, "npm": None, "qwen": None, "ollama": None}
    _ok(f"ОС: {platform.system()} {platform.release()} · Python {platform.python_version()}")

    node = shutil.which("node")
    if node:
        try:
            v = subprocess.run([node, "-v"], capture_output=True, text=True, timeout=15).stdout.strip()
            info["node"] = v
            major = int(v.lstrip("v").split(".")[0])
            if major >= QWEN_MIN_NODE:
                _ok(f"Node.js {v} (нужен ≥{QWEN_MIN_NODE})")
            else:
                _bad(f"Node.js {v} — нужен ≥{QWEN_MIN_NODE}")
                _hint("nvm install 22 && nvm use 22   ·   или https://nodejs.org")
        except Exception as e:                                    # noqa: BLE001
            _warn(f"node найден, но не запустился: {e}")
    else:
        _bad("Node.js не найден в PATH")
        _hint("Qwen Code — npm-пакет, без Node.js не запустится. https://nodejs.org (LTS)")

    info["npm"] = shutil.which("npm")
    if info["npm"]:
        _ok("npm найден")
    elif node:
        _warn("npm не найден — обычно ставится вместе с Node.js")

    qwen = shutil.which("qwen")
    info["qwen"] = qwen
    if qwen:
        try:
            v = subprocess.run([qwen, "--version"], capture_output=True, text=True, timeout=30)
            ver = (v.stdout or v.stderr).strip().splitlines()
            _ok(f"Qwen Code установлен: {ver[0] if ver else qwen}")
        except Exception:                                         # noqa: BLE001
            _ok(f"Qwen Code найден: {qwen}")
    else:
        _warn("Qwen Code не установлен")
        _hint("npm install -g @qwen-code/qwen-code@latest")

    if shutil.which("ollama"):
        info["ollama"] = True
        _ok("Ollama найдена (локальные модели доступны)")
    else:
        _warn("Ollama не найдена — локальный бесплатный вариант недоступен (необязательно)")

    print()
    return info


def check_network() -> None:
    print(f"{C_BOLD}[2/4] Доступность провайдеров{C_RESET}")
    _warn("Проверяется только доступность эндпоинта, не валидность ключа")
    for key in FREE_ORDER + PAID_ORDER:
        p = PROVIDERS[key]
        url = p.models_url or p.base_url
        if "{ACCOUNT_ID}" in url:
            acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
            if not acc:
                print(f"  {p.title:<42s} {C_YEL}нужна CLOUDFLARE_ACCOUNT_ID{C_RESET} "
                      f"{C_DIM}(иначе URL с заглушкой){C_RESET}")
                continue
            url = url.replace("{ACCOUNT_ID}", acc)
        code, err = _head(url)
        label = f"{p.title:<42s}"
        if code in (200, 401, 403):
            # 401/403 = сервер жив, но нужен ключ. Это нормально.
            state = f"{C_GRN}доступен{C_RESET}" if code == 200 else f"{C_GRN}жив{C_RESET} {C_DIM}(нужен ключ: HTTP {code}){C_RESET}"
            print(f"  {label} {state}")
        else:
            print(f"  {label} {C_RED}недоступен{C_RESET} {C_DIM}({err or code}){C_RESET}")
    print()


def check_keys() -> dict:
    print(f"{C_BOLD}[3/4] API-ключи в окружении{C_RESET}")
    found = {}
    for key in FREE_ORDER + PAID_ORDER:
        p = PROVIDERS[key]
        val = os.environ.get(p.env_key)
        if val:
            masked = val[:6] + "…" + val[-4:] if len(val) > 12 else "…"
            _ok(f"{p.env_key} = {masked}  ({p.title})")
            found[key] = val
        else:
            print(f"  {C_DIM}·  {p.env_key:<24s} не задан ({p.title}){C_RESET}")
    if not found:
        _warn("Ни одного ключа не найдено")
        _hint("Без ключа работает только локальная Ollama. Самый простой бесплатный ключ: "
              "ModelScope → https://www.modelscope.cn/my/myaccesstoken")
    print()
    return found


def check_settings() -> None:
    print(f"{C_BOLD}[4/4] Конфигурация Qwen Code{C_RESET}")
    home = Path.home()
    settings = home / ".qwen" / "settings.json"
    if not settings.exists():
        _warn(f"{settings} не существует")
        _hint("Запустите `qwenkit setup --provider modelscope` — файл будет создан")
        print()
        return
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except Exception as e:                                        # noqa: BLE001
        _bad(f"{settings} не является валидным JSON: {e}")
        print()
        return
    _ok(f"{settings} ({len(json.dumps(data))} байт)")

    mp = data.get("modelProviders") or {}
    if not mp:
        _warn("нет modelProviders — /model будет пустым")
    for proto, models in mp.items():
        if not isinstance(models, list):
            _bad(f"modelProviders.{proto} должен быть МАССИВОМ моделей (старый формат "
                 f"{{protocol, models}} больше не поддерживается и молча игнорируется)")
            continue
        _ok(f"modelProviders.{proto}: {len(models)} модел(ей)")
        for m in models:
            if not isinstance(m, dict) or not m.get("id"):
                _bad(f"  запись без id: {m!r}")
                continue
            envk = m.get("envKey")
            has = bool(os.environ.get(envk)) if envk else False
            flag = f"{C_GRN}ключ в env{C_RESET}" if has else (
                f"{C_YEL}ключа нет в env{C_RESET}" if envk else f"{C_DIM}envKey не задан{C_RESET}")
            extra = f" {C_DIM}baseUrl={m['baseUrl']}{C_RESET}" if m.get("baseUrl") else ""
            print(f"    · {m['id']:<40s} {flag}{extra}")

    sel = (data.get("security") or {}).get("auth", {}).get("selectedType")
    name = (data.get("model") or {}).get("name")
    if sel:
        _ok(f"security.auth.selectedType = {sel}")
    else:
        _warn("нет security.auth.selectedType — при запуске попросит /auth")
    if name:
        ids = {m.get("id") for lst in mp.values() if isinstance(lst, list)
               for m in lst if isinstance(m, dict)}
        if name in ids:
            _ok(f"model.name = {name} (есть в modelProviders)")
        else:
            _bad(f"model.name = {name}, но такого id нет в modelProviders {sorted(ids)}")
    else:
        _warn("нет model.name — будет выбрана модель по умолчанию")

    # ключи прямо в settings.json
    env_block = data.get("env") or {}
    if env_block:
        _warn(f"в settings.json хранится ключей: {len(env_block)} — это обычный текст. "
              f"Безопаснее: .env файл или export в shell")

    # память и расширения
    mem = home / ".qwen" / "QWEN.md"
    if mem.exists():
        _ok(f"глобальная память: {mem}")
    for sub, label in (("commands", "команды"), ("agents", "субагенты")):
        d = home / ".qwen" / sub
        if d.is_dir():
            n = len([p for p in d.rglob("*") if p.is_file()])
            _ok(f"глобальные {label}: {n} файл(ов) в {d}")
    print()


def run(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="qwenkit doctor", description="Диагностика Qwen Code")
    ap.add_argument("--offline", action="store_true", help="не обращаться к сети")
    args = ap.parse_args(argv)

    print(f"\n{C_BOLD}qwenkit doctor{C_RESET} {C_DIM}— диагностика окружения Qwen Code{C_RESET}\n")
    info = check_runtime()
    if not args.offline:
        check_network()
    keys = check_keys()
    check_settings()

    print(f"{C_BOLD}Что делать дальше{C_RESET}")
    if not info["node"]:
        print(f"  1. Поставьте Node.js ≥{QWEN_MIN_NODE}: https://nodejs.org")
    if not info["qwen"]:
        print(f"  2. npm install -g @qwen-code/qwen-code@latest")
    if not keys:
        print(f"  3. Возьмите бесплатный ключ: {PROVIDERS['modelscope'].signup}")
        print(f"     export {PROVIDERS['modelscope'].env_key}=<ключ>")
    print(f"  4. qwenkit setup --provider modelscope   (создаст ~/.qwen/settings.json)")
    print(f"  5. qwenkit pack                          (установит команды и субагентов)")
    print(f"  6. qwenkit probe                         (живой тест моделей)")
    print(f"  7. cd ваш-проект && qwen")
    print()
    return 0
