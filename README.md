# NFL Pick'em Forecasting Agent

An AI agent I built for my NFL pick'em league. Each week it predicts the winner of every game, explains its reasoning, and tracks how often it's right.

**Backtested on Weeks 1–7 of the 2026 season, it went 68-38 (64.2%), beating the Vegas-favorite benchmark (61.3%), a record that would rank in the top 3% of ESPN Pick'em players.** Now running live weekly.

## Results (Weeks 1–7 backtest)

| Strategy | Accuracy |
|---|---|
| Always pick the Vegas favorite (benchmark) | 61.3% |
| Claude alone, without seeing the odds | 63.2% |
| **Blend: 70% Vegas + 30% Claude (live strategy)** | **64.2%** |

## How it works

1. Pulls each week's games and betting odds from ESPN and converts the odds into win probabilities.
2. Auto-picks clear favorites (65%+ chance to win).
3. For close games, Claude makes its own forecast from injuries, rest, and recent form, without seeing the odds. That forecast is blended with Vegas.
4. Sends a weekly brief showing Vegas's view, Claude's view, and the final pick.
5. Scores every pick after the games and tracks season accuracy.
