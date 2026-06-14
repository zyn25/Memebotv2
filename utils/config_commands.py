"""
utils/config_commands.py
Additional Telegram config commands - v1.0
==========================================
5 command baru: setconcurrent, setslippage, setmaxrug, setminliq, setminholders
"""
from aiogram.filters import Command
from aiogram.types import Message
from config import config


def register_config_commands(router, auth_func, settings_kb_func):
    r = router

    @r.message(Command("setconcurrent"))
    async def h_setconcurrent(msg: Message):
        if not auth_func(msg): return
        parts = msg.text.split()
        if len(parts) < 2:
            await msg.answer("Usage: /setconcurrent 3")
            return
        try:
            config.trading.max_concurrent = int(parts[1])
            await msg.answer("Concurrent: " + parts[1], reply_markup=settings_kb_func())
        except ValueError:
            await msg.answer("Invalid")

    @r.message(Command("setslippage"))
    async def h_setslippage(msg: Message):
        if not auth_func(msg): return
        parts = msg.text.split()
        if len(parts) < 2:
            await msg.answer("Usage: /setslippage 1000")
            return
        try:
            config.trading.slippage_bps = int(parts[1])
            await msg.answer("Slippage: " + parts[1] + " bps", reply_markup=settings_kb_func())
        except ValueError:
            await msg.answer("Invalid")

    @r.message(Command("setmaxrug"))
    async def h_setmaxrug(msg: Message):
        if not auth_func(msg): return
        parts = msg.text.split()
        if len(parts) < 2:
            await msg.answer("Usage: /setmaxrug 45")
            return
        try:
            config.screening.max_rugpull_score = int(parts[1])
            await msg.answer("Max Rug: " + parts[1] + "/100")
        except ValueError:
            await msg.answer("Invalid")

    @r.message(Command("setminliq"))
    async def h_setminliq(msg: Message):
        if not auth_func(msg): return
        parts = msg.text.split()
        if len(parts) < 2:
            await msg.answer("Usage: /setminliq 2.0")
            return
        try:
            config.trading.min_liquidity_sol = float(parts[1])
            config.screening.min_initial_liquidity = float(parts[1])
            await msg.answer("Min Liq: " + parts[1] + " SOL")
        except ValueError:
            await msg.answer("Invalid")

    @r.message(Command("setminholders"))
    async def h_setminholders(msg: Message):
        if not auth_func(msg): return
        parts = msg.text.split()
        if len(parts) < 2:
            await msg.answer("Usage: /setminholders 12")
            return
        try:
            config.screening.min_unique_holders = int(parts[1])
            config.trading.min_holder_count = int(parts[1])
            await msg.answer("Min Holders: " + parts[1])
        except ValueError:
            await msg.answer("Invalid")
