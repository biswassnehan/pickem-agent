# NFL Pick'em Forecasting Agent

An AI agent I built for my NFL pick'em league. Every week it forecasts the winner of every game, explains its reasoning, and tracks its own accuracy against a market benchmark: always picking the Vegas favorite.

**Backtest, Weeks 1–7 of the 2026 season: 68-38 (64.2%), beating the Vegas-favorite benchmark (61.3%).** For reference, my own picks over the same 106 games went 66-40, which ESPN ranks in the 97th percentile of its NFL Pick'em players. Now running live weekly.

## Results

### Backtest: Weeks 1–7 (106 games, 60 of them close)

I tested four strategies by replaying each week as if the agent were picking before kickoff:

| Strategy | How it picks | All games | Close games | Upset calls that hit |
|---|---|---|---|---|
| Vegas favorite | Always picks the betting favorite (benchmark) | 65/106 (61.3%) | 33/60 (55.0%) | — |
| Guardrail | Claude sees the odds; can only pick an upset with a specific reason | 65/106 (61.3%) | 33/60 (55.0%) | 0 calls |
| Blind | Claude forecasts without seeing the odds | 67/106 (63.2%) | 35/60 (58.3%) | 10/18 |
| **Blend** | **70% Vegas + 30% Claude's blind forecast** | **68/106 (64.2%)** | **36/60 (60.0%)** | **3/3** |

Blend scored best, so it is the strategy running live.

### Live: Week 8 onward

| Metric | Agent | Vegas favorite |
|---|---|---|
| Overall accuracy | _updated weekly_ | _updated weekly_ |

_Live results are logged in `results.csv`, kept separate from the backtest._

## How it works

1. **Pull data.** Each week's schedule, team records, and betting odds come from ESPN's public data. Betting odds are converted into win probabilities, with the bookmaker's margin removed.
2. **Auto-pick clear favorites.** Any team with a 65%+ chance to win is picked automatically. Calling upsets on lopsided games mostly costs wins.
3. **Analyze close games.** For the rest, the agent gathers recent results, days of rest, and key injuries. Claude makes an independent forecast *without seeing the odds*, and that forecast is blended with Vegas.
4. **Deliver a brief.** Each pick shows the Vegas view, Claude's view, the final pick, and Claude's reasoning, and flags games where Claude disagrees with the market.
5. **Score the results.** After each week, picks are scored against real outcomes and added to a season scoreboard.

## Design decisions

- **Code does the math; AI makes the judgment calls.** Probabilities, blending, and scoring are plain code. Claude only reasons about close games, using data it is given, and is instructed not to invent facts.
- **Strategy chosen by evidence, not instinct.** Four approaches were backtested, and the best performer went live.
- **No look-ahead bias in the backtest.** Records are rebuilt from earlier weeks only, recent form includes only games before kickoff, results are never sent to Claude, and the model's knowledge cutoff (mid-2026) predates the season. Known limitation: ESPN's historical injury lists may reflect final game-week statuses.
- **An honest benchmark.** The Vegas favorite is a strong baseline, so beating it at all is meaningful. With 106 games, a 3-game edge is encouraging but not conclusive; the live season will show whether it holds.

## Business application

Swap NFL games for sales opportunities and this becomes a weekly **deal-forecasting agent**: pull pipeline data from the CRM, auto-classify clear-cut deals, have AI independently assess borderline ones from activity and context, blend that with the rep's own forecast, deliver a brief before the forecast call, and track accuracy over the quarter.

## Files

| File | Role |
|---|---|
| `fetch_games.py` | Pulls games and odds; converts odds to probabilities |
| `context.py` | Builds each close game's info packet (form, rest, injuries) |
| `picks.py` | Decision logic for all strategies, plus the weekly brief |
| `backtest.py` | Replays past weeks and compares strategies |
| `tracker.py` | Scores live picks and keeps the season scoreboard |
| `notify.py` | Optional email delivery |
| `main.py` | Commands to run everything |

## Run it

```
pip install -r requirements.txt
python main.py            # make this week's picks
python main.py score      # score last week's picks
python main.py summary    # live season scoreboard
python main.py backtest   # replay weeks 1-7 and compare strategies
```

Requires an `ANTHROPIC_API_KEY` environment variable. Built with Python and the Claude API (Sonnet 5.5).
