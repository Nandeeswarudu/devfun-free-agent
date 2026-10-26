"""Greedy, sandbox-safe TCG action policy for DevFun's hosted engine."""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

def _load_catalog():
    try:
        path = Path(__file__).resolve().parent.parent / "assets" / "card_catalog.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        cards = data.get("cards", [])
        attacks = data.get("attacks", [])
        return (
            {int(c["cardId"]): c for c in cards if isinstance(c, dict) and c.get("cardId") is not None},
            {int(a["attackId"]): a for a in attacks if isinstance(a, dict) and a.get("attackId") is not None},
        )
    except Exception:
        return {}, {}

CARDS, ATTACKS = _load_catalog()

def _to_int(x):
    try:
        if isinstance(x, bool):
            return None
        return int(x)
    except (TypeError, ValueError):
        return None

def _attacks_for(card):
    out = []
    for attack_id in card.get("attacks", []) if isinstance(card, dict) else []:
        attack_id = _to_int(attack_id)
        if attack_id in ATTACKS:
            out.append(ATTACKS[attack_id])
    return out

def _card_power(card):
    if not isinstance(card, dict):
        return 0.0
    hp = float(card.get("hp") or card.get("maxHp") or 0)
    best = 0.0
    for attack in _attacks_for(card):
        damage = float(attack.get("damage") or 0)
        energies = attack.get("energies") or []
        cost = len(energies) if isinstance(energies, list) else 1
        text = str(attack.get("text") or "").lower()
        bonus = 0.0
        if "draw" in text or "attach" in text or "search your deck" in text:
            bonus += 12.0
        if "knocked out" in text or "can't retreat" in text or "paralyzed" in text:
            bonus += 8.0
        if "does 30 damage to itself" in text or "discard all energy" in text:
            bonus -= 18.0
        best = max(best, damage + bonus - 17.0 * cost)
    name = str(card.get("name") or "").lower()
    if "ex" in name:
        hp += 8
    return hp * 0.60 + best

def _name_score(name):
    n = str(name or "").lower()
    score = 0.0
    if "professor" in n or "iono" in n or "research" in n:
        score += 55
    if "nest ball" in n or "ultra ball" in n or "buddy-buddy poffin" in n:
        score += 48
    if "boss's orders" in n or "counter catcher" in n:
        score += 38
    if "switch" in n or "escape rope" in n:
        score += 25
    if "energy retrieval" in n or "earthen vessel" in n:
        score += 22
    if "tool" in n or "stadium" in n:
        score -= 4
    return score

def _iter_ids(obj, parent_key=""):
    """Return values that look like explicit card/attack ID fields."""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            lk = str(k).lower().replace("_", "")
            if lk in ("cardid", "pokemonid", "attackid", "targetcardid", "sourcecardid"):
                iv = _to_int(v)
                if iv is not None:
                    out.append((lk, iv))
            elif isinstance(v, (dict, list)):
                out.extend(_iter_ids(v, lk))
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, (dict, list)):
                out.extend(_iter_ids(v, parent_key))
    return out

def _option_score(option, select, observation):
    sel_type = str((select or {}).get("type") or "").lower()
    sel_context = str((select or {}).get("context") or "").lower()
    ctx = (sel_type + " " + sel_context)
    try:
        blob = json.dumps(option, ensure_ascii=False, sort_keys=True).lower()
    except Exception:
        blob = str(option).lower()
    card_candidates = []
    attack_candidates = []
    for key, ident in _iter_ids(option):
        if key == "attackid" and ident in ATTACKS:
            attack_candidates.append(ATTACKS[ident])
        if key != "attackid" and ident in CARDS:
            card_candidates.append(CARDS[ident])
    if isinstance(option, (int, str)):
        iv = _to_int(option)
        if iv in CARDS:
            card_candidates.append(CARDS[iv])
        if iv in ATTACKS:
            attack_candidates.append(ATTACKS[iv])

    score = 0.0
    discard_context = ("discard" in ctx or "discard" in blob or "choose cards to discard" in ctx)

    # In the main turn menu, the engine encodes legal moves as option types:
    # type 7 plays a legal card from hand, type 8 attaches energy to a Pokémon,
    # type 13 attacks, and type 14 ends the turn. Prefer setup plays before
    # passing, while still allowing high-value attacks to outrank energy attach.
    main_menu = str((select or {}).get("type")) == "0" and str((select or {}).get("context")) == "0"
    option_type = _to_int(option.get("type")) if isinstance(option, dict) else None
    if main_menu and option_type == 7:
        score = 180.0
        # When this runtime exposes our hand, refine card-play priorities by name/ID.
        current = observation.get("current") if isinstance(observation, dict) else {}
        your_index = _to_int((current or {}).get("yourIndex")) if isinstance(current, dict) else None
        players = (current or {}).get("players", []) if isinstance(current, dict) else []
        hand = players[your_index].get("hand") if isinstance(players, list) and your_index is not None and 0 <= your_index < len(players) and isinstance(players[your_index], dict) else None
        hand_index = _to_int(option.get("index")) if isinstance(option, dict) else None
        if isinstance(hand, list) and hand_index is not None and 0 <= hand_index < len(hand):
            hand_card = hand[hand_index]
            if isinstance(hand_card, dict):
                card_id = _to_int(hand_card.get("cardId", hand_card.get("id")))
                card = CARDS.get(card_id) if card_id is not None else None
                name = str((card or hand_card).get("name") or "")
                score += _name_score(name)
                if card:
                    score += min(35.0, max(0.0, _card_power(card) * 0.08))
    elif main_menu and option_type == 8:
        score = 85.0
    elif main_menu and option_type == 14:
        score = -10000.0

    # Attack choices: prefer high damage and low energy cost, with a light penalty
    # for attacks whose text imposes a large self-cost.
    for attack in attack_candidates:
        dmg = float(attack.get("damage") or 0)
        energies = attack.get("energies") or []
        cost = len(energies) if isinstance(energies, list) else 1
        text = str(attack.get("text") or "").lower()
        bonus = 0.0
        if "draw" in text or "attach" in text or "search your deck" in text:
            bonus += 12
        if "knocked out" in text or "paralyzed" in text:
            bonus += 10
        if "does 30 damage to itself" in text or "discard all energy" in text:
            bonus -= 25
        score = max(score, 2.1 * dmg + bonus - 14 * cost)

    # A card choice typically supplies cardId; card instances may have nested cardId.
    for card in card_candidates:
        card_score = _card_power(card)
        name = str(card.get("name") or "")
        card_score += _name_score(name)
        if discard_context:
            card_score = -card_score
        if any(word in ctx for word in ("energy", "attach", "power up")) and not discard_context:
            # The selection is likely an energy destination; favor an efficient attacker.
            card_score += 20.0
        score = min(score, card_score) if discard_context else max(score, card_score)

    # Handle options with their own state fields (usually in-play Pokémon targets).
    if isinstance(option, dict):
        hp = float(option.get("hp") or 0)
        max_hp = float(option.get("maxHp") or option.get("max_hp") or hp or 1)
        energies = option.get("energies") or []
        energy_n = len(energies) if isinstance(energies, list) else float(energies or 0)
        in_play_score = hp + min(energy_n, 6) * 8.0
        if max_hp > 0 and hp > 0:
            in_play_score += 18.0 * hp / max_hp
        if any(w in ctx for w in ("switch", "promote", "active")):
            score = max(score, in_play_score)
        elif any(w in ctx for w in ("attach", "energy")):
            score = max(score, in_play_score - energy_n * 5.0)

    # Text-level fallbacks when the option contains a label/action but no IDs.
    if "professor" in blob or "research" in blob or "draw" in blob:
        score += 40
    if "nest ball" in blob or "ultra ball" in blob or "search" in blob:
        score += 30
    if "attack" in blob or "attack" in ctx:
        score += 4
    if "retreat" in blob and "switch" not in ctx:
        score -= 6
    if "forfeit" in blob or "__forfeit__" in blob:
        score -= 100000
    if isinstance(option, str):
        score += max(0.0, min(10.0, len(option) * 0.02))
    return score



# Optional Mistral-powered decisions. The local heuristic policy remains the safe fallback.
_MISTRAL_URL = "https://api.mistral.ai/v1/chat/completions"
_MISTRAL_MODEL = os.environ.get("MISTRAL_MODEL", "mistral-small-latest")
_MISTRAL_MAX_CALLS_PER_MATCH = 1
_MISTRAL_MIN_INTERVAL_SECONDS = 3.0
_MISTRAL_CALLS_THIS_MATCH = 0
_MISTRAL_LAST_CALL_AT = 0.0
_MISTRAL_WARNED = set()
_MISTRAL_DISABLED_FOR_PROCESS = False


def start_new_match():
    """Reset the per-match LLM budget; keep run-wide request pacing."""
    global _MISTRAL_CALLS_THIS_MATCH
    _MISTRAL_CALLS_THIS_MATCH = 0


def _mistral_warn_once(code, message):
    if code not in _MISTRAL_WARNED:
        print("MISTRAL_STRATEGY_" + code + ": " + message, file=sys.stderr, flush=True)
        _MISTRAL_WARNED.add(code)


def _compact_option(option):
    if isinstance(option, dict):
        allow = (
            "type", "index", "name", "cardId", "pokemonId", "attackId",
            "targetCardId", "sourceCardId", "text", "damage", "energies",
            "hp", "maxHp", "max_hp", "context", "label", "id", "value",
            "playerIndex", "slot", "count"
        )
        compact = {}
        for key in allow:
            if key in option:
                value = option[key]
                if isinstance(value, str) and len(value) > 180:
                    value = value[:180]
                compact[key] = value
        return compact if compact else str(option)[:180]
    if isinstance(option, str):
        return option[:180]
    return option


def _mistral_pick(legal_strings, observation, select, options):
    global _MISTRAL_CALLS_THIS_MATCH, _MISTRAL_LAST_CALL_AT, _MISTRAL_DISABLED_FOR_PROCESS
    if os.environ.get("MISTRAL_ENABLED", "true").strip().lower() not in ("1", "true", "yes", "on"):
        _mistral_warn_once("DISABLED", "Mistral calls are disabled by workflow configuration; using local strategy.")
        return None
    if _MISTRAL_DISABLED_FOR_PROCESS:
        return None
    api_key = os.environ.get("MISTRAL_API_KEY", "").strip()
    if not api_key:
        _mistral_warn_once("KEY_MISSING", "MISTRAL_API_KEY is not passed to this workflow; using local strategy.")
        return None
    if _MISTRAL_CALLS_THIS_MATCH >= _MISTRAL_MAX_CALLS_PER_MATCH:
        return None
    # Skip high-cardinality choices so every legal action stays in the prompt.
    if len(legal_strings) > 15 or len(options) > 15:
        return None

    state = {}
    for key in ("turn", "phase", "current", "players", "yourIndex", "gameState", "board"):
        if key in observation:
            state[key] = observation[key]
    state_text = json.dumps(state, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(state_text) > 1050:
        state_text = state_text[:1050] + "…[state truncated]"

    user_context = {
        "decision_type": select.get("type"),
        "decision_context": select.get("context"),
        "state": state_text,
        "options_by_index": [_compact_option(option) for option in options],
        "legal_actions": legal_strings,
        "instruction": "Choose the strongest legal action for the current Pokemon TCG position."
    }
    user_text = json.dumps(user_context, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(user_text) > 3400:
        _mistral_warn_once("PROMPT_TOO_LARGE", "Decision context was too large; using local strategy for that choice.")
        return None

    wait_for = _MISTRAL_MIN_INTERVAL_SECONDS - (time.monotonic() - _MISTRAL_LAST_CALL_AT)
    if wait_for > 0:
        time.sleep(wait_for)
    body = {
        "model": _MISTRAL_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a tactical Pokemon TCG agent. Pick exactly one action from legal_actions. "
                    "Use the state and indexed options; prefer winning lines, developing useful Pokemon, "
                    "preserving valuable resources, and attacking when advantageous. Never invent an action. "
                    "Return JSON only in the form {\"action\":\"[2]\"}, where the value is copied exactly "
                    "from legal_actions. Do not include explanations."
                )
            },
            {"role": "user", "content": user_text}
        ],
        "temperature": 0.1,
        "max_tokens": 100,
        "response_format": {"type": "json_object"}
    }
    request = urllib.request.Request(
        _MISTRAL_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "NanduAI/1.0 (Mistral API client)"
        },
        method="POST"
    )
    _MISTRAL_LAST_CALL_AT = time.monotonic()
    _MISTRAL_CALLS_THIS_MATCH += 1
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            raw_error = exc.read().decode("utf-8", "replace")
            error_payload = json.loads(raw_error) if raw_error else {}
        except Exception:
            error_payload = {}
        error_data = error_payload.get("error", {}) if isinstance(error_payload, dict) else {}
        if isinstance(error_data, dict):
            error_code = str(error_data.get("code") or "")
            error_message = str(error_data.get("message") or error_payload.get("message") or error_payload.get("detail") or "no response message")
        else:
            error_code = ""
            error_message = str(error_data or error_payload.get("message") or error_payload.get("detail") or "no response message")
        error_message = error_message.replace(api_key, "[REDACTED]")[:180]
        detail = f" ({error_code})" if error_code else ""
        error_type = str(error_data.get("type") or "") if isinstance(error_data, dict) else ""
        error_param = str(error_data.get("param") or "") if isinstance(error_data, dict) else ""
        metadata = []
        if error_type:
            metadata.append("type=" + error_type[:80])
        if error_param:
            metadata.append("param=" + error_param[:80])
        rate_headers = []
        for header_name, header_value in getattr(exc, "headers", {}).items():
            if "ratelimit" in header_name.lower() or header_name.lower() == "retry-after":
                rate_headers.append(f"{header_name}={str(header_value)[:80]}")
        diagnostic = ("; " + ", ".join(metadata)) if metadata else ""
        if rate_headers:
            diagnostic += "; " + ", ".join(rate_headers[:8])
        if exc.code in (400, 401, 402, 403, 404, 429):
            # Request, model, auth, access, billing, and rate-limit errors should not repeat across the batch.
            _MISTRAL_DISABLED_FOR_PROCESS = True
            _mistral_warn_once("API_ACCESS", f"Mistral returned HTTP {exc.code}{detail}: {error_message}{diagnostic}. Disabled more Mistral calls for this workflow run; using local strategy.")
        else:
            _mistral_warn_once("HTTP_ERROR", f"Mistral returned HTTP {exc.code}{detail}: {error_message}; falling back to local strategy.")
        return None
    except Exception as exc:
        _mistral_warn_once("REQUEST_ERROR", f"Mistral request failed ({type(exc).__name__}); falling back to local strategy.")
        return None

    try:
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        parsed = json.loads(str(content).strip())
        action = str(parsed.get("action", "")).strip()
        if action in legal_strings:
            print("MISTRAL_STRATEGY_USED:", json.dumps({"model": _MISTRAL_MODEL, "callsThisMatch": _MISTRAL_CALLS_THIS_MATCH}), flush=True)
            return action
        _mistral_warn_once("INVALID_ACTION", "The model response was not one of the legal actions; using local strategy.")
    except Exception:
        _mistral_warn_once("INVALID_RESPONSE", "Could not parse a valid action from Mistral; using local strategy.")
    return None


def act(context: dict[str, Any]):
    """Return one legal selection; never raise into the match harness."""
    legal = context.get("legalActions") if isinstance(context, dict) else None
    if not isinstance(legal, list) or not legal:
        return {"action": "[0]"}
    legal_strings = [str(x) for x in legal]
    if len(legal_strings) == 1:
        return {"action": legal_strings[0]}

    observation = context.get("observation", context.get("obs", {}))
    if not isinstance(observation, dict):
        observation = {}
    select = observation.get("select", {})
    if not isinstance(select, dict):
        select = {}
    options = select.get("option", select.get("options", []))
    if not isinstance(options, list) or not options:
        # The first legal value is a valid fallback and is preferable to a forfeit.
        return {"action": legal_strings[0]}

    # Ask Mistral for one high-impact decision per match; if anything fails, use heuristics.
    llm_action = _mistral_pick(legal_strings, observation, select, options)
    if llm_action is not None:
        return {"action": llm_action}

    scored = []
    for action in legal_strings:
        match = re.search(r"\[(\d+)\]", action)
        if not match:
            continue
        index = int(match.group(1))
        if 0 <= index < len(options):
            scored.append((_option_score(options[index], select, observation), -index, action))
    if scored:
        scored.sort(reverse=True)
        return {"action": scored[0][2]}
    return {"action": legal_strings[0]}

def choose_action(context):
    return act(context)
