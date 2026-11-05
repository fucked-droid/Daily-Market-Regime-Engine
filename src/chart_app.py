"""
Interactive Financial Charting Application for Daily Market Regime Engine.
Plots NIFTY 50 candlestick price action with automatically drawn:
  - Resistance (R1) & Support (S1) zones
  - Tomorrow's Expected Day Ceiling & Day Floor (Dotted bounds)
  - Institutional Call Wall & Put Floor lines
  - Dynamic EMAs (EMA20, EMA50, EMA200)
  - Floating Trade Playbook HUD & TradingView Pine Script v5 Export
Opens directly in the user's default browser.
"""

from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd


def generate_pine_script_v5(forecast: Dict[str, Any]) -> str:
    """Generate ready-to-paste Pine Script v5 indicator for TradingView."""
    r1 = float(forecast.get("nearest_resistance", {}).get("price", 0.0))
    s1 = float(forecast.get("nearest_support", {}).get("price", 0.0))
    close = float(forecast.get("nifty_close", 0.0))
    atr = float(forecast.get("atr_14", 0.0))

    exp = forecast.get("expected_range", {})
    day_ceil = float(exp.get("expected_daily_upper") or exp.get("expected_high") or (close + atr))
    day_floor = float(exp.get("expected_daily_lower") or exp.get("expected_low") or (close - atr))

    opt = forecast.get("option_data") or {}
    call_wall = float(opt.get("major_resistance_wall") or opt.get("major_call_wall") or 0.0)
    put_floor = float(opt.get("major_support_floor") or opt.get("major_put_floor") or 0.0)
    as_of = forecast.get("as_of_date", "")

    return f"""//@version=5
indicator("Daily Market Regime Engine Levels [{as_of}]", overlay=true)

// --- REGIME ENGINE PREDICTED LEVELS ---
r1_val      = input.float({r1:.2f}, "Resistance R1 (Red)")
s1_val      = input.float({s1:.2f}, "Support S1 (Green)")
ceil_val    = input.float({day_ceil:.2f}, "Day Ceiling (Dotted Top)")
floor_val   = input.float({day_floor:.2f}, "Day Floor (Dotted Bottom)")
call_wall   = input.float({call_wall:.2f}, "Major Call Wall (Pink)")
put_wall    = input.float({put_floor:.2f}, "Major Put Floor (Teal)")

// Plot Horizontal Lines
plot(r1_val > 0 ? r1_val : na, "Resistance R1", color=color.new(color.red, 10), linewidth=2)
plot(s1_val > 0 ? s1_val : na, "Support S1", color=color.new(color.green, 10), linewidth=2)
plot(ceil_val > 0 ? ceil_val : na, "Day Ceiling", color=color.new(color.orange, 10), linewidth=2, style=plot.style_circles)
plot(floor_val > 0 ? floor_val : na, "Day Floor", color=color.new(color.aqua, 10), linewidth=2, style=plot.style_circles)
plot(call_wall > 0 ? call_wall : na, "Call Wall", color=color.new(color.purple, 30), linewidth=1, style=plot.style_linebr)
plot(put_wall > 0 ? put_wall : na, "Put Floor", color=color.new(color.teal, 30), linewidth=1, style=plot.style_linebr)

// Plot Standard EMAs
plot(ta.ema(close, 20), "EMA 20", color=color.yellow, linewidth=1)
plot(ta.ema(close, 50), "EMA 50", color=color.orange, linewidth=1)
plot(ta.ema(close, 200), "EMA 200", color=color.purple, linewidth=2)
"""


def build_chart_html(forecast: Dict[str, Any], df: pd.DataFrame) -> str:
    """Build full interactive TradingView Lightweight Charts HTML document."""
    # Filter last ~200 trading sessions for fast, responsive rendering
    plot_df = df.tail(200).copy()
    plot_df = plot_df.sort_index()

    candle_data = []
    ema20_data = []
    ema50_data = []
    ema200_data = []

    for idx, row in plot_df.iterrows():
        date_str = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        o = float(row.get("Open", row.get("Close", 0.0)))
        h = float(row.get("High", row.get("Close", 0.0)))
        l = float(row.get("Low", row.get("Close", 0.0)))
        c = float(row.get("Close", 0.0))

        candle_data.append({"time": date_str, "open": o, "high": h, "low": l, "close": c})

        if "EMA20" in row and not np.isnan(row["EMA20"]):
            ema20_data.append({"time": date_str, "value": float(row["EMA20"])})
        if "EMA50" in row and not np.isnan(row["EMA50"]):
            ema50_data.append({"time": date_str, "value": float(row["EMA50"])})
        if "EMA200" in row and not np.isnan(row["EMA200"]):
            ema200_data.append({"time": date_str, "value": float(row["EMA200"])})

    # Extract target levels
    res = forecast.get("nearest_resistance", {})
    r1 = float(res.get("price", 0.0))
    res_range = res.get("range", [])
    r1_low = float(res_range[0]) if len(res_range) > 0 else r1
    r1_high = float(res_range[1]) if len(res_range) > 1 else r1

    sup = forecast.get("nearest_support", {})
    s1 = float(sup.get("price", 0.0))
    sup_range = sup.get("range", [])
    s1_low = float(sup_range[0]) if len(sup_range) > 0 else s1
    s1_high = float(sup_range[1]) if len(sup_range) > 1 else s1

    as_of = forecast.get("as_of_date", "")
    close = float(forecast.get("nifty_close", 0.0))
    regime = str(forecast.get("current_regime", "Unknown"))
    rsi = float(forecast.get("rsi_14", 0.0))
    atr = float(forecast.get("atr_14", 0.0))
    bias = str(forecast.get("trading_bias", "NEUTRAL"))

    exp_range = forecast.get("expected_range", {})
    day_ceil = float(exp_range.get("expected_daily_upper") or exp_range.get("expected_high") or (close + atr))
    day_floor = float(exp_range.get("expected_daily_lower") or exp_range.get("expected_low") or (close - atr))

    opt = forecast.get("option_data") or {}
    call_wall = float(opt.get("major_resistance_wall") or opt.get("major_call_wall") or 0.0)
    put_floor = float(opt.get("major_support_floor") or opt.get("major_put_floor") or 0.0)

    alerts_list = forecast.get("alerts") or []
    alerts_html = ""
    if alerts_list:
        items = "".join([f'<span style="padding: 2px 8px; border-radius: 4px; background: rgba(244, 63, 94, 0.25); border: 1px solid #f43f5e; color: #fff; font-weight: 600;">{a.get("message", "")}</span>' for a in alerts_list[:3]])
        alerts_html = f'''
  <div style="background: rgba(244, 63, 94, 0.15); border-bottom: 1px solid rgba(244, 63, 94, 0.4); padding: 6px 24px; font-size: 12px; display: flex; align-items: center; gap: 12px; z-index: 10;">
    <span style="color: #f43f5e; font-weight: 700; text-transform: uppercase;">🚨 Active Live Alerts:</span>
    <div style="display: flex; gap: 8px; flex-wrap: wrap;">{items}</div>
  </div>'''

    pine_script = generate_pine_script_v5(forecast)

    candles_json = json.dumps(candle_data)
    ema20_json = json.dumps(ema20_data)
    ema50_json = json.dumps(ema50_data)
    ema200_json = json.dumps(ema200_data)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NIFTY 50 Daily Market Regime Chart - {as_of}</title>
  <script src="https://unpkg.com/lightweight-charts@4.2.0/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    :root {{
      --bg-dark: #0f172a;
      --card-bg: rgba(30, 41, 59, 0.85);
      --border-color: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent-bullish: #10b981;
      --accent-bearish: #ef4444;
      --accent-r1: #f43f5e;
      --accent-s1: #10b981;
      --accent-ceil: #f59e0b;
      --accent-floor: #06b6d4;
      --accent-wall: #ec4899;
    }}
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
    }}
    body {{
      background: var(--bg-dark);
      color: var(--text-main);
      overflow: hidden;
      height: 100vh;
      display: flex;
      flex-direction: column;
    }}
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 12px 24px;
      background: rgba(15, 23, 42, 0.95);
      border-bottom: 1px solid var(--border-color);
      z-index: 10;
    }}
    .brand {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .badge-bullish {{
      background: rgba(16, 185, 129, 0.2);
      color: var(--accent-bullish);
      border: 1px solid rgba(16, 185, 129, 0.4);
    }}
    .badge-bearish {{
      background: rgba(239, 68, 68, 0.2);
      color: var(--accent-bearish);
      border: 1px solid rgba(239, 68, 68, 0.4);
    }}
    .metrics {{
      display: flex;
      gap: 20px;
      font-size: 13px;
    }}
    .metric-item {{
      display: flex;
      flex-direction: column;
    }}
    .metric-label {{
      color: var(--text-muted);
      font-size: 11px;
      text-transform: uppercase;
    }}
    .metric-value {{
      font-weight: 600;
      color: var(--text-main);
    }}
    .actions {{
      display: flex;
      gap: 10px;
    }}
    .btn {{
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      border: 1px solid var(--border-color);
      background: #1e293b;
      color: var(--text-main);
      transition: all 0.2s ease;
      text-decoration: none;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }}
    .btn:hover {{
      background: #334155;
      border-color: #64748b;
    }}
    .btn-primary {{
      background: #2563eb;
      border-color: #3b82f6;
    }}
    .btn-primary:hover {{
      background: #1d4ed8;
    }}
    #chart-wrapper {{
      position: relative;
      flex: 1;
      width: 100%;
      height: 100%;
    }}
    #tv-chart {{
      width: 100%;
      height: 100%;
    }}
    .hud-card {{
      position: absolute;
      top: 16px;
      left: 16px;
      background: var(--card-bg);
      backdrop-filter: blur(8px);
      border: 1px solid var(--border-color);
      border-radius: 8px;
      padding: 14px 18px;
      z-index: 5;
      max-width: 380px;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);
    }}
    .hud-title {{
      font-size: 13px;
      font-weight: 700;
      color: #94a3b8;
      margin-bottom: 8px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .level-row {{
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      margin-bottom: 5px;
      align-items: center;
    }}
    .level-color {{
      display: inline-block;
      width: 10px;
      height: 10px;
      border-radius: 2px;
      margin-right: 6px;
    }}
    .playbook-box {{
      margin-top: 10px;
      padding-top: 10px;
      border-top: 1px solid var(--border-color);
      font-size: 11px;
      line-height: 1.45;
      color: #cbd5e1;
    }}
    .playbook-item {{
      margin-bottom: 4px;
    }}
    /* Modal */
    #pine-modal {{
      display: none;
      position: fixed;
      top: 0;
      left: 0;
      width: 100vw;
      height: 100vh;
      background: rgba(0,0,0,0.7);
      backdrop-filter: blur(4px);
      z-index: 100;
      align-items: center;
      justify-content: center;
    }}
    .modal-content {{
      background: #1e293b;
      border: 1px solid #475569;
      border-radius: 10px;
      padding: 24px;
      max-width: 620px;
      width: 90%;
      color: #f8fafc;
    }}
    pre {{
      background: #0f172a;
      padding: 12px;
      border-radius: 6px;
      font-family: monospace;
      font-size: 12px;
      max-height: 280px;
      overflow-y: auto;
      margin: 12px 0;
      color: #38bdf8;
    }}
  </style>
</head>
<body>

  <header>
    <div class="brand">
      <h2 style="font-size: 18px; font-weight: 800;">NIFTY 50</h2>
      <span class="badge {'badge-bullish' if 'Bullish' in regime else 'badge-bearish'}">{regime}</span>
      <span style="font-size: 13px; color: var(--text-muted);">As of: {as_of}</span>
      <span style="display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: #10b981; font-weight: 700; letter-spacing: 0.05em; margin-left: 6px;">
        <span style="width: 7px; height: 7px; border-radius: 50%; background: #10b981; box-shadow: 0 0 6px #10b981;"></span> LIVE
      </span>
    </div>

    <div class="metrics">
      <div class="metric-item">
        <span class="metric-label">Close</span>
        <span class="metric-value">{close:,.2f}</span>
      </div>
      <div class="metric-item">
        <span class="metric-label">Bias</span>
        <span class="metric-value" style="color: var(--accent-bullish);">{bias}</span>
      </div>
      <div class="metric-item">
        <span class="metric-label">RSI(14)</span>
        <span class="metric-value">{rsi:.1f}</span>
      </div>
      <div class="metric-item">
        <span class="metric-label">ATR(14)</span>
        <span class="metric-value">{atr:.1f} pts</span>
      </div>
    </div>

    <div class="actions">
      <button class="btn" style="border-color: #00d09c; color: #00d09c; font-weight: 700;" onclick="openGrowwModal()">🌱 Groww Marker</button>
      <a href="https://groww.in/charts/stocks/nifty-50" target="_blank" class="btn">🚀 Open Groww Chart</a>
      <button class="btn" onclick="openPineModal()">📋 Pine Script (TV)</button>
      <a href="https://in.tradingview.com/chart/?symbol=NSE%3ANIFTY" target="_blank" class="btn">TradingView Live</a>
      <a href="https://tv.dhan.co" target="_blank" class="btn">Dhan TV</a>
      <button id="btn-toggle-refresh" class="btn" onclick="toggleAutoRefresh()">🔄 Live: <span id="refresh-timer">15s</span></button>
      <button class="btn btn-primary" onclick="fitChart()">Reset Zoom</button>
    </div>
  </header>
  {alerts_html}

  <div id="chart-wrapper">
    <div id="tv-chart"></div>

    <div class="hud-card">
      <div class="hud-title">Engine Projected Levels</div>
      <div class="level-row">
        <span><span class="level-color" style="background: var(--accent-r1);"></span>Resistance R1</span>
        <strong style="color: var(--accent-r1);">{r1:,.2f}</strong>
      </div>
      <div class="level-row">
        <span><span class="level-color" style="background: var(--accent-ceil);"></span>Dotted Top (Day High)</span>
        <strong style="color: var(--accent-ceil);">{day_ceil:,.2f}</strong>
      </div>
      <div class="level-row">
        <span><span class="level-color" style="background: var(--accent-wall);"></span>Call Wall Ceiling</span>
        <strong style="color: var(--accent-wall);">{call_wall:,.2f}</strong>
      </div>
      <div class="level-row">
        <span><span class="level-color" style="background: #10b981;"></span>Put Floor Strike</span>
        <strong style="color: #10b981;">{put_floor:,.2f}</strong>
      </div>
      <div class="level-row">
        <span><span class="level-color" style="background: var(--accent-floor);"></span>Dotted Btm (Day Low)</span>
        <strong style="color: var(--accent-floor);">{day_floor:,.2f}</strong>
      </div>
      <div class="level-row">
        <span><span class="level-color" style="background: var(--accent-s1);"></span>Support S1</span>
        <strong style="color: var(--accent-s1);">{s1:,.2f}</strong>
      </div>

      <div class="playbook-box">
        <strong style="color: #38bdf8;">ACTION PLAYBOOK:</strong>
        <div class="playbook-item">• <strong>Breakout BUY (Call):</strong> 15m candle close above {r1:,.0f} -> Targets: {day_ceil:,.0f} / {r1_high:,.0f}</div>
        <div class="playbook-item">• <strong>Rejection SHORT (Put):</strong> Rejection at {r1:,.0f} -> Target: {close:,.0f}</div>
        <div class="playbook-item">• <strong>Dip BUY (Call):</strong> Bounce off {day_floor:,.0f} / S1 -> Target: {close:,.0f}</div>
      </div>
    </div>
  </div>

  <div id="pine-modal">
    <div class="modal-content">
      <h3 style="margin-bottom: 8px;">TradingView Pine Script v5</h3>
      <p style="font-size: 13px; color: #94a3b8;">Copy and paste this script directly into your TradingView Pine Editor to overlay these exact engine levels on your live TradingView charts.</p>
      <pre id="pine-code">{pine_script}</pre>
      <div style="display: flex; justify-content: flex-end; gap: 10px;">
        <button class="btn" onclick="copyPineScript()">Copy Script</button>
        <button class="btn btn-primary" onclick="closePineModal()">Close</button>
      </div>
    </div>
  </div>

  <div id="groww-modal" style="display:none; position:fixed; top:0; left:0; width:100%; height:100%; background:rgba(0,0,0,0.7); z-index:9999; justify-content:center; align-items:center;">
    <div class="modal-content" style="background:#1e293b; border:1px solid #00d09c; border-radius:12px; padding:24px; max-width:620px; width:90%; color:#f8fafc;">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
        <h3 style="color:#00d09c; font-size:18px; font-weight:700;">🌱 Groww NIFTY 50 Chart Marking Tool</h3>
        <span style="font-size:12px; background:rgba(0,208,156,0.15); color:#00d09c; padding:3px 8px; border-radius:4px; font-weight:600;">Groww Terminal Ready</span>
      </div>
      <p style="font-size:13px; color:#94a3b8; margin-bottom:14px;">Open your NIFTY 50 chart on Groww (<a href="https://groww.in/charts/stocks/nifty-50" target="_blank" style="color:#38bdf8; text-decoration:underline;">groww.in/charts/stocks/nifty-50</a>). Use the <strong>Horizontal Line (Alt + H)</strong> tool on Groww's chart and input these coordinates:</p>
      
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-bottom:16px;">
        <div style="background:#0f172a; padding:10px 14px; border-radius:8px; border-left:4px solid #f43f5e; display:flex; justify-content:space-between; align-items:center;">
          <div><div style="font-size:11px; color:#94a3b8;">🔴 RESISTANCE R1</div><strong style="color:#f43f5e; font-size:15px;">{r1:,.2f}</strong></div>
          <button class="btn" style="padding:3px 8px; font-size:11px;" onclick="navigator.clipboard.writeText('{r1:.2f}'); alert('Copied R1: {r1:.2f}')">Copy</button>
        </div>
        <div style="background:#0f172a; padding:10px 14px; border-radius:8px; border-left:4px solid #10b981; display:flex; justify-content:space-between; align-items:center;">
          <div><div style="font-size:11px; color:#94a3b8;">🟢 SUPPORT S1</div><strong style="color:#10b981; font-size:15px;">{s1:,.2f}</strong></div>
          <button class="btn" style="padding:3px 8px; font-size:11px;" onclick="navigator.clipboard.writeText('{s1:.2f}'); alert('Copied S1: {s1:.2f}')">Copy</button>
        </div>
        <div style="background:#0f172a; padding:10px 14px; border-radius:8px; border-left:4px solid #f59e0b; display:flex; justify-content:space-between; align-items:center;">
          <div><div style="font-size:11px; color:#94a3b8;">🟠 DAY CEILING (HIGH)</div><strong style="color:#f59e0b; font-size:15px;">{day_ceil:,.2f}</strong></div>
          <button class="btn" style="padding:3px 8px; font-size:11px;" onclick="navigator.clipboard.writeText('{day_ceil:.2f}'); alert('Copied Day Ceiling: {day_ceil:.2f}')">Copy</button>
        </div>
        <div style="background:#0f172a; padding:10px 14px; border-radius:8px; border-left:4px solid #06b6d4; display:flex; justify-content:space-between; align-items:center;">
          <div><div style="font-size:11px; color:#94a3b8;">🔵 DAY FLOOR (LOW)</div><strong style="color:#06b6d4; font-size:15px;">{day_floor:,.2f}</strong></div>
          <button class="btn" style="padding:3px 8px; font-size:11px;" onclick="navigator.clipboard.writeText('{day_floor:.2f}'); alert('Copied Day Floor: {day_floor:.2f}')">Copy</button>
        </div>
        <div style="background:#0f172a; padding:10px 14px; border-radius:8px; border-left:4px solid #ec4899; display:flex; justify-content:space-between; align-items:center;">
          <div><div style="font-size:11px; color:#94a3b8;">🟣 CALL WALL (CEILING)</div><strong style="color:#ec4899; font-size:15px;">{call_wall:,.2f}</strong></div>
          <button class="btn" style="padding:3px 8px; font-size:11px;" onclick="navigator.clipboard.writeText('{call_wall:.2f}'); alert('Copied Call Wall: {call_wall:.2f}')">Copy</button>
        </div>
        <div style="background:#0f172a; padding:10px 14px; border-radius:8px; border-left:4px solid #10b981; display:flex; justify-content:space-between; align-items:center;">
          <div><div style="font-size:11px; color:#94a3b8;">🟢 PUT FLOOR (BASE)</div><strong style="color:#10b981; font-size:15px;">{put_floor:,.2f}</strong></div>
          <button class="btn" style="padding:3px 8px; font-size:11px;" onclick="navigator.clipboard.writeText('{put_floor:.2f}'); alert('Copied Put Floor: {put_floor:.2f}')">Copy</button>
        </div>
      </div>

      <div style="background:#0f172a; padding:10px; border-radius:6px; font-size:11px; color:#94a3b8; margin-bottom:16px;">
        💡 <strong>Groww Pro Tip:</strong> Press <kbd style="background:#334155; padding:2px 5px; border-radius:3px; color:#fff;">Alt + H</kbd> anywhere on Groww's chart to quickly drop a horizontal line, double-click the line, and paste the coordinate value!
      </div>

      <div style="display:flex; justify-content:space-between; align-items:center;">
        <button class="btn" onclick="copyGrowwSummary()">📋 Copy All Levels</button>
        <div style="display:flex; gap:10px;">
          <a href="https://groww.in/charts/stocks/nifty-50" target="_blank" class="btn" style="background:#00d09c; color:#0f172a; font-weight:700;">🚀 Open Groww Chart</a>
          <button class="btn btn-primary" onclick="closeGrowwModal()">Close</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    const chartContainer = document.getElementById('tv-chart');
    const chart = LightweightCharts.createChart(chartContainer, {{
      width: chartContainer.clientWidth,
      height: chartContainer.clientHeight,
      layout: {{
        background: {{ color: '#0f172a' }},
        textColor: '#94a3b8',
      }},
      grid: {{
        vertLines: {{ color: '#1e293b' }},
        horzLines: {{ color: '#1e293b' }},
      }},
      crosshair: {{
        mode: LightweightCharts.CrosshairMode.Normal,
      }},
      rightPriceScale: {{
        borderColor: '#334155',
      }},
      timeScale: {{
        borderColor: '#334155',
        timeVisible: true,
      }},
    }});

    const candleSeries = chart.addCandlestickSeries({{
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    }});

    const candles = {candles_json};
    candleSeries.setData(candles);

    // EMAs
    const ema20Series = chart.addLineSeries({{ color: '#facc15', lineWidth: 1, title: 'EMA 20' }});
    ema20Series.setData({ema20_json});

    const ema50Series = chart.addLineSeries({{ color: '#fb923c', lineWidth: 1, title: 'EMA 50' }});
    ema50Series.setData({ema50_json});

    const ema200Series = chart.addLineSeries({{ color: '#a855f7', lineWidth: 2, title: 'EMA 200' }});
    ema200Series.setData({ema200_json});

    // Marked Levels on the Chart
    const r1 = {r1};
    if (r1 > 0) {{
      candleSeries.createPriceLine({{
        price: r1,
        color: '#f43f5e',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Solid,
        axisLabelVisible: true,
        title: 'LAAL LINE: Resistance R1 ({r1:,.0f})',
      }});
    }}

    const s1 = {s1};
    if (s1 > 0) {{
      candleSeries.createPriceLine({{
        price: s1,
        color: '#10b981',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Solid,
        axisLabelVisible: true,
        title: 'HARI LINE: Support S1 ({s1:,.0f})',
      }});
    }}

    const dayCeil = {day_ceil};
    if (dayCeil > 0) {{
      candleSeries.createPriceLine({{
        price: dayCeil,
        color: '#f59e0b',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: 'DOTTED TOP: Day Ceiling ({day_ceil:,.0f})',
      }});
    }}

    const dayFloor = {day_floor};
    if (dayFloor > 0) {{
      candleSeries.createPriceLine({{
        price: dayFloor,
        color: '#06b6d4',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: 'DOTTED BTM: Day Floor ({day_floor:,.0f})',
      }});
    }}

    const callWall = {call_wall};
    if (callWall > 0) {{
      candleSeries.createPriceLine({{
        price: callWall,
        color: '#ec4899',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'Call Wall Ceiling ({call_wall:,.0f})',
      }});
    }}

    const putFloor = {put_floor};
    if (putFloor > 0) {{
      candleSeries.createPriceLine({{
        price: putFloor,
        color: '#10b981',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: 'Put Floor Base ({put_floor:,.0f})',
      }});
    }}

    window.addEventListener('resize', () => {{
      chart.applyOptions({{
        width: chartContainer.clientWidth,
        height: chartContainer.clientHeight,
      }});
    }});

    function fitChart() {{
      chart.timeScale().fitContent();
    }}

    function openPineModal() {{
      document.getElementById('pine-modal').style.display = 'flex';
    }}

    function closePineModal() {{
      document.getElementById('pine-modal').style.display = 'none';
    }}

    function openGrowwModal() {{
      document.getElementById('groww-modal').style.display = 'flex';
    }}

    function closeGrowwModal() {{
      document.getElementById('groww-modal').style.display = 'none';
    }}

    function copyGrowwSummary() {{
      const summary = `GROWW NIFTY 50 CHART LEVELS ({as_of}):\\n• Resistance R1: {r1:.2f}\\n• Day Ceiling: {day_ceil:.2f}\\n• Call Wall: {call_wall:.2f}\\n• Put Floor: {put_floor:.2f}\\n• Day Floor: {day_floor:.2f}\\n• Support S1: {s1:.2f}`;
      navigator.clipboard.writeText(summary).then(() => {{
        alert('All Groww levels copied to clipboard!');
      }});
    }}

    function copyPineScript() {{
      const code = document.getElementById('pine-code').innerText;
      navigator.clipboard.writeText(code).then(() => {{
        alert('Pine Script copied to clipboard! Paste it into TradingView Pine Editor.');
      }});
    }}

    let refreshCountdown = 15;
    let autoRefreshActive = true;
    function updateRefresh() {{
      if (!autoRefreshActive) return;
      const el = document.getElementById('refresh-timer');
      if (el) el.innerText = refreshCountdown + 's';
      refreshCountdown--;
      if (refreshCountdown <= 0) {{
        window.location.reload();
      }}
    }}
    function toggleAutoRefresh() {{
      autoRefreshActive = !autoRefreshActive;
      const btn = document.getElementById('btn-toggle-refresh');
      if (btn) {{
        btn.innerHTML = autoRefreshActive ? '🔄 Auto-Refresh: <span id=\"refresh-timer\">15s</span>' : '⏸ Auto-Refresh: OFF';
      }}
    }}
    setInterval(updateRefresh, 1000);
  </script>
</body>
</html>
"""
    return html


def launch_chart_application(
    forecast: Optional[Dict[str, Any]] = None,
    output_html_path: Optional[str] = None,
    open_browser: bool = True,
) -> str:
    """Generate chart HTML file and immediately launch it in default browser."""
    repo_root = Path(__file__).resolve().parent.parent
    if forecast is None:
        from scan_nifty import scan_and_predict
        forecast = scan_and_predict(update_data=False)

    from src.engine import load_nifty_master, build_core_engine, add_regime_layer
    df = load_nifty_master()
    df = build_core_engine(df)
    df = add_regime_layer(df)

    html_content = build_chart_html(forecast, df)

    if not output_html_path:
        output_html_path = str(repo_root / "nifty_regime_chart.html")

    with open(output_html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n[CHART READY] Interactive chart generated at: {output_html_path}")

    if open_browser:
        uri = Path(output_html_path).resolve().as_uri()
        print(f"[BROWSER] Launching chart application in your default browser: {uri}")
        webbrowser.open(uri)

    return output_html_path


if __name__ == "__main__":
    launch_chart_application(open_browser=True)
