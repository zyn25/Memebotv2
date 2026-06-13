# 🎯 Meme Coin Sniper Bot

Solana meme coin sniper bot with 12-layer rugpull detection, real-time scanning, and auto trading via Jupiter aggregator.

## Features

- 🔍 Multi-source token scanning (Raydium WS, Birdeye, Jupiter)
- 🛡️ 12-layer rugpull detection
- 📊 Smart position management (TP/SL/Trailing Stop)
- 💰 Risk management (position sizing, daily limits)
- 📡 Real-time web dashboard
- 📱 Telegram notifications
- 🔄 Circuit breaker (auto-pause on errors)
- 💾 State persistence (survives restarts)

## Architecture


## Quick Start

1. Clone repo
2. Copy `.env.example` to `.env`
3. Fill in your API keys
4. Run `python main.py`

## Environment Variables

| Variable | Description |
|----------|-------------|
| PRIVATE_KEY | Solana wallet private key (base58) |
| WALLET_ADDRESS | Solana wallet address |
| HELIUS_API_KEY | API key from helius.dev |
| BIRDEYE_API_KEY | API key from birdeye.so |
| TELEGRAM_BOT_TOKEN | Telegram bot token from @BotFather |
| TELEGRAM_CHAT_ID | Your Telegram chat ID |
| MAX_SOL_PER_TRADE | Max SOL per trade |
| STOP_LOSS_PERCENT | Stop loss percentage |
| TAKE_PROFIT_PERCENT | Take profit percentage |
| DRY_RUN | true = no real trades, false = live |

## API Keys

- **Helius**: https://helius.dev (Free: 100K req/day)
- **Birdeye**: https://birdeye.so (Free: 100 req/min)
- **Telegram**: @BotFather on Telegram

## Deploy to Railway

1. Connect GitHub repo
2. Set environment variables
3. Deploy

## Disclaimer

⚠️ This bot is for educational purposes only. Meme coin trading is extremely risky. You can lose all your funds. Use at your own risk. Never invest more than you can afford to lose.

## License

MIT