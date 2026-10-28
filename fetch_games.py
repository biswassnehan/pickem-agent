"""
Step 1 (pick'em version): Pull this week's NFL games and betting odds.

Uses ESPN's public scoreboard data -- no login, no cookies.
Prints every game with records, the Vegas favorite, and implied win
probability, then saves the data to a JSON file for the next steps.

Setup (in Replit):
  1. Shell tab:  pip install requests
  2. Click Run.
"""

import json
import requests

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"


def implied_prob(moneyline):
    """Convert American moneyline odds (e.g. -150, +130) to a win probability."""
    if moneyline is None:
        return None
    ml = float(moneyline)
    return -ml / (-ml + 100) if ml < 0 else 100 / (ml + 100)


def parse_moneyline(odds, side):
    """ESPN has used a few odds formats over time; try each one."""
    # Older format: odds["homeTeamOdds"]["moneyLine"]
    team_odds = odds.get(f"{side}TeamOdds") or {}
    if team_odds.get("moneyLine") is not None:
        return team_odds["moneyLine"]
    # Newer format: odds["moneyline"]["home"]["close"]["odds"] (as a string)
    ml = (odds.get("moneyline") or {}).get(side) or {}
    for key in ("close", "open", "current"):
        val = (ml.get(key) or {}).get("odds")
        if val not in (None, "", "OFF", "EVEN"):
            try:
                return int(str(val).replace("+", ""))
            except ValueError:
                pass
    return None


def fetch_week(week=None, season=2026):
    params = {"seasontype": 2}  # 2 = regular season
    if week:
        params.update({"week": week, "dates": season})
    resp = requests.get(SCOREBOARD_URL, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()

    week_num = (data.get("week") or {}).get("number")
    games = []
    for event in data.get("events", []):
        comp = event["competitions"][0]
        teams = {c["homeAway"]: c for c in comp["competitors"]}
        home, away = teams["home"], teams["away"]

        def record(c):
            recs = c.get("records") or []
            return recs[0]["summary"] if recs else "0-0"

        odds = (comp.get("odds") or [{}])[0]
        home_ml = parse_moneyline(odds, "home")
        away_ml = parse_moneyline(odds, "away")
        home_p, away_p = implied_prob(home_ml), implied_prob(away_ml)

        # Remove the bookmaker's margin so the two probabilities add to 100%
        if home_p and away_p:
            total = home_p + away_p
            home_p, away_p = home_p / total, away_p / total

        state = comp["status"]["type"]["state"]  # "pre", "in", or "post"
        winner = None
        if state == "post":
            winner = next((c["team"]["abbreviation"] for c in comp["competitors"]
                           if c.get("winner")), None)

        favorite = None
        if home_p and away_p:
            favorite = home["team"]["abbreviation"] if home_p >= away_p else away["team"]["abbreviation"]

        games.append({
            "game_id": event["id"],
            "kickoff": event["date"],
            "home": home["team"]["abbreviation"],
            "away": away["team"]["abbreviation"],
            "home_record": record(home),
            "away_record": record(away),
            "spread": odds.get("details"),          # e.g. "KC -3.5"
            "home_moneyline": home_ml,
            "away_moneyline": away_ml,
            "home_win_prob": round(home_p, 3) if home_p else None,
            "away_win_prob": round(away_p, 3) if away_p else None,
            "vegas_favorite": favorite,
            "status": state,
            "winner": winner,
        })
    return week_num, games


if __name__ == "__main__":
    week, games = fetch_week()
    print(f"NFL Week {week}: {len(games)} games\n")
    print(f"{'Matchup':<14}{'Records':<14}{'Spread':<12}{'Fav':<6}{'Win %':>6}  Status")
    for g in games:
        matchup = f"{g['away']} @ {g['home']}"
        records = f"{g['away_record']} / {g['home_record']}"
        fav = g["vegas_favorite"] or "-"
        prob = g["home_win_prob"] if fav == g["home"] else g["away_win_prob"]
        prob_str = f"{prob:.0%}" if prob else "-"
        status = f"Final: {g['winner']} won" if g["status"] == "post" else g["status"]
        print(f"{matchup:<14}{records:<14}{(g['spread'] or '-'):<12}{fav:<6}{prob_str:>6}  {status}")

    outfile = f"games_week{week}.json"
    with open(outfile, "w") as f:
        json.dump({"week": week, "games": games}, f, indent=2)
    print(f"\nSaved to {outfile}")
