"""
The decision layer: turns odds + context into a pick for every game.

Heavy favorites (>= 65% Vegas win probability) are always picked automatically.
Close games are decided by one of three strategies (set STRATEGY below):

  "guardrail"  Claude sees the Vegas odds and may only pick the underdog if it
               names a specific factor. Otherwise the code reverts to the favorite.
  "blind"      Claude forecasts WITHOUT seeing the odds. Its pick is used as-is.
  "blend"      Claude's blind forecast is combined with Vegas (70% Vegas / 30%
               Claude) and the team above 50% is picked.

Run `python3 main.py backtest` to compare all three on past weeks, then set
STRATEGY to whichever scored best.
"""

import json
import re
from datetime import datetime, timezone

import anthropic

from context import get_game_context

MODEL = "claude-sonnet-5-5"
AUTO_PICK_THRESHOLD = 0.65
STRATEGY = "blend"        # "guardrail", "blind", or "blend"
BLEND_VEGAS_WEIGHT = 0.70     # how much the blend trusts Vegas vs. Claude

GUARDRAIL_PROMPT = """You are an NFL analyst making straight-up winner picks for a pick'em league.

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

BLIND_PROMPT = """You are an NFL analyst forecasting the straight-up winner of one game.

You are deliberately NOT shown betting odds. Form your own independent view from
the data provided: team records, recent results and scores, days of rest,
home field, and injuries.

Rules:
- Use only the information provided. Do not invent injuries, stats, or news.
- Home field is typically worth a few percentage points of win probability.
- Be calibrated: most NFL games are between 40% and 75% for the favorite.

Respond with JSON only, no other text:
{"pick": "<team abbreviation>",
 "win_probability": <probability your pick wins, between 0.50 and 0.95>,
 "reason": "<one sentence>"}"""

client = None


def _get_client():
    global client
    if client is None:
        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from Secrets
    return client


def _call_claude(system, packet):
    resp = _get_client().messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": json.dumps(packet, indent=2)}],
    )
    # Claude may "think" before answering; keep only the final text blocks
    text = "".join(b.text for b in resp.content if b.type == "text")
    match = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(match.group(0)) if match else {}


def _fav_prob(game):
    if not game["vegas_favorite"]:
        return None
    return game["home_win_prob"] if game["vegas_favorite"] == game["home"] else game["away_win_prob"]


def _base_packet(game, ctx):
    return {
        "matchup": f"{game['away']} at {game['home']}",
        "home_team": game["home"],
        "away_team": game["away"],
        "kickoff": game["kickoff"],
        "records": {game["away"]: game["away_record"], game["home"]: game["home_record"]},
        "team_context": ctx,
    }


# ---------- The three strategies for close games ----------

def ask_guardrail(game, ctx):
    packet = {**_base_packet(game, ctx),
              "spread": game["spread"],
              "vegas_win_probability": {game["away"]: game["away_win_prob"],
                                        game["home"]: game["home_win_prob"]},
              "vegas_favorite": game["vegas_favorite"]}
    return _call_claude(GUARDRAIL_PROMPT, packet)


def ask_blind(game, ctx):
    return _call_claude(BLIND_PROMPT, _base_packet(game, ctx))  # no odds included


def decide_guardrail(game, ai):
    fav = game["vegas_favorite"]
    pick, note = ai.get("pick"), None
    if pick not in (game["home"], game["away"]):
        pick, note = fav or game["home"], "Guardrail: invalid pick, reverted to favorite."
    elif fav and pick != fav and not ai.get("override_factor"):
        pick, note = fav, "Guardrail: upset pick had no specific factor, reverted to favorite."
    return pick, note


def decide_blind(game, ai):
    pick = ai.get("pick")
    if pick not in (game["home"], game["away"]):
        return game["vegas_favorite"] or game["home"], "Invalid pick, reverted to favorite."
    return pick, None


def decide_blend(game, ai):
    """Combine Vegas and Claude's blind probability for the HOME team."""
    pick, p = ai.get("pick"), ai.get("win_probability")
    if pick not in (game["home"], game["away"]) or not isinstance(p, (int, float)):
        return game["vegas_favorite"] or game["home"], None, "Invalid AI answer, reverted to favorite."
    claude_home = p if pick == game["home"] else 1 - p
    vegas_home = game["home_win_prob"]
    if vegas_home is None:
        blended = claude_home
    else:
        blended = BLEND_VEGAS_WEIGHT * vegas_home + (1 - BLEND_VEGAS_WEIGHT) * claude_home
    final = game["home"] if blended >= 0.5 else game["away"]
    return final, round(max(blended, 1 - blended), 3), None


# ---------- Live picks ----------

def pick_game(game, strategy=STRATEGY):
    fav = game["vegas_favorite"]
    fav_p = _fav_prob(game)
    base = {"game_id": game["game_id"], "matchup": f"{game['away']} @ {game['home']}",
            "vegas_favorite": fav, "vegas_prob": fav_p}

    # Heavy favorite -> automatic pick
    if fav and fav_p and fav_p >= AUTO_PICK_THRESHOLD:
        return {**base, "pick": fav, "method": "auto", "confidence": round(fav_p, 2),
                "reason": f"Heavy Vegas favorite ({fav_p:.0%}).", "upset_call": False}

    ctx = get_game_context(game)
    override_factor = None
    claude_pick = claude_prob = None
    try:
        if strategy == "guardrail":
            ai = ask_guardrail(game, ctx)
            pick, note = decide_guardrail(game, ai)
            confidence = ai.get("confidence")
            override_factor = ai.get("override_factor") if pick != fav else None
        elif strategy == "blind":
            ai = ask_blind(game, ctx)
            pick, note = decide_blind(game, ai)
            confidence = ai.get("win_probability")
            claude_pick, claude_prob = ai.get("pick"), ai.get("win_probability")
        else:  # blend
            ai = ask_blind(game, ctx)
            pick, confidence, note = decide_blend(game, ai)
            claude_pick, claude_prob = ai.get("pick"), ai.get("win_probability")
    except Exception as e:
        ai, pick, confidence = {}, fav or game["home"], None
        note = f"AI call failed ({e}); defaulted to favorite."

    return {**base, "pick": pick, "method": "ai", "strategy": strategy,
            "confidence": confidence, "reason": ai.get("reason", ""),
            "override_factor": override_factor,
            "claude_pick": claude_pick, "claude_prob": claude_prob,
            "upset_call": bool(fav and pick != fav),
            "guardrail_note": note, "context_used": ctx}


def make_picks(week, games):
    picks, skipped = [], []
    for g in games:
        if g["status"] != "pre":  # don't "predict" games that already started
            skipped.append(f"{g['away']} @ {g['home']}")
            continue
        picks.append(pick_game(g))
    result = {"week": week, "made_at": datetime.now(timezone.utc).isoformat(),
              "model": MODEL, "strategy": STRATEGY,
              "picks": picks, "skipped_already_started": skipped}
    with open(f"picks_week{week}.json", "w") as f:
        json.dump(result, f, indent=2)
    return result


def format_brief(result):
    lines = [f"NFL WEEK {result['week']} PICKS  (strategy: {result.get('strategy', STRATEGY)})", ""]
    auto = [p for p in result["picks"] if p["method"] == "auto"]
    ai = [p for p in result["picks"] if p["method"] == "ai"]

    pct = lambda x: f"{x:.0%}" if isinstance(x, (int, float)) else "-"
    lines.append(f"CLOSE GAMES - AGENT ANALYSIS ({len(ai)})")
    for p in ai:
        torn = p.get("claude_pick") and p["claude_pick"] != p["pick"]
        tag = "  [UPSET CALL]" if p["upset_call"] else ("  [CLAUDE LEANS OTHER WAY]" if torn else "")
        lines.append(f"- {p['matchup']}: PICK {p['pick']} ({pct(p.get('confidence'))}){tag}")
        if p.get("claude_pick"):
            views = [f"Vegas: {p['vegas_favorite']} {pct(p.get('vegas_prob'))}",
                     f"Claude: {p['claude_pick']} {pct(p.get('claude_prob'))}"]
            if p.get("strategy") == "blend":
                views.append(f"Blend -> {p['pick']}")
            lines.append("    " + " | ".join(views))
            lines.append(f"    Claude's read: {p['reason']}")
        else:
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
    leans = sum(1 for p in ai if p.get("claude_pick") and p["claude_pick"] != p["pick"])
    lines += ["", f"{len(result['picks'])} picks | {upsets} upset call(s) | "
                  f"{leans} game(s) where Claude leans the other way"]
    return "\n".join(lines)
