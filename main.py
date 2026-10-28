"""
NFL Pick'em Agent

  python main.py              -> make this week's picks, print + email the brief
  python main.py score        -> score last week's picks against real results
  python main.py score 9      -> score a specific week
  python main.py summary      -> season scoreboard vs. Vegas favorites
"""

import sys

from fetch_games import fetch_week
from notify import send_email
from picks import format_brief, make_picks
from tracker import score_week, season_summary


def run_picks():
    week, games = fetch_week()
    print(f"Making picks for week {week} ({len(games)} games)...\n")
    result = make_picks(week, games)
    brief = format_brief(result)
    summary = season_summary()
    if summary != "No results yet.":
        brief += "\n\n" + summary
    print(brief)
    send_email(f"Pick'em Agent - Week {week} Picks", brief)


def run_score(week=None):
    if week is None:
        current, _ = fetch_week()
        week = current - 1
    score_week(week)
    print()
    print(season_summary())


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "picks"
    if cmd == "score":
        run_score(int(sys.argv[2]) if len(sys.argv) > 2 else None)
    elif cmd == "summary":
        print(season_summary())
    else:
        run_picks()
