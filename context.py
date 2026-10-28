"""
Builds the info packet for a close game: recent form, rest days, and key injuries.

Uses ESPN's public game summary data (no login). Everything is wrapped in
safe lookups because ESPN occasionally changes field names -- if something
is missing, the packet just has less detail rather than crashing.
"""

from datetime import datetime
import requests

SUMMARY_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary"

KEY_STATUSES = ("Out", "Doubtful", "Questionable")
# Positions that usually matter most for a single game's outcome
POSITION_PRIORITY = {"QB": 0, "RB": 1, "WR": 1, "TE": 2, "OT": 2, "LT": 2, "EDGE": 3, "DE": 3, "CB": 3}


def _parse_date(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def fetch_summary(game_id):
    """Download ESPN's full summary for one game (form, injuries, odds)."""
    resp = requests.get(SUMMARY_URL, params={"event": game_id}, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_game_context(game, data=None):
    """Return {team_abbr: {recent_games, days_rest, injuries}} for one game."""
    if data is None:
        try:
            data = fetch_summary(game["game_id"])
        except Exception as e:
            return {"note": f"Context unavailable ({e})"}

    kickoff = _parse_date(game["kickoff"])
    ctx = {game["home"]: {}, game["away"]: {}}

    # --- Recent form + rest days ---
    for block in data.get("lastFiveGames") or []:
        abbr = (block.get("team") or {}).get("abbreviation")
        if abbr not in ctx:
            continue
        events = []
        for ev in block.get("events") or []:
            date = ev.get("gameDate")
            events.append({
                "date": _parse_date(date) if date else None,
                "summary": " ".join(str(x) for x in [
                    ev.get("gameResult"), ev.get("score"), ev.get("atVs"),
                    (ev.get("opponent") or {}).get("abbreviation"),
                ] if x),
            })
        dated = sorted([e for e in events if e["date"] and e["date"] < kickoff],
                       key=lambda e: e["date"], reverse=True)
        ctx[abbr]["recent_games"] = [e["summary"] for e in (dated or events)][:4]
        if dated:
            ctx[abbr]["days_rest"] = (kickoff - dated[0]["date"]).days

    # --- Key injuries (skip long-term IR; Vegas has already priced those in) ---
    for block in data.get("injuries") or []:
        abbr = (block.get("team") or {}).get("abbreviation")
        if abbr not in ctx:
            continue
        notable = []
        for inj in block.get("injuries") or []:
            status = inj.get("status") or (inj.get("type") or {}).get("description")
            if status not in KEY_STATUSES:
                continue
            athlete = inj.get("athlete") or {}
            pos = (athlete.get("position") or {}).get("abbreviation", "")
            notable.append((POSITION_PRIORITY.get(pos, 9),
                            f"{athlete.get('displayName', '?')} ({pos}) - {status}"))
        ctx[abbr]["injuries"] = [txt for _, txt in sorted(notable)][:8]

    return ctx
