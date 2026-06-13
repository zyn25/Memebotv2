"""
Helper functions
"""
import time
import base58

def short_address(a, c=6):
    return f"{a[:c]}...{a[-c:]}"

def lamports_to_sol(lp):
    return lp / 1e9

def sol_to_lamports(sol):
    return int(sol * 1e9)

def current_timestamp():
    return int(time.time())

def calculate_pnl(entry, current):
    if entry == 0: return 0.0
    return ((current - entry) / entry) * 100

def calculate_price_impact(amt_in, res_in, res_out):
    amt_out = (res_out * amt_in) / (res_in + amt_in)
    spot = res_out / res_in
    exec_p = amt_out / amt_in
    return ((spot - exec_p) / spot) * 100

def is_valid_solana_address(addr):
    try:
        d = base58.b58decode(addr)
        return len(d) == 32
    except:
        return False

def time_ago(ts):
    diff = current_timestamp() - ts
    if diff < 60: return f"{diff}s"
    if diff < 3600: return f"{diff//60}m"
    if diff < 86400: return f"{diff//3600}h"
    return f"{diff//86400}d"

def risk_level(score):
    if score <= 20: return "LOW"
    if score <= 40: return "MEDIUM"
    if score <= 60: return "HIGH"
    return "CRITICAL"