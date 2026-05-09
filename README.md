# CryptoRadar

CryptoRadar is a terminal-based crypto market signal bot. It watches Binance Spot public market data, analyzes technical conditions, reads your local crypto notes, sends alerts, and tracks how past signals performed.

CryptoRadar has no website, no dashboard, and no graphical interface. It runs from the command line or as a background service.

## Important Safety Note

CryptoRadar does not trade. It does not place orders, cancel orders, withdraw funds, transfer funds, use futures, use margin, use leverage, or need Binance trading permissions.

Signals are analysis only. They are not guaranteed profit. You always decide manually.

## What CryptoRadar Can Do

- Monitor Binance Spot markets using public market data.
- Track USDT pairs by default.
- Calculate indicators such as RSI, MACD, EMA, SMA, Bollinger Bands, ATR, volume, support, resistance, and market structure.
- Detect pumps, dumps, breakouts, failed breakouts, volume spikes, high-risk moves, and weak setups.
- Create BUY, SELL, HOLD, WAIT, AVOID, and HIGH_RISK signals.
- Send Telegram alerts.
- Optionally send desktop, email, or Discord alerts.
- Read local knowledge files from the `knowledge/` folder.
- Use local LM Studio or Ollama AI when available.
- Save signals and simulated paper trades in SQLite.
- Track wins, losses, neutral results, and manual feedback.
- Generate learning reports so scoring can improve slowly over time.

## Quick Start

1. Clone or download the project.

```bash
git clone https://github.com/Gxmi2006/CryptoRadar.git
cd CryptoRadar
```

2. Create a Python virtual environment.

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

4. Copy the example environment file.

```bash
copy .env.example .env
```

On macOS or Linux:

```bash
cp .env.example .env
```

5. Run a safe mock scan.

```bash
python main.py --mock --scan-now
```

Mock mode uses fake market data, so it is the easiest way to confirm everything works.

## Telegram Alerts

Telegram is the main alert channel.

1. Open Telegram and create a bot with BotFather.
2. Copy the bot token into `.env`.
3. Put your Telegram chat ID into `.env`.

```bash
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

4. Send a test message.

```bash
python main.py --test-telegram
```

Do not commit your `.env` file. It is ignored by Git.

## LM Studio Setup

CryptoRadar can use LM Studio for local AI signal analysis. Telegram alert wording is still produced by fixed code templates, not by the AI model.

1. Open LM Studio.
2. Load a Qwen chat or instruct model.
3. Start the local server.
4. Confirm the server URL is `http://localhost:1234/v1`.

In `config.yaml`, use:

```yaml
ai:
  enabled: true
  provider: "lmstudio"
  base_url: "http://localhost:1234/v1"
  model: "qwen/qwen3.5-9b"
  reasoning_effort: "none"
```

Use the exact model name shown by LM Studio if yours is different.

Test LM Studio:

```bash
python main.py --test-ai
```

Test the fixed Telegram template:

```bash
python main.py --test-telegram-format
```

Send a fake BUY signal through the real notification path:

```bash
python main.py --test-live-notification
```

If LM Studio is offline or the model fails, CryptoRadar logs the issue and continues with normal scoring and template alerts.

## Ollama Setup

CryptoRadar can use local AI through Ollama. This is optional.

Install Ollama, then run:

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
```

If Ollama is not running, CryptoRadar still works with normal scoring and a safe fallback analysis.

## Add Knowledge Sources

Put your local research files inside the `knowledge/` folder.

Supported files:

- PDF
- TXT
- MD
- CSV
- JSON
- DOCX

Rebuild the local knowledge index:

```bash
python main.py --rebuild-knowledge
```

CryptoRadar stores source file names, categories, trust levels, notes, warnings, and performance scores. It warns when a source looks risky, outdated, too short, or missing risk-management language.

## Common Commands

Run normally:

```bash
python main.py
```

Run with fake market data:

```bash
python main.py --mock
```

Run one scan and exit:

```bash
python main.py --scan-now
```

Show current settings:

```bash
python main.py --show-config
```

Test local AI:

```bash
python main.py --test-ai
```

Test the fixed Telegram template:

```bash
python main.py --test-telegram-format
```

Test the live notification path with a fake BUY signal:

```bash
python main.py --test-live-notification
```

Show top stored signals:

```bash
python main.py --top-signals
```

Send a daily summary now:

```bash
python main.py --daily-summary
```

Show the learning report:

```bash
python main.py --learning-report
```

Mark a signal manually:

```bash
python main.py --mark-signal SIGNAL_ID win
python main.py --mark-signal SIGNAL_ID loss
python main.py --mark-signal SIGNAL_ID neutral
```

## Configuration

Edit `config.yaml` to change:

- Quote assets such as `USDT`, `FDUSD`, `BTC`, or `ETH`.
- Minimum 24h volume.
- Maximum symbols to analyze.
- Scan interval.
- Signal thresholds.
- Telegram and notification behavior.
- LM Studio or Ollama model names.
- Knowledge folder location.
- Learning settings.

No Binance API key is required.

## Signal Scores

CryptoRadar scores signals from 0 to 100.

- 0-30: Avoid
- 31-50: Weak
- 51-65: Watchlist
- 66-80: Good signal
- 81-100: Strong signal

BUY scoring looks at trend, volume, breakouts, RSI, MACD, EMA alignment, BTC and ETH direction, liquidity, volatility, support/resistance, knowledge-source support, and historical performance.

SELL scoring looks at weakening momentum, failed breakouts, support breakdowns, bearish MACD, overbought RSI, sell volume, BTC and ETH weakness, resistance rejection, and previous sell-warning accuracy.

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

BUY signals track possible entry, take-profit, stop-loss, invalidation, maximum profit, drawdown, and final result.

SELL and HIGH_RISK signals track whether the warning helped avoid downside.

HOLD signals track whether staying neutral was reasonable.

## Notifications

Default alert rules:

- BUY alerts need score 70 or higher.
- SELL alerts need score 70 or higher.
- HIGH_RISK alerts need score 65 or higher.
- HOLD, WAIT, and AVOID are not sent by default.
- Alerts use cooldowns and hourly limits to reduce spam.

Every alert reminds you that the signal is not guaranteed profit and that you must decide manually.

## Tests

Run tests with:

```bash
pytest
```

The tests cover indicators, scoring, Binance public-data parsing, notification cooldowns, RAG retrieval, prompt safety, paper trades, adaptive scoring, manual feedback, and the rule that no trading execution endpoints exist.

## Files Created While Running

CryptoRadar writes runtime data locally:

- SQLite database: `data/cryptoradar.sqlite3`
- App logs: `logs/app.log`
- Signal logs: `logs/signals.log`
- Error logs: `logs/errors.log`
- Learning logs: `logs/learning.log`
- Local vector index: `data/vector_db/`

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
