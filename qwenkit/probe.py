"""`qwenkit probe` — живой тест провайдеров: реально дёргаем API и проверяем tool-calling."""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

from .providers import FREE_ORDER, PAID_ORDER, PROVIDERS

C_RESET = C_RED = C_GRN = C_YEL = C_DIM = C_BOLD = ""
if sys.stdout.isatty():
    C_RESET, C_RED, C_GRN = "\033[0m", "\033[31m", "\033[32m"
    C_YEL, C_DIM, C_BOLD = "\033[33m", "\033[2m", "\033[1m"

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE

# Минимальный инструмент в формате OpenAI: без tool-calling агент работать не будет
TOOL_PROBE = {
    "type": "function",
    "function": {
        "name": "read_file",
        "description": "Read a file from the workspace",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "file path"}},
            "required": ["path"],
        },
    },
}


def chat_completion(base_url: str, api_key: str, model: str,
                    with_tools: bool = True, timeout: int = 90) -> dict:
    """Один запрос к chat/completions. Возвращает словарь с результатом."""
    url = base_url.rstrip("/") + "/chat/completions"
    body: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a terse assistant."},
            {"role": "user", "content": "Read the file at path 'a.txt' using your tools. "
                                        "If you have no tools, answer with the single word NOTOOLS."},
        ],
        "max_tokens": 200,
        "temperature": 0,
        "stream": False,
    }
    if with_tools:
        body["tools"] = [TOOL_PROBE]
        body["tool_choice"] = "auto"

    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "qwenkit-probe/1.0",
    })
    t0 = time.time()
    try:
        raw = urllib.request.urlopen(req, timeout=timeout, context=_CTX).read()
        dt = time.time() - t0
        j = json.loads(raw)
        msg = (j.get("choices") or [{}])[0].get("message") or {}
        calls = msg.get("tool_calls") or []
        usage = j.get("usage") or {}
        return {
            "ok": True,
            "latency": round(dt, 2),
            "tool_call": bool(calls),
            "tool_name": (calls[0].get("function", {}).get("name") if calls else None),
            "text": (msg.get("content") or "")[:160],
            "usage": usage,
            "error": "",
        }
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8", "ignore")[:300]
        except Exception:                                         # noqa: BLE001
            pass
        return {"ok": False, "latency": round(time.time() - t0, 2), "tool_call": False,
                "tool_name": None, "text": "", "usage": {},
                "error": f"HTTP {e.code}: {detail or e.reason}"}
    except Exception as e:                                        # noqa: BLE001
        return {"ok": False, "latency": round(time.time() - t0, 2), "tool_call": False,
                "tool_name": None, "text": "", "usage": {},
                "error": f"{type(e).__name__}: {e}"}


def _resolve_key(p, explicit: str | None) -> str | None:
    return explicit or os.environ.get(p.env_key)


def run(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        prog="qwenkit probe",
        description="Живой тест: какой провайдер и какая модель реально работают с tool-calling",
    )
    ap.add_argument("--provider", action="append", choices=list(PROVIDERS),
                    help="проверить конкретного провайдера (можно несколько раз)")
    ap.add_argument("--model", action="append", help="проверить конкретную модель (можно несколько раз)")
    ap.add_argument("--api-key", help="ключ (иначе берётся из env-переменной провайдера)")
    ap.add_argument("--all-models", action="store_true", help="проверить все модели провайдера из каталога")
    ap.add_argument("--limit", type=int, default=3, help="сколько моделей проверить (по умолчанию 3)")
    ap.add_argument("--include-paid", action="store_true", help="проверить и платных провайдеров")
    args = ap.parse_args(argv)

    order = args.provider or (FREE_ORDER + (PAID_ORDER if args.include_paid else []))
    print(f"\n{C_BOLD}qwenkit probe{C_RESET} {C_DIM}— проверка tool-calling (обязателен для агента){C_RESET}\n")

    results: list[tuple[str, str, dict]] = []
    for key in order:
        p = PROVIDERS[key]
        api_key = _resolve_key(p, args.api_key)
        if not api_key and not p.local:
            print(f"{C_DIM}· {p.title}: пропущен, {p.env_key} не задан{C_RESET}")
            continue
        if p.local and not api_key:
            api_key = "ollama"          # Ollama ключ не проверяет
        if "{ACCOUNT_ID}" in p.base_url:
            acc = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
            if not acc:
                print(f"{C_DIM}· {p.title}: пропущен, нужна CLOUDFLARE_ACCOUNT_ID{C_RESET}")
                continue
            p.base_url = p.base_url.replace("{ACCOUNT_ID}", acc)

        models = args.model or list(p.models)
        if args.all_models:
            ok, ids, err = live_models(p, api_key)
            if ok:
                models = ids
            else:
                print(f"{C_YEL}· {p.title}: каталог не получен ({err}){C_RESET}")
        if not models:
            print(f"{C_YEL}· {p.title}: список моделей пуст — укажите --model{C_RESET}")
            continue

        print(f"{C_BOLD}{p.title}{C_RESET}")
        for m in models[: max(1, args.limit if not args.model else len(models))]:
            r = chat_completion(p.base_url, api_key, m)
            results.append((p.key, m, r))
            if r["ok"]:
                tc = f"{C_GRN}tools ✓{C_RESET}" if r["tool_call"] else f"{C_RED}tools ✗{C_RESET}"
                u = r["usage"]
                tok = f" {C_DIM}{u.get('total_tokens', '?')} ток{C_RESET}" if u else ""
                print(f"  {C_GRN}OK {C_RESET} {m:<48s} {tc} {r['latency']}s{tok}")
                if not r["tool_call"]:
                    print(f"      {C_DIM}ответ: {r['text'][:100]!r}{C_RESET}")
            else:
                print(f"  {C_RED}ERR{C_RESET} {m:<48s} {C_DIM}{r['error'][:150]}{C_RESET}")
        print()

    # итог
    good = [(pk, m, r) for pk, m, r in results if r["ok"] and r["tool_call"]]
    notool = [(pk, m, r) for pk, m, r in results if r["ok"] and not r["tool_call"]]
    print(f"{C_BOLD}Итог{C_RESET}")
    if good:
        print(f"  {C_GRN}Годятся для Qwen Code (есть tool-calling):{C_RESET}")
        for pk, m, r in sorted(good, key=lambda x: x[2]["latency"]):
            print(f"    · {PROVIDERS[pk].key}:{m}  ({r['latency']}s)")
        best = min(good, key=lambda x: x[2]["latency"])
        print(f"\n  Рекомендация: {C_BOLD}qwenkit setup --provider {best[0]} --model {best[1]}{C_RESET}")
    else:
        print(f"  {C_RED}Ни одна модель не прошла проверку tool-calling{C_RESET}")
    if notool:
        print(f"  {C_YEL}Работают, но БЕЗ tool-calling (для агента не годятся, "
              f"только для чата):{C_RESET}")
        for pk, m, _ in notool:
            print(f"    · {PROVIDERS[pk].key}:{m}")
    print()
    return 0 if good else 1
