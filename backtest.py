"""
Backtest: replay past weeks as if the agent were picking before each game,
then score every strategy against what actually happened.

Strategies compared:
  vegas      always pick the Vegas favorite (the benchmark)
  guardrail  Claude sees odds; may only pick an upset with a specific factor
  blind      Claude's own pick, made without seeing any odds
  blend      70% Vegas + 30% Claude's blind forecast

Avoiding look-ahead bias (accidentally using future information):
  - Team records are rebuilt from games BEFORE each week, not taken from ESPN
    (which can show the record after the game).
  - Recent form only includes games played before kickoff.
  - Final scores and winners are never sent to Claude.
  - Claude's knowledge cutoff (mid-2026) is before this season started.
Known limitation: ESPN's historical injury lists may reflect final game-week
statuses rather than exactly what was known mid-week.

Each finished week is saved to backtest_weekN.json, so if the run stops
partway, running it again picks up where it left off.
"""

import csv
import json
import os

from context import fetch_summary, get_game_context
from fetch_games import fetch_week, odds_to_probs
from picks import (AUTO_PICK_THRESHOLD, ask_blind, ask_guardrail,
                   decide_blend, decide_blind, decide_guardrail)

STRATEGIES = ["vegas", "guardrail", "blind", "blend"]
RESULTS_FILE = "backtest_results.csv"


def pregame_records(all_weeks, week):
    """Each team's W-L(-T) record using only games from earlier weeks."""
    rec = {}
    for w, games in all_weeks.items():
        if w >= week:
            continue
        for g in games:
            if g["status"] != "post":
                continue
            for team in (g["home"], g["away"]):
                rec.setdefault(team, [0, 0, 0])
            if g["winner"] is None:  # tie
                rec[g["home"]][2] += 1
                rec[g["away"]][2] += 1
            else:
                loser = g["away"] if g["winner"] == g["home"] else g["home"]
                rec[g["winner"]][0] += 1
                rec[loser][1] += 1
    return {t: f"{w}-{l}" + (f"-{ti}" if ti else "") for t, (w, l, ti) in rec.items()}


def backtest_game(g, records):
    """Replay one finished game with outcome information stripped out."""
    winner = g["winner"]
    game = {**g, "status": "pre", "winner": None,
            "home_record": records.get(g["home"], "0-0"),
            "away_record": records.get(g["away"], "0-0")}

    summary = None
    try:
        summary = fetch_summary(g["game_id"])
    except Exception:
        pass

    # Finished games sometimes lose their odds on the scoreboard; ESPN's game
    # summary keeps the pre-game line under "pickcenter".
    if not game["vegas_favorite"] and summary:
        for odds in summary.get("pickcenter") or []:
            filled = odds_to_probs(odds, game["home"], game["away"])
            if filled["vegas_favorite"]:
                game.update(filled)
                break

    fav = game["vegas_favorite"]
    fav_p = (game["home_win_prob"] if fav == game["home"] else game["away_win_prob"]) if fav else None
    row = {"week": None, "game_id": g["game_id"], "matchup": f"{g['away']} @ {g['home']}",
           "winner": winner, "vegas_favorite": fav, "vegas_prob": fav_p,
           "close_game": int(not (fav and fav_p and fav_p >= AUTO_PICK_THRESHOLD))}

    if not row["close_game"]:
        picks = {s: fav for s in STRATEGIES}
    else:
        ctx = get_game_context(game, summary) if summary else {}
        picks = {"vegas": fav}
        try:
            picks["guardrail"], _ = decide_guardrail(game, ask_guardrail(game, ctx))
        except Exception as e:
            print(f"    guardrail call failed ({e}); using favorite")
            picks["guardrail"] = fav
        try:
            blind_ai = ask_blind(game, ctx)
            picks["blind"], _ = decide_blind(game, blind_ai)
            picks["blend"], _, _ = decide_blend(game, blind_ai)
        except Exception as e:
            print(f"    blind call failed ({e}); using favorite")
            picks["blind"] = picks["blend"] = fav

    for s in STRATEGIES:
        row[f"{s}_pick"] = picks[s]
        row[f"{s}_correct"] = int(picks[s] == winner) if picks[s] else 0
    return row


def run_backtest(first_week=1, last_week=7):
    print(f"Loading results for weeks 1-{last_week}...")
    all_weeks = {w: fetch_week(w)[1] for w in range(1, last_week + 1)}

    all_rows = []
    for week in range(first_week, last_week + 1):
        cache = f"backtest_week{week}.json"
        if os.path.exists(cache):
            with open(cache) as f:
                rows = json.load(f)
            print(f"Week {week}: loaded {len(rows)} saved games")
            all_rows += rows
            continue

        records = pregame_records(all_weeks, week)
        finished = [g for g in all_weeks[week] if g["status"] == "post" and g["winner"]]
        print(f"Week {week}: replaying {len(finished)} games...")
        rows = []
        for g in finished:
            row = backtest_game(g, records)
            row["week"] = week
            rows.append(row)
            flag = "close" if row["close_game"] else "auto"
            print(f"  {row['matchup']:<12} {flag:<6} winner {row['winner']:<4} "
                  + " ".join(f"{s}:{row[s + '_pick']}" for s in STRATEGIES[1:]))
        with open(cache, "w") as f:
            json.dump(rows, f, indent=2)
        all_rows += rows

    with open(RESULTS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(all_rows[0].keys()))
        writer.writeheader()
        writer.writerows(all_rows)

    print()
    print(summarize(all_rows, first_week, last_week))


def summarize(rows, first_week, last_week):
    close = [r for r in rows if r["close_game"]]

    def score(rs, s):
        n = len(rs)
        hits = sum(r[f"{s}_correct"] for r in rs)
        return f"{hits}/{n} ({hits / n:.1%})" if n else "n/a"

    def upsets(s):
        calls = [r for r in rows if r[f"{s}_pick"] != r["vegas_favorite"]]
        hits = sum(r[f"{s}_correct"] for r in calls)
        return f"{hits}/{len(calls)}" if calls else "0 calls"

    lines = [f"BACKTEST RESULTS - WEEKS {first_week}-{last_week}  ({len(rows)} games, {len(close)} close)",
             f"{'Strategy':<11}{'All games':<20}{'Close games':<20}Upset calls that hit"]
    for s in STRATEGIES:
        lines.append(f"{s:<11}{score(rows, s):<20}{score(close, s):<20}{upsets(s) if s != 'vegas' else '-'}")
    best = max(STRATEGIES, key=lambda s: sum(r[f"{s}_correct"] for r in rows))
    lines += ["", f"Best overall: {best}. To use it live, set STRATEGY = \"{best}\" in picks.py"
              + (" (vegas = keep 'guardrail', the closest live option)." if best == "vegas" else ".")]
    return "\n".join(lines)
