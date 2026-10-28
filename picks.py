"""
The decision layer: turns odds + context into a pick for every game.

  1. Heavy favorites (>= 65% Vegas win probability) are picked automatically.
  2. Close games go to Claude with an info packet.
  3. Guardrail: Claude can only pick against Vegas if it names a specific
     factor. Otherwise the code reverts the pick to the favorite.
"""

import json
import re
from datetime import datetime, timezone

import anthropic

from context import get_game_context

MODEL = "claude-sonnet-5-5"
AUTO_PICK_THRESHOLD = 0.65

SYSTEM_PROMPT = """You are an NFL analyst making straight-up winner picks for a pick'em league.

Rules:
- The Vegas implied win probability is your starting point. It is usually right.
- Only pick the underdog if you can name a specific, concrete factor in the data
  provided that the betting line may underweight (for example, a starting QB
  listed Out or Doubtful, or a large rest disadvantage). General narratives
  ("they're due", "rivalry game", "momentum") do not count.
- Use only the information provided. Do not invent injuries, stats, or news.

Respond with JSON only, no other text:
{"pick": "<team abbreviation>",
 "confidence": <number between 0.50 and 0.95>,
 "reason": "<one sentence>",
 "override_factor": "<the specific factor if you picked against the Vegas favorite, otherwise null>"}"""

client = None


def _get_client():
    global client
    if client is None:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from Secrets
    return client


def _fav_prob(game):
    if not game["vegas_favorite"]:
        return None
    return game["home_win_prob"] if game["vegas_favorite"] == game["home"] else game["away_win_prob"]


def _ask_claude(game, ctx):
    packet = {
        "matchup": f"{game['away']} at {game['home']}",
        "kickoff": game["kickoff"],
        "records": {game["away"]: game["away_record"], game["home"]: game["home_record"]},
        "spread": game["spread"],
        "vegas_win_probability": {game["away"]: game["away_win_prob"], game["home"]: game["home_win_prob"]},
        "vegas_favorite": game["vegas_favorite"],
        "team_context": ctx,
    }
    resp = _get_client().messages.create(
        model=MODEL,
        max_tokens=400,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(packet, indent=2)}],
    )
    text = resp.content[0].text
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0)) if match else {}


def pick_game(game):
    fav = game["vegas_favorite"]
    fav_p = _fav_prob(game)
    base = {"game_id": game["game_id"], "matchup": f"{game['away']} @ {game['home']}",
            "vegas_favorite": fav, "vegas_prob": fav_p}

    # 1. Heavy favorite -> automatic pick
    if fav and fav_p and fav_p >= AUTO_PICK_THRESHOLD:
        return {**base, "pick": fav, "method": "auto", "confidence": round(fav_p, 2),
                "reason": f"Heavy Vegas favorite ({fav_p:.0%}).", "upset_call": False}

    # 2. Close game (or no odds) -> Claude reviews the info packet
    ctx = get_game_context(game)
    try:
        ai = _ask_claude(game, ctx)
    except Exception as e:
        ai = {"reason": f"AI call failed ({e}); defaulted to favorite."}

    pick = ai.get("pick")
    valid_teams = (game["home"], game["away"])
    note = None

    # 3. Guardrails
    if pick not in valid_teams:
        pick = fav or game["home"]
        note = "Guardrail: invalid pick, reverted to favorite."
    elif fav and pick != fav and not ai.get("override_factor"):
        pick = fav
        note = "Guardrail: upset pick had no specific factor, reverted to favorite."

    return {**base, "pick": pick, "method": "ai",
            "confidence": ai.get("confidence"),
            "reason": ai.get("reason", ""),
            "override_factor": ai.get("override_factor") if pick != fav else None,
            "upset_call": bool(fav and pick != fav),
            "guardrail_note": note,
            "context_used": ctx}


def make_picks(week, games):
    picks, skipped = [], []
    for g in games:
        if g["status"] != "pre":  # don't "predict" games that already started
            skipped.append(f"{g['away']} @ {g['home']}")
            continue
        picks.append(pick_game(g))
    result = {"week": week, "made_at": datetime.now(timezone.utc).isoformat(),
              "model": MODEL, "picks": picks, "skipped_already_started": skipped}
    with open(f"picks_week{week}.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


def format_brief(result):
    lines = [f"NFL WEEK {result['week']} PICKS", ""]
    auto = [p for p in result["picks"] if p["method"] == "auto"]
    ai = [p for p in result["picks"] if p["method"] == "ai"]

    lines.append(f"CLOSE GAMES - AGENT ANALYSIS ({len(ai)})")
    for p in ai:
        conf = f"{p['confidence']:.0%}" if isinstance(p.get("confidence"), (int, float)) else "-"
        tag = "  [UPSET CALL]" if p["upset_call"] else ""
        lines.append(f"- {p['matchup']}: {p['pick']} ({conf}){tag}")
        lines.append(f"    {p['reason']}")
        if p.get("override_factor"):
            lines.append(f"    Why vs. Vegas: {p['override_factor']}")
        if p.get("guardrail_note"):
            lines.append(f"    {p['guardrail_note']}")
    lines.append("")
    lines.append(f"HEAVY FAVORITES - AUTO PICKS ({len(auto)})")
    for p in auto:
        lines.append(f"- {p['matchup']}: {p['pick']} ({p['vegas_prob']:.0%})")
    if result["skipped_already_started"]:
        lines += ["", "Skipped (already started): " + ", ".join(result["skipped_already_started"])]
    upsets = sum(p["upset_call"] for p in result["picks"])
    lines += ["", f"{len(result['picks'])} picks | {upsets} upset call(s)"]
    return "\n".join(lines)
