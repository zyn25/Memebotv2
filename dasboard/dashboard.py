"""
Full Production Dashboard
"""
import os
import time
import threading
from flask import Flask, render_template_string, jsonify
from flask_socketio import SocketIO
from core.risk_manager import RiskManager
from utils.helpers import current_timestamp

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meme Sniper Bot</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Inter:wght@400;600&display=swap" rel="stylesheet">
<link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.0/css/all.min.css" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/socket.io/4.7.4/socket.io.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
:root{--bg0:#0a0a0f;--bg1:#12121a;--bg2:#1a1a2e;--bg3:#1e1e35;--bg4:#0f0f1a;--bdr:#2a2a3e;--t1:#e8e8f0;--t2:#8888aa;--t3:#555577;--g:#00ff88;--gg:rgba(0,255,136,.15);--r:#ff4466;--rg:rgba(255,68,102,.15);--y:#ffaa00;--yg:rgba(255,170,0,.15);--b:#4488ff;--bg:rgba(68,136,255,.15);--p:#aa44ff;--pg:rgba(170,68,255,.15);--c:#00ddff;--cg:rgba(0,221,255,.15)}
body{background:var(--bg0);color:var(--t1);font-family:'Inter',sans-serif;min-height:100vh}
.mono{font-family:'JetBrains Mono',monospace}
::-webkit-scrollbar{width:6px}::-webkit-scrollbar-track{background:var(--bg0)}::-webkit-scrollbar-thumb{background:var(--bdr);border-radius:3px}
.hdr{background:linear-gradient(180deg,var(--bg1),var(--bg0));border-bottom:1px solid var(--bdr);padding:14px 20px;position:sticky;top:0;z-index:100}
.hdr-in{max-width:1600px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.logo{display:flex;align-items:center;gap:10px}.logo-t{font-weight:700;font-size:16px;background:linear-gradient(135deg,var(--g),var(--c));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.hdr-r{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.sb{display:flex;align-items:center;gap:6px;padding:5px 12px;border-radius:16px;font-size:11px;font-weight:600}
.sb-dry{background:var(--yg);border:1px solid var(--y);color:var(--y)}
.sb-live{background:var(--gg);border:1px solid var(--g);color:var(--g)}
.sd{width:7px;height:7px;border-radius:50%;animation:p 2s infinite}
@keyframes p{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.5;transform:scale(.8)}}
.cb{display:none;padding:5px 12px;border-radius:16px;font-size:11px;font-weight:600;background:var(--rg);border:1px solid var(--r);color:var(--r);animation:p 1s infinite}.cb.on{display:flex;align-items:center;gap:4px}
.nt{max-width:1600px;margin:0 auto;padding:10px 20px 0;display:flex;gap:4px;overflow-x:auto}
.tb{padding:8px 16px;border-radius:8px 8px 0 0;background:0;border:none;color:var(--t2);font-size:12px;font-weight:500;cursor:pointer;transition:.3s;white-space:nowrap;display:flex;align-items:center;gap:6px}
.tb:hover{background:var(--bg2);color:var(--t1)}.tb.on{background:var(--bg2);color:var(--g);border-bottom:2px solid var(--g)}
.tb .bc{background:var(--g);color:var(--bg0);padding:1px 6px;border-radius:8px;font-size:9px;font-weight:700}
.mc{max-width:1600px;margin:0 auto;padding:0 20px 20px}
.tc{display:none;animation:fi .3s}.tc.on{display:block}
@keyframes fi{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:translateY(0)}}
.g{display:grid;gap:14px}.g4{grid-template-columns:repeat(4,1fr)}.g3{grid-template-columns:repeat(3,1fr)}.g2{grid-template-columns:repeat(2,1fr)}.g21{grid-template-columns:2fr 1fr}
@media(max-width:1200px){.g4{grid-template-columns:repeat(2,1fr)}.g3{grid-template-columns:repeat(2,1fr)}.g21{grid-template-columns:1fr}}
@media(max-width:768px){.g4,.g3,.g2{grid-template-columns:1fr}}
.cd{background:var(--bg2);border:1px solid var(--bdr);border-radius:12px;padding:18px;transition:.3s}.cd:hover{border-color:#333;box-shadow:0 2px 12px rgba(0,0,0,.3)}
.ch{display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;padding-bottom:10px;border-bottom:1px solid var(--bdr)}
.ct{font-size:13px;font-weight:600;display:flex;align-items:center;gap:6px}.ct i{color:var(--g);font-size:14px}
.sc{background:var(--bg2);border:1px solid var(--bdr);border-radius:12px;padding:18px;transition:.3s;position:relative;overflow:hidden}
.sc::before{content:'';position:absolute;top:0;left:0;right:0;height:3px;border-radius:12px 12px 0 0}
.sc.gn::before{background:var(--g)}.sc.rd::before{background:var(--r)}.sc.yw::before{background:var(--y)}.sc.bl::before{background:var(--b)}.sc.pr::before{background:var(--p)}.sc.cy::before{background:var(--c)}
.sc:hover{transform:translateY(-2px);box-shadow:0 4px 20px rgba(0,0,0,.4)}
.si{width:36px;height:36px;border-radius:8px;display:flex;align-items:center;justify-content:center;font-size:16px;margin-bottom:10px}
.sc.gn .si{background:var(--gg);color:var(--g)}.sc.rd .si{background:var(--rg);color:var(--r)}.sc.yw .si{background:var(--yg);color:var(--y)}.sc.bl .si{background:var(--bg);color:var(--b)}.sc.pr .si{background:var(--pg);color:var(--p)}.sc.cy .si{background:var(--cg);color:var(--c)}
.sl{font-size:11px;color:var(--t2);margin-bottom:3px;font-weight:500}
.sv{font-size:22px;font-weight:700;font-family:'JetBrains Mono',monospace;line-height:1.2}
.p{color:var(--g)}.n{color:var(--r)}.w{color:var(--y)}.i{color:var(--b)}
.tc-wrap{overflow-x:auto;border-radius:8px}table{width:100%;border-collapse:collapse;font-size:12px}
th{padding:10px 14px;text-align:left;font-weight:600;color:var(--t2);font-size:10px;text-transform:uppercase;letter-spacing:.5px;background:var(--bg4);border-bottom:1px solid var(--bdr);white-space:nowrap}
td{padding:10px 14px;border-bottom:1px solid var(--bdr);white-space:nowrap;transition:.3s}tr:hover td{background:var(--bg3)}tr:last-child td{border-bottom:none}
.bg{display:inline-flex;align-items:center;gap:3px;padding:2px 8px;border-radius:5px;font-size:10px;font-weight:600}
.bg-g{background:var(--gg);color:var(--g)}.bg-r{background:var(--rg);color:var(--r)}.bg-y{background:var(--yg);color:var(--y)}.bg-b{background:var(--bg);color:var(--b)}.bg-p{background:var(--pg);color:var(--p)}
.pb{height:5px;border-radius:3px;background:var(--bg4);overflow:hidden;margin-top:3px}.pf{height:100%;border-radius:3px;transition:width .5s}.pf.p{background:linear-gradient(90deg,var(--g),var(--c))}.pf.n{background:linear-gradient(90deg,#cc3355,var(--r))}
.fd{max-height:380px;overflow-y:auto;display:flex;flex-direction:column;gap:6px}
.fi{display:flex;gap:10px;padding:10px;background:var(--bg4);border-radius:8px;border-left:3px solid var(--bdr);transition:.3s;animation:si2 .3s}
@keyframes si2{from{opacity:0;transform:translateX(-15px)}to{opacity:1;transform:translateX(0)}}
.fi.buy{border-left-color:var(--g)}.fi.sell{border-left-color:var(--r)}.fi.alert{border-left-color:var(--y)}.fi.rug{border-left-color:var(--r)}.fi.scan{border-left-color:var(--b)}.fi.info{border-left-color:var(--c)}
.fic{width:28px;height:28px;border-radius:6px;display:flex;align-items:center;justify-content:center;font-size:12px;flex-shrink:0}
.fi.buy .fic{background:var(--gg);color:var(--g)}.fi.sell .fic{background:var(--rg);color:var(--r)}.fi.alert .fic{background:var(--yg);color:var(--y)}.fi.rug .fic{background:var(--rg);color:var(--r)}.fi.scan .fic{background:var(--bg);color:var(--b)}.fi.info .fic{background:var(--cg);color:var(--c)}
.fit{font-size:12px;font-weight:600;margin-bottom:1px}.fid{font-size:11px;color:var(--t2)}.ft{font-size:10px;color:var(--t3);font-family:'JetBrains Mono',monospace;flex-shrink:0}
.chk{display:flex;flex-direction:column;gap:6px}.ci{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:var(--bg4);border-radius:8px;font-size:12px}
.ci .lb{display:flex;align-items:center;gap:6px;color:var(--t2)}.ci .st{font-weight:600}.ci.ok .st{color:var(--g)}.ci.fail .st{color:var(--r)}
.rm{width:100%;height:20px;background:var(--bg4);border-radius:10px;overflow:hidden;margin:10px 0}.rmf{height:100%;border-radius:10px;transition:width 1s}.rml{position:absolute;right:8px;top:50%;transform:translateY(-50%);font-size:10px;font-weight:700;color:#fff}
.cc{position:relative;height:220px;width:100%}.sr{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--bdr)}.sr:last-child{border-bottom:none}.sl2{font-size:12px;color:var(--t2)}.sv2{font-family:'JetBrains Mono',monospace;font-size:12px;font-weight:600}
.pgb{width:100%;height:6px;background:var(--bg4);border-radius:3px;overflow:hidden}.pgf{height:100%;border-radius:3px;transition:width .5s}
.es{text-align:center;padding:40px 20px;color:var(--t3)}.es i{font-size:40px;margin-bottom:12px;opacity:.3}.es h3{font-size:14px;color:var(--t2);margin-bottom:6px}.es p{font-size:12px}
.ta{font-family:'JetBrains Mono',monospace;font-size:11px;color:var(--t3);cursor:pointer;transition:.3s}.ta:hover{color:var(--g)}
@keyframes fg{0%{color:var(--g);transform:scale(1.1)}100%{transform:scale(1)}}@keyframes fr2{0%{color:var(--r);transform:scale(1.1)}100%{transform:scale(1)}}
.cn.fg{animation:fg .5s}.cn.fr{animation:fr2 .5s}
</style>
</head>
<body>
<header class="hdr"><div class="hdr-in">
<div class="logo"><span style="font-size:24px">🎯</span><div><div class="logo-t">MEME SNIPER BOT</div><div style="font-size:10px;color:var(--t3)">Dashboard v2.0</div></div></div>
<div class="hdr-r">
<div id="cb-badge" class="cb"><i class="fas fa-exclamation-triangle"></i><span>CIRCUIT BREAKER</span></div>
<div id="mode-badge" class="sb sb-dry"><div class="sd"></div><span id="mode-text">DRY RUN</span></div>
<div style="font-size:11px;color:var(--t2);font-family:'JetBrains Mono'"><i class="fas fa-clock"></i> <span id="uptime">0s</span></div>
<div id="ws" class="sb" style="background:var(--gg);border:1px solid var(--g);color:var(--g);font-size:10px"><div class="sd" style="background:var(--g)"></div><span>CONNECTED</span></div>
</div></div></header>

<nav class="nt">
<button class="tb on" onclick="sw('overview')"><i class="fas fa-chart-pie"></i> Overview</button>
<button class="tb" onclick="sw('positions')"><i class="fas fa-layer-group"></i> Positions <span class="bc" id="pc">0</span></button>
<button class="tb" onclick="sw('history')"><i class="fas fa-history"></i> History</button>
<button class="tb" onclick="sw('scanner')"><i class="fas fa-satellite-dish"></i> Scanner</button>
<button class="tb" onclick="sw('rugcheck')"><i class="fas fa-shield-halved"></i> Rug Check</button>
<button class="tb" onclick="sw('alerts')"><i class="fas fa-bell"></i> Alerts <span class="bc" id="ac">0</span></button>
<button class="tb" onclick="sw('settings')"><i class="fas fa-cog"></i> Settings</button>
</nav>

<main class="mc">
<div id="t-overview" class="tc on">
<div class="g g4" style="margin-bottom:14px">
<div class="sc gn"><div class="si"><i class="fas fa-coins"></i></div><div class="sl">Total PnL</div><div class="sv p cn" id="tpnl">0.0000</div><div style="font-size:10px;margin-top:4px;color:var(--t2)">SOL</div></div>
<div class="sc bl"><div class="si"><i class="fas fa-chart-line"></i></div><div class="sl">Win Rate</div><div class="sv i cn" id="wr">0.0%</div><div style="font-size:10px;margin-top:4px" id="wrd"><span class="p">0W</span> / <span class="n">0L</span></div></div>
<div class="sc yw"><div class="si"><i class="fas fa-crosshairs"></i></div><div class="sl">Trades</div><div class="sv cn" id="tt" style="color:var(--y)">0</div><div style="font-size:10px;margin-top:4px;color:var(--b)" id="apc">0 active</div></div>
<div class="sc rd"><div class="si"><i class="fas fa-shield-virus"></i></div><div class="sl">Rugs Blocked</div><div class="sv n cn" id="rb">0</div><div style="font-size:10px;margin-top:4px;color:var(--b)" id="tsc">0 scanned</div></div>
</div>
<div class="g g4" style="margin-bottom:14px">
<div class="sc pr"><div class="si"><i class="fas fa-search"></i></div><div class="sl">Scanned</div><div class="sv cn" id="ts" style="color:var(--p)">0</div></div>
<div class="sc cy"><div class="si"><i class="fas fa-check-circle"></i></div><div class="sl">Passed</div><div class="sv cn" id="tsp" style="color:var(--c)">0</div><div style="font-size:10px;margin-top:4px" id="pr">0% pass</div></div>
<div class="sc gn"><div class="si"><i class="fas fa-trophy"></i></div><div class="sl">Profit Factor</div><div class="sv p cn" id="pf">0.00</div></div>
<div class="sc rd"><div class="si"><i class="fas fa-arrow-down"></i></div><div class="sl">Max DD</div><div class="sv n cn" id="mdd">0.0000</div><div style="font-size:10px;margin-top:4px;color:var(--t2)">SOL</div></div>
</div>
<div class="g g21">
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-chart-area"></i> PnL Chart</div><span class="bg bg-b" id="dpb">Today: 0.00 SOL</span></div><div class="cc"><canvas id="pc2"></canvas></div></div>
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-rss"></i> Activity</div><span class="bg bg-g">LIVE</span></div><div class="fd" id="af"><div class="fi info"><div class="fic"><i class="fas fa-robot"></i></div><div style="flex:1"><div class="fit">Bot Started</div><div class="fid">Waiting for data...</div></div><div class="ft">now</div></div></div></div>
</div>
<div class="cd" style="margin-top:14px"><div class="ch"><div class="ct"><i class="fas fa-exchange-alt"></i> Recent Trades</div></div><div class="tc-wrap"><table><thead><tr><th>Time</th><th>Token</th><th>SOL</th><th>PnL %</th><th>Duration</th><th>Status</th></tr></thead><tbody id="rtb"><tr><td colspan="6"><div class="es"><i class="fas fa-inbox"></i><h3>No trades yet</h3></div></td></tr></tbody></table></div></div>
</div>

<div id="t-positions" class="tc"><div class="cd"><div class="ch"><div class="ct"><i class="fas fa-layer-group"></i> Active Positions</div><span class="bg bg-g" id="pcb">0 open</span></div>
<div class="tc-wrap"><table><thead><tr><th>Token</th><th>Entry</th><th>Current</th><th>SOL</th><th>PnL</th><th>SL</th><th>TP</th><th>Duration</th><th>Health</th></tr></thead>
<tbody id="ptb"><tr><td colspan="9"><div class="es"><i class="fas fa-layer-group"></i><h3>No positions</h3></div></td></tr></tbody></table></div></div></div>

<div id="t-history" class="tc"><div class="cd"><div class="ch"><div class="ct"><i class="fas fa-history"></i> Trade History</div><span class="bg bg-b" id="hc">0 trades</span></div>
<div class="tc-wrap"><table><thead><tr><th>#</th><th>Time</th><th>Token</th><th>Entry</th><th>Exit</th><th>PnL %</th><th>PnL SOL</th><th>Duration</th><th>Result</th></tr></thead>
<tbody id="htb"><tr><td colspan="9"><div class="es"><i class="fas fa-history"></i><h3>No history</h3></div></td></tr></tbody></table></div></div></div>
<div id="t-scanner" class="tc">
<div class="g g3" style="margin-bottom:14px">
<div class="sc bl"><div class="si"><i class="fas fa-satellite-dish"></i></div><div class="sl">Sources</div><div style="margin-top:6px"><div class="ci ok"><span class="lb">Raydium WS</span><span class="st">ACTIVE</span></div><div class="ci ok"><span class="lb">Birdeye</span><span class="st">ACTIVE</span></div><div class="ci ok"><span class="lb">Jupiter</span><span class="st">ACTIVE</span></div></div></div>
<div class="sc pr"><div class="si"><i class="fas fa-filter"></i></div><div class="sl">Funnel</div><div style="margin-top:10px">
<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px"><span>Scanned</span><span id="fs">0</span></div><div class="pgb" style="margin-bottom:8px"><div class="pgf" id="fbs" style="width:100%;background:var(--b)"></div></div>
<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px"><span>Passed</span><span id="fp">0</span></div><div class="pgb" style="margin-bottom:8px"><div class="pgf" id="fbp" style="width:0%;background:var(--c)"></div></div>
<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px"><span>Rug OK</span><span id="fr">0</span></div><div class="pgb" style="margin-bottom:8px"><div class="pgf" id="fbr" style="width:0%;background:var(--g)"></div></div>
<div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:3px"><span>Traded</span><span id="ft">0</span></div><div class="pgb"><div class="pgf" id="fbt" style="width:0%;background:var(--y)"></div></div>
</div></div>
<div class="sc gn"><div class="si"><i class="fas fa-chart-bar"></i></div><div class="sl">Performance</div><div style="margin-top:6px">
<div class="sr"><span class="sl2">Scanned</span><span class="sv2" id="ps2">0</span></div>
<div class="sr"><span class="sl2">Pass Rate</span><span class="sv2 p" id="ppr">0%</span></div>
<div class="sr"><span class="sl2">Rug Block</span><span class="sv2 n" id="prr">0%</span></div>
<div class="sr"><span class="sl2">Trade Rate</span><span class="sv2 i" id="ptr">0%</span></div>
<div class="sr"><span class="sl2">Errors</span><span class="sv2 w" id="pe">0</span></div>
</div></div>
</div>
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-list"></i> Scanned Tokens</div></div>
<div class="tc-wrap"><table><thead><tr><th>Time</th><th>Token</th><th>Source</th><th>Liq</th><th>Holders</th><th>Rug</th><th>Score</th><th>Decision</th></tr></thead>
<tbody id="stb"><tr><td colspan="8"><div class="es"><i class="fas fa-satellite-dish"></i><h3>Waiting...</h3></div></td></tr></tbody></table></div></div></div>

<div id="t-rugcheck" class="tc"><div class="g g2" style="margin-bottom:14px">
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-shield-halved"></i> Rug Detection</div></div>
<div style="margin-bottom:14px"><div style="display:flex;justify-content:space-between;margin-bottom:6px;font-size:12px"><span>Detection</span><span class="mono n" id="rdr">0%</span></div><div class="rm"><div class="rmf" id="rm" style="width:0%;background:linear-gradient(90deg,var(--g),var(--y),var(--r))"><span class="rml" id="rml">0</span></div></div></div>
<div class="chk">
<div class="ci ok"><span class="lb"><i class="fas fa-bug"></i> Honeypot</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-key"></i> Mint Auth</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-lock"></i> Freeze</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-user-shield"></i> Ownership</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-water"></i> Liquidity</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-lock-open"></i> LP Lock</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-users"></i> Holders</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-user-secret"></i> Dev Wallet</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-file-code"></i> Contract</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-globe"></i> Social</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-chart-line"></i> Tx Patterns</span><span class="st">PASS</span></div>
<div class="ci ok"><span class="lb"><i class="fas fa-robot"></i> Bundle</span><span class="st">PASS</span></div>
</div></div>
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-ban"></i> Blocked</div></div>
<div class="fd" id="btf"><div class="es"><i class="fas fa-shield-halved"></i><h3>No rugpulls detected</h3></div></div></div>
</div></div>

<div id="t-alerts" class="tc"><div class="cd"><div class="ch"><div class="ct"><i class="fas fa-bell"></i> Alerts</div><button onclick="clr()" style="background:var(--bg4);border:1px solid var(--bdr);color:var(--t2);padding:5px 10px;border-radius:5px;cursor:pointer;font-size:11px"><i class="fas fa-trash"></i> Clear</button></div>
<div class="fd" id="alr" style="max-height:500px"><div class="fi info"><div class="fic"><i class="fas fa-robot"></i></div><div style="flex:1"><div class="fit">System Ready</div><div class="fid">Dashboard initialized.</div></div><div class="ft">now</div></div></div></div></div>

<div id="t-settings" class="tc"><div class="g g3">
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-sliders-h"></i> Trading</div></div>
<div class="sr"><span class="sl2">Max SOL/Trade</span><span class="sv2" id="sms">0.5</span></div>
<div class="sr"><span class="sl2">Stop Loss</span><span class="sv2 n" id="ssl">30%</span></div>
<div class="sr"><span class="sl2">Take Profit</span><span class="sv2 p" id="stp">200%</span></div>
<div class="sr"><span class="sl2">Concurrent</span><span class="sv2" id="scn">5</span></div>
<div class="sr"><span class="sl2">Slippage</span><span class="sv2" id="ssp">500 bps</span></div></div>
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-filter"></i> Screening</div></div>
<div class="sr"><span class="sl2">Max Rug Score</span><span class="sv2 w" id="smr">35/100</span></div>
<div class="sr"><span class="sl2">Min Liquidity</span><span class="sv2" id="sml">10 SOL</span></div>
<div class="sr"><span class="sl2">Min Holders</span><span class="sv2" id="smh">30</span></div>
<div class="sr"><span class="sl2">Ownership</span><span class="sv2 p">Required</span></div>
<div class="sr"><span class="sl2">Honeypot</span><span class="sv2 p">Required</span></div></div>
<div class="cd"><div class="ch"><div class="ct"><i class="fas fa-server"></i> System</div></div>
<div class="sr"><span class="sl2">Scanner</span><span class="sv2 p">Running</span></div>
<div class="sr"><span class="sl2">Monitor</span><span class="sv2 p">Running</span></div>
<div class="sr"><span class="sl2">Dashboard</span><span class="sv2 p">Running</span></div>
<div class="sr"><span class="sl2">Circuit Breaker</span><span class="sv2 p" id="sck">OK</span></div>
<div class="sr"><span class="sl2">Errors</span><span class="sv2" id="ser">0</span></div></div>
</div></div>

</main>
<script>
const S=io();let pp=0,ac=0,PC=null;
function sw(n){document.querySelectorAll('.tc').forEach(e=>e.classList.remove('on'));document.querySelectorAll('.tb').forEach(e=>e.classList.remove('on'));document.getElementById('t-'+n).classList.add('on');event.currentTarget.classList.add('on');}
function clr(){document.getElementById('alr').innerHTML='';ac=0;document.getElementById('ac').textContent='0';}
function fS(v){return(parseFloat(v)||0).toFixed(4);}
function fP(v){return(parseFloat(v)||0).toFixed(2)+'%';}
function fPr(v){const n=parseFloat(v)||0;if(n<.000001)return'$'+n.toFixed(12);if(n<.01)return'$'+n.toFixed(8);if(n<1)return'$'+n.toFixed(6);return'$'+n.toFixed(4);}
function fT(){return new Date().toLocaleTimeString('en-US',{hour12:false});}
function fl(id,t){const e=document.getElementById(id);if(e){e.classList.add(t==='p'?'fg':'fr');setTimeout(()=>e.classList.remove('fg','fr'),500);}}
function aF(cid,type,t,d){const c=document.getElementById(cid);if(!c)return;const ic={buy:'fa-arrow-up',sell:'fa-arrow-down',alert:'fa-exclamation-triangle',rug:'fa-shield-virus',scan:'fa-search',info:'fa-info-circle'};const e=document.createElement('div');e.className='fi '+type;e.innerHTML='<div class="fic"><i class="fas '+(ic[type]||'fa-circle')+'"></i></div><div style="flex:1"><div class="fit">'+t+'</div><div class="fid">'+d+'</div></div><div class="ft">'+fT()+'</div>';c.insertBefore(e,c.firstChild);while(c.children.length>50)c.removeChild(c.lastChild);}
function iC(){const x=document.getElementById('pc2');if(!x)return;PC=new Chart(x,{type:'line',data:{labels:[],datasets:[{data:[],borderColor:'#00ff88',backgroundColor:'rgba(0,255,136,0.08)',borderWidth:2,fill:true,tension:.4,pointRadius:0}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{display:true,grid:{color:'rgba(255,255,255,0.03)'},ticks:{color:'#555',font:{size:9},maxTicksLimit:8}},y:{display:true,grid:{color:'rgba(255,255,255,0.03)'},ticks:{color:'#555',font:{size:9,family:'JetBrains Mono'},callback:v=>v.toFixed(2)}}},interaction:{intersect:false,mode:'index'}}});}
function uC(v){if(!PC)return;PC.data.labels.push(fT());PC.data.datasets[0].data.push(v);if(PC.data.labels.length>60){PC.data.labels.shift();PC.data.datasets[0].data.shift();}PC.data.datasets[0].borderColor=v>=0?'#00ff88':'#ff4466';PC.data.datasets[0].backgroundColor=v>=0?'rgba(0,255,136,0.08)':'rgba(255,68,102,0.08)';PC.update('none');}

S.on('stats_update',function(d){
const mb=document.getElementById('mode-badge'),mt=document.getElementById('mode-text');
if(d.mode==='dry_run'){mb.className='sb sb-dry';mt.textContent='DRY RUN';}else{mb.className='sb sb-live';mt.textContent='LIVE';}
document.getElementById('cb-badge').classList.toggle('on',d.circuit_breaker);
document.getElementById('uptime').textContent=d.uptime||'0s';
const pnl=d.total_pnl_sol||0,pe=document.getElementById('tpnl');pe.textContent=fS(pnl);pe.className='sv cn '+(pnl>=0?'p':'n');if(pnl!==pp){fl('tpnl',pnl>=0?'p':'n');pp=pnl;}
document.getElementById('wr').textContent=fP(d.win_rate);document.getElementById('wrd').innerHTML='<span class="p">'+(d.winning||0)+'W</span> / <span class="n">'+(d.losing||0)+'L</span>';
document.getElementById('tt').textContent=d.total_trades||0;document.getElementById('apc').textContent=(d.active_positions||0)+' active';document.getElementById('pc').textContent=d.active_positions||0;
document.getElementById('rb').textContent=d.rugs_blocked||0;document.getElementById('tsc').textContent=(d.tokens_scanned||0)+' scanned';
document.getElementById('ts').textContent=d.tokens_scanned||0;document.getElementById('tsp').textContent=d.tokens_passed||0;
const sc=d.tokens_scanned||1,pd=d.tokens_passed||0;document.getElementById('pr').textContent=((pd/sc)*100).toFixed(1)+'% pass';
document.getElementById('pf').textContent=(d.profit_factor||0).toFixed(2);document.getElementById('mdd').textContent=fS(d.max_drawdown);
document.getElementById('dpb').textContent='Today: '+fS(d.daily_pnl)+' SOL';
if(d.max_sol_per_trade!==undefined){document.getElementById('sms').textContent=d.max_sol_per_trade+' SOL';document.getElementById('ssl').textContent=d.stop_loss+'%';document.getElementById('stp').textContent=d.take_profit+'%';document.getElementById('scn').textContent=d.max_concurrent;document.getElementById('ssp').textContent=d.slippage_bps+' bps';document.getElementById('smr').textContent=d.max_rug_score+'/100';}
document.getElementById('ps2').textContent=d.tokens_scanned||0;document.getElementById('ppr').textContent=((pd/sc)*100).toFixed(1)+'%';
const rb=d.rugs_blocked||0;document.getElementById('prr').textContent=((rb/sc)*100).toFixed(1)+'%';document.getElementById('ptr').textContent=(((d.total_trades||0)/sc)*100).toFixed(2)+'%';document.getElementById('pe').textContent=d.errors||0;
document.getElementById('fs').textContent=d.tokens_scanned||0;document.getElementById('fp').textContent=d.tokens_passed||0;document.getElementById('fr').textContent=pd-rb;document.getElementById('ft').textContent=d.total_trades||0;
const mx=Math.max(sc,1);document.getElementById('fbp').style.width=((pd/mx)*100)+'%';document.getElementById('fbr').style.width=(((pd-rb)/mx)*100)+'%';document.getElementById('fbt').style.width=(((d.total_trades||0)/mx)*100)+'%';
document.getElementById('sck').textContent=d.circuit_breaker?'BREAK':'OK';document.getElementById('sck').className='sv2 '+(d.circuit_breaker?'n':'p');document.getElementById('ser').textContent=d.errors||0;
uC(pnl);
});

S.on('position_update',function(ps){
const tb=document.getElementById('ptb');document.getElementById('pcb').textContent=ps.length+' open';
if(!ps.length){tb.innerHTML='<tr><td colspan="9"><div class="es"><i class="fas fa-layer-group"></i><h3>No positions</h3></div></td></tr>';return;}
tb.innerHTML=ps.map(p=>{const c=p.pnl>=0?'p':'n',i=p.pnl>=0?'▲':'▼',bw=Math.min(Math.abs(p.pnl),200)/2;
return'<tr><td><strong>'+p.symbol+'</strong><br><span class="ta">'+(p.address?p.address.substring(0,10)+'...':'')+'</span></td><td class="mono">'+fPr(p.entry_price)+'</td><td class="mono">'+fPr(p.current_price)+'</td><td class="mono">'+fS(p.entry_sol)+'</td><td class="mono '+c+'">'+i+' '+fP(p.pnl)+'</td><td class="mono n" style="font-size:10px">'+fPr(p.stop_loss)+'</td><td class="mono p" style="font-size:10px">'+fPr(p.take_profit)+'</td><td class="mono">'+p.duration+'</td><td><div class="pb"><div class="pf '+c+'" style="width:'+bw+'%"></div></div></td></tr>';}).join('');
});

S.on('trade_history',function(ts){
const tb=document.getElementById('htb');document.getElementById('hc').textContent=ts.length+' trades';
if(!ts.length){tb.innerHTML='<tr><td colspan="9"><div class="es"><i class="fas fa-history"></i><h3>No history</h3></div></td></tr>';return;}
tb.innerHTML=ts.map((t,i)=>{const p=t.pnl_percent||0,ps=t.pnl_sol||0,c=p>=0?'p':'n',rb=p>=0?'<span class="bg bg-g">WIN</span>':'<span class="bg bg-r">LOSS</span>';
return'<tr><td class="mono">'+(ts.length-i)+'</td><td class="mono" style="font-size:10px">'+(t.timestamp?new Date(t.timestamp*1000).toLocaleString():'-')+'</td><td><strong>'+(t.symbol||'???')+'</strong></td><td class="mono">'+fS(t.entry_sol)+'</td><td class="mono">'+fS(t.exit_sol)+'</td><td class="mono '+c+'">'+(p>=0?'+':'')+fP(p)+'</td><td class="mono '+c+'">'+(ps>=0?'+':'')+fS(ps)+'</td><td class="mono">'+(t.hold_time||'-')+'</td><td>'+rb+'</td></tr>';}).join('');
});

S.on('recent_trades',function(ts){
const tb=document.getElementById('rtb');if(!ts||!ts.length)return;
tb.innerHTML=ts.slice(0,10).map(t=>{const p=t.pnl_percent||0,c=p>=0?'p':'n',rb=p>=0?'<span class="bg bg-g">WIN</span>':'<span class="bg bg-r">LOSS</span>';
return'<tr><td class="mono" style="font-size:10px">'+(t.timestamp?new Date(t.timestamp*1000).toLocaleString():'-')+'</td><td><strong>'+(t.symbol||'???')+'</strong></td><td class="mono">'+fS(t.entry_sol)+'</td><td class="mono '+c+'">'+(p>=0?'+':'')+fP(p)+'</td><td class="mono">'+(t.hold_time||'-')+'</td><td>'+rb+'</td></tr>';}).join('');
});

S.on('new_alert',function(a){ac++;document.getElementById('ac').textContent=ac;aF('alr',a.type||'info',a.title||'',a.desc||'');aF('af',a.type||'info',a.title||'',a.desc||'');});

S.on('scanned_token',function(t){
const tb=document.getElementById('stb');const e=tb.querySelector('.es');if(e)tb.innerHTML='';
const rs=t.rug_score||0,rB=rs<=20?'<span class="bg bg-g">'+rs+'</span>':rs<=40?'<span class="bg bg-y">'+rs+'</span>':'<span class="bg bg-r">'+rs+'</span>';
const scB=t.screener_score?'<span class="bg bg-b">'+t.screener_score.toFixed(1)+'</span>':'-';
const dB=t.decision==='buy'?'<span class="bg bg-g">BUY</span>':t.decision==='rug_blocked'?'<span class="bg bg-r">BLOCKED</span>':'<span class="bg bg-y">SKIP</span>';
const r=document.createElement('tr');r.style.animation='fi .3s';
r.innerHTML='<td class="mono" style="font-size:10px">'+fT()+'</td><td><span class="ta">'+(t.address||'').substring(0,10)+'...</span></td><td><strong>'+(t.symbol||'???')+'</strong></td><td><span class="bg bg-p">'+(t.source||'?')+'</span></td><td class="mono">'+(t.liquidity?'$'+t.liquidity.toLocaleString():'-')+'</td><td class="mono">'+(t.holders||'-')+'</td><td>'+rB+'</td><td>'+scB+'</td><td>'+dB+'</td>';
tb.insertBefore(r,tb.firstChild);while(tb.children.length>50)tb.removeChild(tb.lastChild);
});

S.on('rug_blocked',function(d){
const f=document.getElementById('btf');const e=f.querySelector('.es');if(e)e.remove();
const i=document.createElement('div');i.className='fi rug';
i.innerHTML='<div class="fic"><i class="fas fa-shield-virus"></i></div><div style="flex:1"><div class="fit">'+(d.symbol||'Unknown')+' - '+d.score+'/100</div><div class="fid">'+((d.reasons||[]).join(', ')||'Multiple risks')+'</div></div><div class="ft">'+fT()+'</div>';
f.insertBefore(i,f.firstChild);
});

S.on('connect',function(){document.getElementById('ws').innerHTML='<div class="sd" style="background:var(--g)"></div><span>CONNECTED</span>';aF('af','info','Connected','WebSocket ready');});
S.on('disconnect',function(){document.getElementById('ws').innerHTML='<div class="sd" style="background:var(--r)"></div><span>OFFLINE</span>';document.getElementById('ws').style.borderColor='var(--r)';document.getElementById('ws').style.color='var(--r)';document.getElementById('ws').style.background='var(--rg)';});

document.addEventListener('DOMContentLoaded',function(){iC();});
</script>
</body></html>
"""


# ═══════════════════════════════
#  PYTHON DASHBOARD CLASS
# ═══════════════════════════════

class Dashboard:
    def __init__(self, risk_manager: RiskManager, port: int = None):
        self.app = Flask(__name__)
        self.app.config["SECRET_KEY"] = os.urandom(24).hex()
        self.socketio = SocketIO(self.app, cors_allowed_origins="*",
            async_mode="threading", logger=False, engineio_logger=False)
        self.risk_manager = risk_manager
        self.port = port or int(os.environ.get("DASHBOARD_PORT", 5000))
        self.trade_history = []
        self.scanned_tokens = []
        self.alerts = []
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route("/")
        def index():
            return render_template_string(DASHBOARD_HTML)

        @self.app.route("/api/stats")
        def api_stats():
            return jsonify(self.risk_manager.get_stats())

        @self.app.route("/api/positions")
        def api_positions():
            ps = []
            for a, p in self.risk_manager.positions.items():
                if p.status == "open":
                    ps.append({"token":a,"symbol":p.symbol,"entry":p.entry_price,
                        "sl":p.stop_loss_price,"tp":p.take_profit_price,"dur":p.hold_duration()})
            return jsonify({"positions":ps})

        @self.app.route("/api/history")
        def api_history():
            return jsonify({"trades":self.trade_history[-100:]})

    def emit_update(self, event, data):
        try: self.socketio.emit(event, data, namespace="/")
        except: pass

    def emit_alert(self, alert_type, title, desc):
        a = {"type":alert_type,"title":title,"desc":desc,"timestamp":current_timestamp()}
        self.alerts.append(a)
        if len(self.alerts)>200: self.alerts=self.alerts[-200:]
        self.emit_update("new_alert", a)

    def emit_scanned_token(self, td, decision):
        info = {"address":td.get("address",""),"symbol":td.get("symbol","???"),
            "source":td.get("source","unknown"),"liquidity":td.get("liquidity",0),
            "holders":td.get("holder_count",0),"rug_score":td.get("rugpull_score",0),
            "screener_score":td.get("screener_score",0),"decision":decision,
            "timestamp":current_timestamp()}
        self.scanned_tokens.append(info)
        if len(self.scanned_tokens)>200: self.scanned_tokens=self.scanned_tokens[-200:]
        self.emit_update("scanned_token", info)

    def emit_rug_blocked(self, td, score, reasons):
        self.emit_update("rug_blocked", {"address":td.get("address",""),
            "symbol":td.get("symbol","???"),"score":score,"reasons":reasons})

    def add_trade_to_history(self, trade):
        self.trade_history.append(trade)
        if len(self.trade_history)>500: self.trade_history=self.trade_history[-500:]
        self.emit_update("trade_history", self.trade_history[-50:])
        self.emit_update("recent_trades", self.trade_history[-10:])

    def start_async(self):
        t = threading.Thread(target=lambda: self.socketio.run(self.app,
            host="0.0.0.0",port=self.port,debug=False,use_reloader=False,
            allow_unsafe_werkzeug=True), daemon=True, name="Dashboard")
        t.start()
        return t