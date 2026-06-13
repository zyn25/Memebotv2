"""
Bot Configuration (OPTIMIZED)
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
    stop_loss_percent: float = float(os.getenv("STOP_LOSS_PERCENT", "20"))
    take_profit_percent: float = float(os.getenv("TAKE_PROFIT_PERCENT", "200"))
    max_concurrent: int = int(os.getenv("MAX_CONCURRENT_TRADES", "3"))
    slippage_bps: int = int(os.getenv("SLIPPAGE_BPS", "800"))
    min_liquidity_sol: float = 3.0
    max_buy_tax: float = 5.0
    max_sell_tax: float = 5.0
    min_holder_count: int = 15
    max_top_holder_percent: float = 35.0
    min_token_age_seconds: int = 10
    max_token_age_seconds: int = 7200
    min_volume_5m: float = 0.5


@dataclass
class ScreeningConfig:
    min_initial_liquidity: float = 3.0
    max_initial_liquidity: float = 50000.0
    liquidity_lock_required: bool = False
    min_lock_duration_days: int = 0
    ownership_renounced_required: bool = False
    max_mint_authority_risk: int = 0
    max_freeze_authority_risk: int = 0
    honeypot_check_required: bool = True
    min_unique_holders: int = 20
    max_top10_holder_percent: float = 45.0
    dev_wallet_max_percent: float = 10.0
    require_telegram: bool = False
    require_website: bool = False
    require_twitter: bool = False
    max_rugpull_score: int = 35
    min_5m_volume_sol: float = 0.5
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