"""`qwenkit setup` — установка Qwen Code и генерация ~/.qwen/settings.json под бесплатный API."""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .providers import FREE_ORDER, PROVIDERS, live_models

C_RESET = C_RED = C_GRN = C_YEL = C_DIM = C_BOLD = ""
if sys.stdout.isatty():
    C_RESET, C_RED, C_GRN = "\033[0m", "\033[31m", "\033[32m"
    C_YEL, C_DIM, C_BOLD = "\033[33m", "\033[2m", "\033[1m"

NPM_PACKAGE = "@qwen-code/qwen-code"


def _sh(cmd: list[str], timeout: int = 600) -> tuple[int, str]:
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def install_npm(verbose: bool = True) -> bool:
    if shutil.which("qwen"):
        if verbose:
            print(f"  {C_GRN}✓{C_RESET} qwen уже установлен: {shutil.which('qwen')}")
        return True
    if not shutil.which("npm"):
        print(f"  {C_RED}✗{C_RESET} npm не найден. Сначала поставьте Node.js ≥20: https://nodejs.org")
        return False
    print(f"  … npm install -g {NPM_PACKAGE}@latest  {C_DIM}(может занять минуту){C_RESET}")
    try:
        code, out = _sh(["npm", "install", "-g", f"{NPM_PACKAGE}@latest"], timeout=900)
    except subprocess.TimeoutExpired:
        print(f"  {C_RED}✗{C_RESET} установка превысила 15 минут")
        return False
    if code == 0:
        print(f"  {C_GRN}✓{C_RESET} установлено")
        return True
    # EACCES — типичная проблема глобальной установки
    print(f"  {C_RED}✗{C_RESET} npm install вернул {code}")
    tail = "\n".join(out.strip().splitlines()[-12:])
    print(f"{C_DIM}{tail}{C_RESET}")
    if "EACCES" in out or "permission denied" in out.lower():
        print(f"\n  {C_YEL}Не хватает прав на глобальную установку. Три варианта:{C_RESET}")
        print(f"    1) npx {NPM_PACKAGE}          {C_DIM}— запуск без установки{C_RESET}")
        print(f"    2) настроить npm-prefix в домашний каталог:")
        print(f"       npm config set prefix ~/.npm-global")
        print(f"       echo 'export PATH=~/.npm-global/bin:$PATH' >> ~/.bashrc && source ~/.bashrc")
        print(f"       npm install -g {NPM_PACKAGE}@latest")
        print(f"    3) sudo npm install -g {NPM_PACKAGE}@latest   {C_DIM}(не рекомендуется){C_RESET}")
    return False


def _shell_profile() -> Path | None:
    home = Path.home()
    if platform.system() == "Windows":
        return None
    for name in (".zshrc", ".bashrc", ".bash_profile", ".profile"):
        p = home / name
        if p.exists():
            return p
    return home / ".bashrc"


def write_env_hint(env_key: str, value: str) -> None:
    """Подсказать, как экспортировать ключ (никогда не пишем ключ в файлы молча)."""
    prof = _shell_profile()
    print(f"\n{C_BOLD}Ключ API{C_RESET}")
    if platform.system() == "Windows":
        print(f"  PowerShell (текущая сессия):")
        print(f"    {C_BOLD}$env:{env_key}='{value}'{C_RESET}")
        print(f"  PowerShell (навсегда):")
        print(f"    {C_BOLD}[Environment]::SetEnvironmentVariable('{env_key}','{value}','User'){C_RESET}")
        print(f"  cmd:")
        print(f"    {C_BOLD}setx {env_key} \"{value}\"{C_RESET}")
    else:
        print(f"  Добавьте в {prof}:")
        print(f"    {C_BOLD}export {env_key}='{value}'{C_RESET}")
        print(f"  и выполните {C_BOLD}source {prof}{C_RESET}")
    print(f"  {C_DIM}Проверить: qwenkit probe --provider …{C_RESET}")


def build_settings(provider_keys: list[str], default_model: str | None,
                   fast_model: str | None, store_key: dict[str, str] | None,
                   extra_models: dict[str, list[str]]) -> dict:
    """Собрать modelProviders в формате qwen-code 0.26+.

    Важно: значение ключа провайдера — ГОЛЫЙ массив ModelConfig.
    Старый формат {"protocol": …, "models": […]} молча игнорируется.
    """
    mp: dict[str, list[dict]] = {}
    all_ids: list[str] = []
    for pk in provider_keys:
        p = PROVIDERS[pk]
        base = p.base_url
        if "{ACCOUNT_ID}" in base:
            acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "ВАШ_ACCOUNT_ID")
            base = base.replace("{ACCOUNT_ID}", acc)
        models = extra_models.get(pk) or p.models
        entries = []
        for mid in models:
            e: dict = {"id": mid, "name": f"{mid}", "envKey": p.env_key}
            if base:
                e["baseUrl"] = base
            e["description"] = p.title
            entries.append(e)
            all_ids.append(mid)
        # все провайдеры из каталога говорят по OpenAI-совместимому протоколу
        mp.setdefault(p.protocol, []).extend(entries)

    settings: dict = {"modelProviders": mp}
    if store_key:
        settings["env"] = dict(store_key)
    settings["security"] = {"auth": {"selectedType": "openai"}}

    chosen = default_model or (all_ids[0] if all_ids else None)
    if chosen:
        settings["model"] = {"name": chosen}
    if fast_model:
        settings["fastModel"] = fast_model
    return settings


def merge_settings(path: Path, new: dict) -> dict:
    """Объединить с существующим settings.json, ничего не теряя."""
    old: dict = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:                                    # noqa: BLE001
            print(f"  {C_RED}✗{C_RESET} {path} содержит невалидный JSON ({e}). "
                  f"Исправьте вручную или используйте --force")
            raise SystemExit(2)
    merged = json.loads(json.dumps(old))          # deep copy
    # modelProviders: объединяем по протоколам, дубли по (id, baseUrl) отбрасываем
    old_mp = merged.get("modelProviders") or {}
    new_mp = new.get("modelProviders") or {}
    for proto, models in new_mp.items():
        cur = old_mp.get(proto)
        if not isinstance(cur, list):
            cur = []
        seen = {(m.get("id"), m.get("baseUrl")) for m in cur if isinstance(m, dict)}
        for m in models:
            k = (m.get("id"), m.get("baseUrl"))
            if k not in seen:
                cur.append(m)
                seen.add(k)
        old_mp[proto] = cur
    merged["modelProviders"] = old_mp
    for k in ("security", "model", "fastModel", "env"):
        if k in new:
            if k == "env" and isinstance(merged.get("env"), dict):
                merged["env"] = {**merged["env"], **new["env"]}
            else:
                merged[k] = new[k]
    return merged


def run(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="qwenkit setup",
        description="Установить Qwen Code и настроить бесплатный API-провайдер",
    )
    ap.add_argument("--provider", action="append", choices=list(PROVIDERS),
                    help=f"провайдер (можно несколько). Бесплатные: {', '.join(FREE_ORDER)}")
    ap.add_argument("--model", help="модель по умолчанию (model.name)")
    ap.add_argument("--fast-model", help="быстрая модель для субагентов (fastModel)")
    ap.add_argument("--install", action="store_true", help="установить npm-пакет, если не установлен")
    ap.add_argument("--refresh-models", action="store_true",
                    help="запросить актуальный список моделей у провайдера вместо встроенного")
    ap.add_argument("--max-models", type=int, default=10, help="сколько моделей добавить (по умолчанию 10)")
    ap.add_argument("--store-key", action="store_true",
                    help="сохранить ключ из env прямо в settings.json (менее безопасно)")
    ap.add_argument("--settings", default=str(Path.home() / ".qwen" / "settings.json"),
                    help="путь к settings.json")
    ap.add_argument("--force", action="store_true", help="перезаписать settings.json вместо объединения")
    ap.add_argument("--dry-run", action="store_true", help="показать JSON, не записывая")
    args = ap.parse_args(argv)

    keys = args.provider or ["modelscope"]
    print(f"\n{C_BOLD}qwenkit setup{C_RESET} {C_DIM}— провайдеры: {', '.join(keys)}{C_RESET}\n")

    if args.install:
        install_npm()
    elif not shutil.which("qwen"):
        print(f"  {C_YEL}!{C_RESET} qwen не найден в PATH. Установите: "
              f"{C_BOLD}npm install -g {NPM_PACKAGE}@latest{C_RESET} "
              f"или запустите {C_BOLD}qwenkit setup --install{C_RESET}")

    # ключи
    store: dict[str, str] = {}
    missing = []
    for pk in keys:
        p = PROVIDERS[pk]
        val = os.environ.get(p.env_key)
        if val:
            print(f"  {C_GRN}✓{C_RESET} {p.env_key} найден в окружении")
            if args.store_key:
                store[p.env_key] = val
        elif p.local:
            print(f"  {C_GRN}✓{C_RESET} {p.title}: ключ не требуется")
            if args.store_key:
                store[p.env_key] = "ollama"
        else:
            missing.append(p)
            print(f"  {C_RED}✗{C_RESET} {p.env_key} НЕ задан")

    # живой каталог моделей
    extra: dict[str, list[str]] = {}
    if args.refresh_models:
        for pk in keys:
            p = PROVIDERS[pk]
            api_key = os.environ.get(p.env_key) or ("ollama" if p.local else None)
            ok, ids, err = live_models(p, api_key)
            if ok and ids:
                extra[pk] = ids[: args.max_models]
                print(f"  {C_GRN}✓{C_RESET} {p.title}: получено моделей {len(ids)}, берём {len(extra[pk])}")
            else:
                print(f"  {C_YEL}!{C_RESET} {p.title}: каталог не получен ({err or 'пусто'}) — "
                      f"используем встроенный список")
                extra[pk] = p.models[: args.max_models]
    else:
        for pk in keys:
            extra[pk] = PROVIDERS[pk].models[: args.max_models]

    settings = build_settings(keys, args.model, args.fast_model, store or None, extra)
    path = Path(args.settings).expanduser()

    if args.dry_run:
        print(f"\n{C_BOLD}Будет записано в {path}:{C_RESET}\n")
        print(json.dumps(settings, ensure_ascii=False, indent=2))
        return 0

    final = settings if args.force else merge_settings(path, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and args.force:
        bk = path.with_suffix(".json.bak")
        shutil.copy2(path, bk)
        print(f"  {C_YEL}!{C_RESET} старая копия сохранена в {bk}")
    path.write_text(json.dumps(final, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except Exception:                                             # noqa: BLE001
        pass
    print(f"  {C_GRN}✓{C_RESET} записано {path}")

    n = sum(len(v) for v in final.get("modelProviders", {}).values())
    print(f"  {C_GRN}✓{C_RESET} моделей в /model: {n}")
    if final.get("model"):
        print(f"  {C_GRN}✓{C_RESET} модель по умолчанию: {final['model']['name']}")
    if final.get("fastModel"):
        print(f"  {C_GRN}✓{C_RESET} быстрая модель: {final['fastModel']}")

    for p in missing:
        write_env_hint(p.env_key, "ВАШ_КЛЮЧ")
        print(f"  {C_DIM}Где взять: {p.signup}{C_RESET}")
        print(f"  {C_DIM}Что бесплатно: {p.free}{C_RESET}")

    print(f"\n{C_BOLD}Готово. Дальше:{C_RESET}")
    print(f"  1. export ключ (см. выше) и перезапустите терминал")
    print(f"  2. {C_BOLD}qwenkit probe --provider {keys[0]}{C_RESET}   — убедиться, что API отвечает")
    print(f"  3. {C_BOLD}qwenkit pack{C_RESET}                            — поставить команды и субагентов")
    print(f"  4. {C_BOLD}cd ваш-проект && qwen{C_RESET}")
    print(f"  {C_DIM}Внутри qwen: /model — сменить модель, /auth — провайдер, /agents — субагенты{C_RESET}\n")
    return 0
