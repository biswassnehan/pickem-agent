"""
The evaluation layer: scores each week's picks against real results and
keeps a season-long scoreboard vs. the "always pick the Vegas favorite" benchmark.
"""

import csv
import json
import os

from fetch_games import fetch_week

RESULTS_FILE = "results.csv"
FIELDS = ["week", "game_id", "matchup", "agent_pick", "vegas_favorite", "winner",
          "agent_correct", "vegas_correct", "method", "upset_call"]


def score_week(week):
    picks_file = f"picks_week{week}.json"
    if not os.path.exists(picks_file):
        print(f"No picks saved for week {week}.")
        return
    with open(picks_file) as f:
        picks = json.load(f)["picks"]

    _, games = fetch_week(week)
    winners = {g["game_id"]: g["winner"] for g in games if g["status"] == "post"}

    rows = []
    for p in picks:
        winner = winners.get(p["game_id"])
        if not winner:  # not finished yet, or a tie
            continue
        rows.append({
            "week": week, "game_id": p["game_id"], "matchup": p["matchup"],
            "agent_pick": p["pick"], "vegas_favorite": p["vegas_favorite"], "winner": winner,
            "agent_correct": int(p["pick"] == winner),
            "vegas_correct": int(p["vegas_favorite"] == winner) if p["vegas_favorite"] else "",
            "method": p["method"], "upset_call": int(p["upset_call"]),
        })

    # Replace any earlier rows for this week, then save
    existing = []
    if os.path.exists(RESULTS_FILE):
        with open(RESULTS_FILE) as f:
            existing = [r for r in csv.DictReader(f) if str(r["week"]) != str(week)]
    with open(RESULTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(existing + rows)

    agent = sum(r["agent_correct"] for r in rows)
    vegas = sum(r["vegas_correct"] for r in rows if r["vegas_correct"] != "")
    print(f"Week {week}: agent {agent}/{len(rows)} | Vegas favorites {vegas}/{len(rows)}")


def _pct(hits, n):
    return f"{hits}/{n} ({hits / n:.0%})" if n else "n/a"


def season_summary():
    if not os.path.exists(RESULTS_FILE):
        return "No results yet."
    with open(RESULTS_FILE) as f:
        rows = list(csv.DictReader(f))
    ints = lambda rs, k: sum(int(r[k]) for r in rs if r[k] != "")

    close = [r for r in rows if r["method"] == "ai"]
    upsets = [r for r in rows if r["upset_call"] == "1"]
    weeks = sorted({int(r["week"]) for r in rows})

    return "\n".join([
        f"SEASON SCOREBOARD (weeks {weeks[0]}-{weeks[-1]})",
        f"Agent overall:          {_pct(ints(rows, 'agent_correct'), len(rows))}",
        f"Vegas favorites:        {_pct(ints(rows, 'vegas_correct'), len(rows))}",
        f"Close games - agent:    {_pct(ints(close, 'agent_correct'), len(close))}",
        f"Close games - Vegas:    {_pct(ints(close, 'vegas_correct'), len(close))}",
        f"Upset calls that hit:   {_pct(ints(upsets, 'agent_correct'), len(upsets))}",
    ])
