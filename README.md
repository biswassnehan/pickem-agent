# NFL Pick'em Agent

An AI agent that forecasts the winner of every NFL game each week, explains its reasoning, and measures its own accuracy against a market benchmark (the Vegas favorite).

Built to practice a pattern that applies directly to business operations: **pull data from a source of truth → apply rules → use AI for judgment calls with guardrails → deliver a decision brief on a schedule → measure whether the decisions were right.**

## How it works

| Layer | What it does | File |
|---|---|---|
| Data pull | Pulls the week's schedule, records, and betting odds from ESPN's public data; converts odds to win probabilities | `fetch_games.py` |
| Context | For close games, gathers recent form, days of rest, and key injuries | `context.py` |
| Decision | Heavy favorites (≥65%) are picked automatically; close games go to Claude with an info packet | `picks.py` |
| Guardrails | Claude can only pick an underdog if it cites a specific factor; otherwise the code reverts to the favorite | `picks.py` |
| Delivery | Formats a weekly brief and emails it | `notify.py` |
| Evaluation | Scores every pick against real results and tracks a season scoreboard vs. the Vegas benchmark | `tracker.py` |

## Design choices

- **Code does the math; AI makes judgment calls.** Probabilities and scoring are deterministic. Claude only reasons about close games, using data it is given, and is instructed not to invent facts.
- **The benchmark is honest.** Always picking the Vegas favorite is a strong baseline. The agent is judged against it, with close games and upset calls reported separately.
- **Every decision is logged** with its reasoning, so wrong calls can be reviewed and the rules improved.

## Results

| Metric | Agent | Vegas favorite |
|---|---|---|
| Overall accuracy | _TBD_ | _TBD_ |
| Close games | _TBD_ | _TBD_ |
| Upset calls that hit | _TBD_ | — |

_Updated weekly from `results.csv`._

## Business application

Replace NFL games with sales opportunities and this becomes a **weekly deal-forecasting agent**: pull pipeline data from the CRM, auto-classify clear-cut deals, have AI review borderline deals with context (activity, stage age, stakeholder changes), send the brief to sales leaders before the forecast call, and track forecast accuracy over the quarter.

## Run it

```
pip install -r requirements.txt
python main.py            # make this week's picks
python main.py score      # score last week
python main.py summary    # season scoreboard
```

Requires `ANTHROPIC_API_KEY`. Email delivery is optional (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`).
