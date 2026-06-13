"""
Rich logger
"""
import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.theme import Theme

custom_theme = Theme({
    "info": "cyan", "warning": "yellow", "error": "bold red",
    "success": "bold green", "buy": "bold green", "sell": "bold red",
    "scan": "bold blue", "rug": "bold red", "safe": "bold green",
})

console = Console(theme=custom_theme)

logging.basicConfig(
    level=logging.INFO, format="%(message)s", datefmt="[%X]",
    handlers=[RichHandler(console=console, rich_tracebacks=True)],
)

logger = logging.getLogger("SniperBot")


def log_scan(addr, msg=""):
    console.print(f"[scan]SCAN[/] [{addr[:12]}...] {msg}")


def log_buy(addr, amt, price):
    console.print(f"[buy]BUY[/] [{addr[:8]}...] {amt:.4f} SOL @ ${price:.10f}")


def log_sell(addr, amt, pnl):
    c = "success" if pnl >= 0 else "error"
    e = "W" if pnl >= 0 else "L"
    console.print(f"[{c}]SELL[/] [{addr[:8]}...] {amt:.4f} SOL | PnL: {e} {pnl:+.2f}%")


def log_rug(addr, score, reasons):
    console.print(f"[rug]RUG[/] [{addr[:8]}...] Score: {score}/100 | {', '.join(reasons)}")


def log_safe(addr, score):
    console.print(f"[safe]SAFE[/] [{addr[:8]}...] Score: {score}/100")
