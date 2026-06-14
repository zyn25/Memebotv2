"""
Bot Configuration (OPTIMIZED v2.0 - LENIENT MODE)
==================================================
Perubahan dari v1.0:
  - min_liquidity_sol     : 3.0 → 2.0   (lebih longgar)
  - min_holder_count      : 15 → 12     (lebih longgar)
  - max_top_holder_percent: 35 → 40     (lebih longgar)
  - min_volume_5m         : 0.5 → 0.3   (lebih longgar)
  - slippage_bps          : 800 → 1000  (lebih tinggi, swap lebih sering berhasil)
  - min_initial_liquidity : 3.0 → 2.0   (lebih longgar)
  - min_unique_holders    : 20 → 12     (lebih longgar)
  - max_top10_holder_pct  : 45 → 50     (lebih longgar)
  - max_rugpull_score     : 35 → 45     (lebih longgar)
  - min_5m_volume_sol     : 0.5 → 0.3   (lebih longgar)
  - dev_wallet_max_percent: 10 → 25     (pump.fun bonding curve normal)
  - max_buy_tax           : 5 → 8       (lebih longgar)
  - max_sell_tax          : 5 → 8       (lebih longgar)
"""
import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()


@dataclass
class WalletConfig:
    private_key: str = os.getenv("PRIVATE_KEY", "")
    address: str = os.getenv("WALLET_ADDRESS", "")


@dataclass
class RPCConfig:
    solana_rpc: str = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    solana_ws: str = os.getenv("SOLANA_WS_URL", "wss://api.mainnet-beta.solana.com")
    helius_key: str = os.getenv("HELIUS_API_KEY", "")
    birdeye_key: str = os.getenv("BIRDEYE_API_KEY", "")


@dataclass
class TradingConfig:
    max_sol_per_trade: float = float(os.getenv("MAX_SOL_PER_TRADE", "0.02"))
    stop_loss_percent: float = float(os.getenv("STOP_LOSS_PERCENT", "25"))
    take_profit_percent: float = float(os.getenv("TAKE_PROFIT_PERCENT", "150"))
    max_concurrent: int = int(os.getenv("MAX_CONCURRENT_TRADES", "2"))
    slippage_bps: int = int(os.getenv("SLIPPAGE_BPS", "1000"))
    min_liquidity_sol: float = 2.0
    max_buy_tax: float = 8.0
    max_sell_tax: float = 8.0
    min_holder_count: int = 12
    max_top_holder_percent: float = 40.0
    min_token_age_seconds: int = 10
    max_token_age_seconds: int = 7200
    min_volume_5m: float = 0.3


@dataclass
class ScreeningConfig:
    min_initial_liquidity: float = 2.0
    max_initial_liquidity: float = 50000.0
    liquidity_lock_required: bool = False
    min_lock_duration_days: int = 0
    ownership_renounced_required: bool = False
    max_mint_authority_risk: int = 0
    max_freeze_authority_risk: int = 0
    honeypot_check_required: bool = True
    min_unique_holders: int = 12
    max_top10_holder_percent: float = 50.0
    dev_wallet_max_percent: float = 25.0
    require_telegram: bool = False
    require_website: bool = False
    require_twitter: bool = False
    max_rugpull_score: int = 45
    min_5m_volume_sol: float = 0.3
    min_buy_sell_ratio: float = 1.0


@dataclass
class NotificationConfig:
    telegram_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    notify_on_scan: bool = True
    notify_on_buy: bool = True
    notify_on_sell: bool = True


@dataclass
class BotConfig:
    wallet: WalletConfig = field(default_factory=WalletConfig)
    rpc: RPCConfig = field(default_factory=RPCConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    screening: ScreeningConfig = field(default_factory=ScreeningConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    dry_run: bool = os.getenv("DRY_RUN", "true").lower() == "true"


config = BotConfig()
