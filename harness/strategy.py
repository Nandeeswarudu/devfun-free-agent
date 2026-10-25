"""Greedy, sandbox-safe TCG action policy for DevFun's hosted engine."""
from __future__ import annotations

import json
import re
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
