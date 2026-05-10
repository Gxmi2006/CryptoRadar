# CryptoRadar

> Backend-only crypto signal intelligence for Binance Spot markets, local AI analysis, and Telegram push alerts.

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](#requirements)
[![No Trading](https://img.shields.io/badge/Trading-disabled-red)](#safety-first)
[![Local AI](https://img.shields.io/badge/AI-LM%20Studio%20%7C%20Ollama-green)](#local-ai-analysis)
[![Telegram](https://img.shields.io/badge/Alerts-Telegram-26A5E4)](#telegram-push-notifications)

CryptoRadar is a terminal-based crypto market signal bot. It discovers active Binance Spot markets, scans broad token coverage by default, analyzes technical conditions, uses local AI when available, and sends clean Telegram notifications when strong signals appear.

There is no website, no dashboard, and no frontend. CryptoRadar runs from the terminal or as a background service.

## Main Focus

| Focus | What CryptoRadar Does |
| --- | --- |
| Broad token scanning | Discovers active Binance Spot symbols and analyzes nearly every token that passes your quote, volume, and watchlist filters. USDT pairs are enabled by default. |
| Local AI analysis | Uses LM Studio or Ollama locally to reason over market data, indicators, knowledge snippets, and signal history. No cloud AI is required by default. |
| Telegram push alerts | Sends short, mobile-friendly Telegram alerts for eligible BUY, SELL, and HIGH_RISK signals. |
| Learning loop | Tracks signal outcomes, simulated paper trades, broad market data, ML filtering, manual feedback, and adaptive scoring notes. |
| Safety-first design | The bot only analyzes and notifies. It cannot place trades or use Binance trading endpoints. |

## Safety First

CryptoRadar does not trade.

It does not:

- Place buy or sell orders
- Cancel orders
- Withdraw or transfer funds
- Use futures, margin, leverage, or auto-invest
- Require Binance trading API permission
- Connect to Binance trading endpoints

Signals are analysis only. They are not guaranteed profit. You always decide manually.

## How It Works

```mermaid
flowchart LR
    A["Binance Spot public data"] --> B["Symbol discovery and market scanner"]
    B --> C["Technical indicators"]
    C --> D["Signal scoring"]
    D --> E["Local AI analysis"]
    E --> F["Telegram push alert"]
    D --> G["SQLite signal history"]
    G --> H["Paper trade tracking"]
    H --> I["Adaptive scoring report"]
```

CryptoRadar watches public Binance Spot market data, calculates indicators, creates signal scores, asks local AI for extra analysis when configured, and then sends only the signals that pass your notification rules.

## What CryptoRadar Can Analyze

- Active Binance Spot pairs
- USDT pairs by default
- High-volume symbols
- Low-volume/minor symbols for ML data collection
- Watchlist symbols
- Top movers
- New listings you add to config
- BTC and ETH market conditions
- Breakouts, breakdowns, pumps, dumps, volume spikes, fake breakout risk, and high-risk moves

The default configuration uses volume and symbol limits so the scanner stays practical. You can widen or narrow coverage in `config.yaml`.

## Broad Data Collection For ML

CryptoRadar separates live alert scanning from broad data collection.

| Layer | Purpose |
| --- | --- |
| Live scanner | Keeps Telegram alerts focused on stronger, higher-quality signals |
| Broad collector | Stores data for active Binance Spot symbols, including minor and low-volume coins |
| Data-quality labels | Marks coins as `good`, `thin`, `low_volume`, or `missing_candles` instead of silently dropping them |
| ML dataset | Uses stored signals and outcomes to build local training examples |

This helps the future ML filter learn from more than only the obvious high-volume winners.

Run broad collection manually:

```powershell
python main.py --collect-market-data-now
python main.py --data-coverage-report
```

By default, broad collection stores ticker data quickly and prints progress in PowerShell. If you want slower candle enrichment for each symbol, set `collector.fetch_candles: true` in `config.yaml`.

The normal background service can also run the broad collector on its configured interval.

## Local AI Analysis

CryptoRadar supports local AI through:

- LM Studio at `http://localhost:1234/v1`
- Ollama

The AI is used for analysis only. It can help explain why a signal matters, summarize risk, compare indicator support, and include notes from your local knowledge folder.

Telegram alert wording is still produced by fixed code templates. The LLM does not rewrite prices, scores, signal types, or key levels.

Recommended LM Studio config:

```yaml
ai:
  enabled: true
  provider: "lmstudio"
  base_url: "http://localhost:1234/v1"
  model: "qwen/qwen3.5-9b"
  temperature: 0.2
  max_tokens: 500
  timeout_seconds: 15
  reasoning_effort: "none"
  analysis_reasoning_effort: "none"
  analysis_max_tokens: 300
  analysis_timeout_seconds: 3
```

`reasoning_effort` and `analysis_reasoning_effort` stay at `none` by default so live scans do not wait on long model thinking. The analysis timeout is intentionally short; if Qwen does not answer quickly, CryptoRadar keeps the scan moving with fallback analysis. If you want deeper AI commentary later, set `analysis_reasoning_effort` to `low` or `medium` and raise `analysis_timeout_seconds`.

If LM Studio is offline, slow, or returns no visible final answer, CryptoRadar logs the issue and continues with normal scoring and fallback analysis.

Test local AI:

```bash
python main.py --test-ai
```

## Telegram Push Notifications

Telegram is the main alert channel. Alerts are short, structured, and designed for phone screens.

Example alert shape:

```text
BUY SIGNAL - SOLUSDT

Score: 75/100
Confidence: Medium
Risk: Medium
Trend: uptrend

Why this matters:
Breakout with strong relative volume while BTC trend is supportive.

Key levels:
Entry: 140.50-142.50
Invalidation: 137.8
Take-profit: 146, 150

Final:
This is an analysis-based signal, not guaranteed profit. Decide manually.
```

Default notification rules:

| Signal | Default Rule |
| --- | --- |
| BUY | Send when score is 70 or higher |
| SELL | Send when score is 70 or higher |
| HIGH_RISK | Send when score is 65 or higher |
| HOLD, WAIT, AVOID | Do not send by default |

The bot also uses cooldowns and hourly alert limits to reduce spam.

## Quick Start

1. Clone the project.

```bash
git clone https://github.com/Gxmi2006/CryptoRadar.git
cd CryptoRadar
```

2. Create and activate a virtual environment.

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

macOS or Linux:

```bash
python -m venv .venv
source .venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Create your local environment file.

Windows:

```bash
copy .env.example .env
```

macOS or Linux:

```bash
cp .env.example .env
```

5. Run a safe mock scan.

```bash
python main.py --mock --scan-now
```

Mock mode uses fake market data, so it is the safest first test.

## Telegram Setup

1. Open Telegram.
2. Create a bot with BotFather.
3. Put your bot token and chat ID in `.env`.

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

4. Send a test alert.

```bash
python main.py --test-telegram
```

Do not commit `.env`. It is ignored by Git.

## LM Studio Setup

1. Open LM Studio.
2. Load your Qwen chat or instruct model.
3. Start the local server.
4. Confirm the server URL is `http://localhost:1234/v1`.
5. Set the exact model name in `config.yaml`.

Useful tests:

```bash
python main.py --test-ai
python main.py --test-telegram-format
python main.py --test-live-notification
```

## Knowledge Sources

Add your local research files to the `knowledge/` folder.

Supported files:

| Type | Supported |
| --- | --- |
| PDF | Yes |
| TXT | Yes |
| MD | Yes |
| CSV | Yes |
| JSON | Yes |
| DOCX | Yes |

Rebuild the local knowledge index:

```bash
python main.py --rebuild-knowledge
```

Knowledge sources stay local by default. CryptoRadar stores source quality notes and can reduce trust in sources that repeatedly support weak signals.

## Local ML Filter

CryptoRadar can train a small local ML model from saved signal history. This is not LLM fine-tuning.

The ML model learns from rows like:

- signal type
- score details
- RSI, MACD, relative volume, ATR, and price changes
- BTC and ETH trend context
- data-quality label
- final result: win or loss

The model outputs:

- success probability
- risk score
- confidence score
- data-quality warning
- model version

ML is an extra filter only. It does not replace the scoring engine and it never trades.

Train and inspect the local model:

```powershell
python main.py --train-ml-model
python main.py --ml-report
```

If not enough labeled examples exist, training will stop safely and explain what is missing.

## Common Commands

| Command | Purpose |
| --- | --- |
| `python main.py` | Run the live background scanner |
| `python main.py --mock` | Run with simulated market data |
| `python main.py --scan-now` | Run one scan and exit |
| `python main.py --test-telegram` | Send a Telegram test message |
| `python main.py --test-ai` | Test LM Studio local AI |
| `python main.py --test-telegram-format` | Preview the fixed alert template |
| `python main.py --test-live-notification` | Send a fake BUY signal through the real notification path |
| `python main.py --show-config` | Print sanitized config |
| `python main.py --rebuild-knowledge` | Rebuild the local knowledge index |
| `python main.py --collect-market-data-now` | Collect broad Binance Spot data for ML |
| `python main.py --data-coverage-report` | Show data coverage and weak-data symbols |
| `python main.py --train-ml-model` | Train the local ML filter from labeled signal history |
| `python main.py --ml-report` | Show ML training and prediction status |
| `python main.py --daily-summary` | Send a daily summary now |
| `python main.py --top-signals` | Show top stored signals |
| `python main.py --learning-report` | Show learning performance |

Manual feedback:

```bash
python main.py --mark-signal SIGNAL_ID win
python main.py --mark-signal SIGNAL_ID loss
python main.py --mark-signal SIGNAL_ID neutral
```

## Configuration Highlights

Edit `config.yaml` to control:

| Area | Important Settings |
| --- | --- |
| Market coverage | `quote_assets`, `min_24h_volume_usdt`, `max_symbols_to_analyze`, `watchlist_symbols` |
| Broad collector | `collector.max_symbols_per_cycle`, `collector.min_24h_volume_usdt`, `collector.interval_minutes` |
| Scanner speed | `scan_interval_seconds`, timeframe list |
| Signal thresholds | `buy_score_threshold`, `sell_score_threshold`, `high_risk_threshold` |
| AI | `provider`, `base_url`, `model`, `analysis_reasoning_effort` |
| ML | `ml.min_training_samples`, `ml.random_forest_min_samples`, `ml.model_path` |
| Telegram | token env name, chat ID env name, cooldowns, alert limits |
| Learning | paper-trade tracking, manual feedback, adaptive scoring |

No Binance API key is required for public market monitoring.

## Signal Scores

| Score | Label |
| --- | --- |
| 0-30 | Avoid |
| 31-50 | Weak |
| 51-65 | Watchlist |
| 66-80 | Good signal |
| 81-100 | Strong signal |

BUY scoring considers trend, volume, breakouts, RSI, MACD, EMA alignment, BTC and ETH direction, liquidity, volatility, support and resistance, knowledge-source support, and historical performance.

SELL scoring considers weakening momentum, failed breakouts, support breakdowns, bearish MACD, overbought RSI, sell volume, BTC and ETH weakness, resistance rejection, and previous sell-warning accuracy.

## Learning System

CryptoRadar does not fine-tune the AI model in version 1.

Instead, it learns carefully from:

- Signal history
- Paper-trade tracking
- Manual feedback
- Adaptive scoring weights
- Learning reports

The bot waits for enough completed signals before suggesting scoring changes. This helps avoid overfitting to a few lucky or unlucky trades.

## Paper Trades

Every signal is saved as a simulated paper trade.

| Signal Type | What Gets Tracked |
| --- | --- |
| BUY | Entry zone, take-profit, stop-loss, invalidation, favorable move, drawdown |
| SELL | Whether the warning helped avoid downside |
| HIGH_RISK | Whether the risk warning was useful |
| HOLD | Whether staying neutral was reasonable |

## Requirements

- Python 3.11 or newer
- Internet access for Binance public market data
- Telegram bot token and chat ID for Telegram alerts
- Optional: LM Studio or Ollama for local AI analysis

## Tests

Run tests with:

```bash
pytest
```

The tests cover indicators, scoring, Binance public-data parsing, notification cooldowns, RAG retrieval, prompt safety, paper trades, adaptive scoring, manual feedback, and the rule that no trading execution endpoints exist.

## Runtime Files

CryptoRadar writes runtime data locally:

| File or Folder | Purpose |
| --- | --- |
| `data/cryptoradar.sqlite3` | SQLite database |
| `logs/app.log` | Main app log |
| `logs/signals.log` | Signal log |
| `logs/errors.log` | Error log |
| `logs/learning.log` | Learning log |
| `data/vector_db/` | Local knowledge index |

These runtime files are ignored by Git.

## Private Data

Do not commit:

- `.env`
- API tokens
- Telegram chat IDs
- Email passwords
- Personal notes you do not want public
- Runtime database files
- Log files

The included `.gitignore` is set up to keep common secrets and generated files out of GitHub.
