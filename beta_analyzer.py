"""
A股 β 分析工具 v2.0
输入：股票代码（如 300750.SZ、600519.SS）
      支持批量：可输入多个股票代码
      支持自定义基准：--bench 代码
输出：1年β值、5年β值、风险等级、解读、散点图、β走势图、HTML报告
"""

import yfinance as yf
import pandas as pd
import numpy as np
import sys
import os
import requests
import argparse
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm

# ── 输出目录 ──
OUTPUT_DIR = "/Users/zmbgzx/Projects/beta_analyzer/output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ── 中文字体设置 ──
chinese_fonts = [f.name for f in fm.fontManager.ttflist if any(c > '\u4e00' for c in f.name)]
if chinese_fonts:
    plt.rcParams['font.sans-serif'] = [chinese_fonts[0], 'Heiti TC', 'PingFang SC', 'Noto Sans CJK SC']
else:
    plt.rcParams['font.sans-serif'] = ['Heiti TC', 'PingFang SC', 'Noto Sans CJK SC']
plt.rcParams['axes.unicode_minus'] = False

# ── 颜色方案（最多16只股票） ──
COLORS = ['#3B82F6', '#EF4444', '#10B981', '#F59E0B', '#8B5CF6',
          '#EC4899', '#06B6D4', '#F97316', '#6366F1', '#14B8A6',
          '#DC2626', '#2563EB', '#7C3AED', '#DB2777', '#0284C7', '#65A30D']


# ═══════════════════════════════════════════
# 核心计算
# ═══════════════════════════════════════════

def calc_beta(stock_code, bench_code="000300.SS", period="1y"):
    """计算单只股票相对于基准的β值，返回β值和收益率数据"""
    try:
        stock = yf.download(stock_code, period=period, auto_adjust=True, progress=False)["Close"]
        bench = yf.download(bench_code, period=period, auto_adjust=True, progress=False)["Close"]

        if isinstance(stock, pd.DataFrame):
            stock = stock.iloc[:, 0]
        if isinstance(bench, pd.DataFrame):
            bench = bench.iloc[:, 0]

        stock_ret = stock.pct_change().dropna()
        bench_ret = bench.pct_change().dropna()

        combined = pd.concat({"stock": stock_ret, "bench": bench_ret}, axis=1).dropna()

        if len(combined) < 5:
            return None, 0, None

        cov = np.cov(combined["stock"], combined["bench"])[0][1]
        var = np.var(combined["bench"])
        beta = cov / var if var != 0 else None
        return beta, len(combined), combined
    except Exception as e:
        return None, 0, None


def calc_rolling_beta(stock_code, bench_code="000300.SS", window=60, period="3y"):
    """计算滚动窗口β，返回时间序列"""
    try:
        stock = yf.download(stock_code, period=period, auto_adjust=True, progress=False)["Close"]
        bench = yf.download(bench_code, period=period, auto_adjust=True, progress=False)["Close"]

        if isinstance(stock, pd.DataFrame):
            stock = stock.iloc[:, 0]
        if isinstance(bench, pd.DataFrame):
            bench = bench.iloc[:, 0]

        stock_ret = stock.pct_change().dropna()
        bench_ret = bench.pct_change().dropna()

        combined = pd.concat({"stock": stock_ret, "bench": bench_ret}, axis=1).dropna()

        if len(combined) < window:
            return None

        # 滚动窗口计算β
        roll_cov = combined["stock"].rolling(window).cov(combined["bench"])
        roll_var = combined["bench"].rolling(window).var()
        roll_beta = roll_cov / roll_var
        roll_beta = roll_beta.dropna()

        return roll_beta
    except Exception as e:
        return None


# ═══════════════════════════════════════════
# 名称获取
# ═══════════════════════════════════════════

def search_stock_name(code):
    """通过网络搜索股票代码对应的中文名称"""
    code_clean = code.replace(".SS", "").replace(".SZ", "")
    market = "1" if code.endswith(".SS") else "0"
    url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={market}.{code_clean}&fltt=2&fields=f58,f57,f43"
    try:
        resp = requests.get(url, timeout=5)
        data = resp.json()
        name = data.get("data", {}).get("f58", "")
        if name:
            return name
    except:
        pass
    return None


def get_stock_name(code):
    """获取股票名称——优先东方财富中文，其次yfinance英文"""
    searched = search_stock_name(code)
    if searched:
        return searched
    try:
        stock = yf.Ticker(code)
        info = stock.info
        return info.get("longName", info.get("shortName", code))
    except:
        return code


# ═══════════════════════════════════════════
# 风险评估 & 解读
# ═══════════════════════════════════════════

def risk_level(beta):
    if beta is None:
        return "数据不足"
    if beta >= 1.5:
        return "高风险"
    elif beta >= 1.0:
        return "中高风险"
    elif beta >= 0.8:
        return "中等风险"
    elif beta >= 0.5:
        return "中低风险"
    else:
        return "低风险"


def interpret(beta_1y, beta_5y):
    lines = []
    if beta_1y is not None:
        lines.append(f"近1年Beta={beta_1y:.2f}，属于【{risk_level(beta_1y)}】，"
                     f"意味着近期该股波动{'高于' if beta_1y > 1 else '低于'}大盘")
    if beta_5y is not None:
        lines.append(f"近5年Beta={beta_5y:.2f}，属于【{risk_level(beta_5y)}】，"
                     f"长期来看该股波动{'高于' if beta_5y > 1 else '低于'}大盘")
    if beta_1y is not None and beta_5y is not None:
        diff = beta_1y - beta_5y
        if abs(diff) > 0.2:
            lines.append(f"⚠ 1年和5年的Beta值相差{diff:.2f}，说明该股的'股票性格'在变化——"
                         f"可能是公司所处行业周期或自身发展阶段发生了变化。")
        else:
            lines.append(f"✅ 1年和5年Beta值接近，该股的性格比较稳定。")
    return "\n".join(lines)


# ═══════════════════════════════════════════
# 散点图（单只股票）
# ═══════════════════════════════════════════

def plot_beta_scatter(combined, beta, stock_name, code, bench_name, period, filepath):
    """画出收益率散点图和β回归线"""
    stock_ret = combined["stock"]
    bench_ret = combined["bench"]

    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    ax.scatter(bench_ret, stock_ret, alpha=0.5, s=25, c='#3B82F6',
               edgecolors='none', label='每日收益率')

    x_min, x_max = bench_ret.min(), bench_ret.max()
    x_pad = (x_max - x_min) * 0.15
    x_line = np.linspace(x_min - x_pad, x_max + x_pad, 200)
    y_line = beta * x_line
    ax.plot(x_line, y_line, color='#DC2626', linewidth=1.5, alpha=0.6,
            label=f'β = {beta:.3f}（回归线）', zorder=5)

    ax.plot(x_line, x_line, color='#D1D5DB', linewidth=1,
            linestyle='--', alpha=0.5, label='β = 1（与大盘同步）', zorder=3)

    ax.axhline(0, color='#E5E7EB', linewidth=0.5)
    ax.axvline(0, color='#E5E7EB', linewidth=0.5)

    beta_interpret = "高于大盘" if beta > 1 else "低于大盘" if beta < 1 else "与大盘持平"
    stats_lines = (
        f"* 数据点：{len(combined)} 个交易日\n"
        f"* β = {beta:.3f}\n"
        f"* {bench_name}涨 1% → 该股平均涨 {beta:.2f}%\n"
        f"* 结论：该股波动{beta_interpret}"
    )
    ax.text(0.96, 0.96, stats_lines, transform=ax.transAxes,
            fontsize=10, color='#374151', verticalalignment='top',
            horizontalalignment='right',
            bbox=dict(boxstyle='round,pad=0.7', facecolor='#F9FAFB',
                      edgecolor='#D1D5DB', alpha=0.92))

    ax.set_xlabel(f'{bench_name} 日收益率', color='#4B5563', fontsize=12, labelpad=10)
    ax.set_ylabel(f'{stock_name} 日收益率', color='#4B5563', fontsize=12, labelpad=10)
    ax.set_title(f'{stock_name}（{code}）β 散点图（{period} | 基准：{bench_name}）',
                 color='#111827', fontsize=16, fontweight='bold', pad=18)

    legend = ax.legend(frameon=True, facecolor='white', edgecolor='#D1D5DB',
                       labelcolor='#374151', fontsize=10,
                       loc='lower left', framealpha=0.9)

    ax.tick_params(colors='#4B5563', labelsize=9)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1%}"))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.1%}"))
    ax.margins(x=0.08, y=0.08)
    for spine in ax.spines.values():
        spine.set_visible(False)

    plt.tight_layout()
    plt.savefig(filepath, dpi=150, facecolor='white', bbox_inches='tight')
    plt.close()


# ═══════════════════════════════════════════
# β走势图（滚动窗口）
# ═══════════════════════════════════════════

def plot_rolling_beta(roll_beta, stock_name, code, bench_name, window, filepath):
    """画出β随时间变化的走势图"""
    fig, ax = plt.subplots(figsize=(14, 6))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    # β走势线
    ax.plot(roll_beta.index, roll_beta.values, color='#3B82F6', linewidth=1.5, alpha=0.8, label='滚动β')

    # β=1 参考线
    ax.axhline(y=1, color='#D1D5DB', linewidth=1, linestyle='--', alpha=0.6, label='β = 1')

    # 填充 β 与 1 之间的区域，便于观察偏离
    ax.fill_between(roll_beta.index, 1, roll_beta.values, alpha=0.1, color='#3B82F6')

    # 当前β值标注
    latest_beta = roll_beta.iloc[-1]
    ax.annotate(f'当前β = {latest_beta:.3f}',
                xy=(roll_beta.index[-1], latest_beta),
                xytext=(20, -10), textcoords='offset points',
                fontsize=10, color='#DC2626', fontweight='bold',
                arrowprops=dict(arrowstyle='->', color='#DC2626'))

    ax.set_xlabel('日期', color='#4B5563', fontsize=12, labelpad=10)
    ax.set_ylabel('β 值', color='#4B5563', fontsize=12, labelpad=10)
    ax.set_title(f'{stock_name}（{code}）滚动β走势（窗口={window}天 | 基准：{bench_name}）',
                 color='#111827', fontsize=15, fontweight='bold', pad=18)

    legend = ax.legend(frameon=True, facecolor='white', edgecolor='#D1D5DB',
                       labelcolor='#374151', fontsize=10, loc='upper right', framealpha=0.9)

    ax.tick_params(colors='#4B5563', labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(True, alpha=0.15, color='#D1D5DB')

    plt.tight_layout()
    plt.savefig(filepath, dpi=150, facecolor='white', bbox_inches='tight')
    plt.close()


# ── 合并滚动β走势图（所有股票在同一张图上） ──

def plot_combined_rolling(all_rolling, bench_name, bench_code, window, filepath):
    """所有股票β走势画在同一张图上"""
    if not all_rolling:
        return

    fig, ax = plt.subplots(figsize=(14, 7))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')

    for i, (name, roll_series) in enumerate(all_rolling):
        color = COLORS[i % len(COLORS)]
        ax.plot(roll_series.index, roll_series.values, color=color,
                linewidth=1.5, alpha=0.85, label=name)
        latest = roll_series.iloc[-1]
        ax.annotate(f'{latest:.2f}',
                    xy=(roll_series.index[-1], latest),
                    xytext=(8, 0), textcoords='offset points',
                    fontsize=9, color=color, fontweight='bold',
                    va='center')

    ax.axhline(y=1, color='#D1D5DB', linewidth=1, linestyle='--', alpha=0.6, label='β = 1')

    ax.set_xlabel('日期', color='#4B5563', fontsize=12, labelpad=10)
    ax.set_ylabel('β 值', color='#4B5563', fontsize=12, labelpad=10)
    ax.set_title(f'滚动β走势对比（窗口={window}天 | 基准：{bench_name}）',
                 color='#111827', fontsize=15, fontweight='bold', pad=18)

    legend = ax.legend(frameon=True, facecolor='white', edgecolor='#D1D5DB',
                       labelcolor='#374151', fontsize=9, loc='upper right', framealpha=0.9)

    ax.tick_params(colors='#4B5563', labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.grid(True, alpha=0.15, color='#D1D5DB')

    plt.tight_layout()
    plt.savefig(filepath, dpi=150, facecolor='white', bbox_inches='tight')
    plt.close()


# ── 合并散点图：多子图横向对比 ──

def plot_combined_scatter(all_data_list, bench_name, bench_code, filepath):
    """所有股票的散点图用多子图网格排布，共用X/Y范围"""
    if not all_data_list:
        return

    n = len(all_data_list)
    cols = min(3, n)
    rows = (n + cols - 1) // cols

    # 统一X/Y范围
    all_bench = pd.concat([d[3]["bench"] for d in all_data_list])
    all_stock = pd.concat([d[3]["stock"] for d in all_data_list])
    x_min, x_max = all_bench.min(), all_bench.max()
    y_min, y_max = all_stock.min(), all_stock.max()
    x_pad = (x_max - x_min) * 0.15
    y_pad = (y_max - y_min) * 0.15
    x_line = np.linspace(x_min - x_pad, x_max + x_pad, 200)

    fig, axes = plt.subplots(rows, cols, figsize=(16, 5 * rows))
    fig.patch.set_facecolor('white')

    # 展平 axes 便于遍历
    if rows == 1 and cols == 1:
        axes = [axes]
    else:
        axes = axes.flatten()

    for i, (name, code, beta, combined) in enumerate(all_data_list):
        ax = axes[i]
        color = COLORS[i % len(COLORS)]

        # 散点
        ax.scatter(combined["bench"], combined["stock"],
                   alpha=0.5, s=18, c=color, edgecolors='none', zorder=2)
        # β线
        y_line = beta * x_line
        ax.plot(x_line, y_line, color=color, linewidth=2,
                label=f'β = {beta:.3f}', zorder=5)
        # β=1参考线
        ax.plot(x_line, x_line, color='#D1D5DB', linewidth=1,
                linestyle='--', alpha=0.5, zorder=3)
        # 零点线
        ax.axhline(0, color='#E5E7EB', linewidth=0.5)
        ax.axvline(0, color='#E5E7EB', linewidth=0.5)

        # 标题
        ax.set_title(f'{name}', color='#111827', fontsize=12, fontweight='bold', pad=8)
        legend = ax.legend(frameon=True, facecolor='white', edgecolor='#D1D5DB',
                           labelcolor='#374151', fontsize=9, loc='lower left', framealpha=0.9)

        ax.set_xlim(x_min - x_pad, x_max + x_pad)
        ax.set_ylim(y_min - y_pad, y_max + y_pad)
        ax.tick_params(colors='#4B5563', labelsize=8)
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
        for spine in ax.spines.values():
            spine.set_visible(False)

    # 隐藏未使用的子图
    for j in range(i + 1, len(axes)):
        axes[j].set_visible(False)

    # 全局X/Y轴标签
    fig.text(0.5, 0.04, f'{bench_name} 日收益率', ha='center',
             color='#4B5563', fontsize=12, fontweight='bold')
    fig.text(0.04, 0.5, '各股票 日收益率', va='center', rotation='vertical',
             color='#4B5563', fontsize=12, fontweight='bold')
    fig.suptitle(f'β 散点图对比（基准：{bench_name}）',
                 color='#111827', fontsize=16, fontweight='bold', y=0.98)

    plt.tight_layout(rect=[0.05, 0.05, 1, 0.95])
    plt.savefig(filepath, dpi=150, facecolor='white', bbox_inches='tight')
    plt.close()


# ═══════════════════════════════════════════
# HTML报告生成
# ═══════════════════════════════════════════

def generate_html_report(results, bench_name, bench_code, output_path,
                         combined_scatter_path=None, combined_rolling_path=None):
    """生成包含所有分析结果的HTML报告"""
    rows_html = ""

    for r in results:
        beta_1y_str = f"{r['beta_1y']:.3f}" if r['beta_1y'] is not None else "数据不足"
        beta_5y_str = f"{r['beta_5y']:.3f}" if r['beta_5y'] is not None else "数据不足"
        risk_1y = risk_level(r['beta_1y']) if r['beta_1y'] is not None else "-"
        risk_5y = risk_level(r['beta_5y']) if r['beta_5y'] is not None else "-"

        rows_html += f"""
        <tr>
            <td>{r['name']}</td>
            <td class="mono">{r['code']}</td>
            <td class="num">{beta_1y_str}</td>
            <td>{risk_1y}</td>
            <td class="num">{beta_5y_str}</td>
            <td>{risk_5y}</td>
            <td class="mono">{r.get('streak_note', '—')}</td>
        </tr>"""

    # 合并图
    combined_scatter_html = ""
    combined_rolling_html = ""
    if combined_scatter_path and os.path.exists(combined_scatter_path):
        rel = os.path.relpath(combined_scatter_path, os.path.dirname(output_path))
        combined_scatter_html = f"""
            <div class="chart-card chart-card-wide">
                <img src="{rel}" alt="合并β回归线对比" class="chart-img">
            </div>"""
    if combined_rolling_path and os.path.exists(combined_rolling_path):
        rel = os.path.relpath(combined_rolling_path, os.path.dirname(output_path))
        combined_rolling_html = f"""
            <div class="chart-card chart-card-wide">
                <img src="{rel}" alt="合并β走势对比" class="chart-img">
            </div>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>A股 β 分析报告</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #f9fafb;
    color: #111827;
    font-family: -apple-system, 'PingFang SC', 'Inter', sans-serif;
    padding: 2rem;
}}
.container {{ max-width: 1200px; margin: 0 auto; }}
h1 {{ font-size: 1.8rem; font-weight: 700; margin-bottom: 0.3rem; }}
.subtitle {{ color: #6b7280; font-size: 0.9rem; margin-bottom: 2rem; }}
.report-date {{ float: right; color: #9ca3af; font-size: 0.85rem; }}
table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin-bottom: 2rem; }}
th {{ background: #f3f4f6; padding: 0.8rem 1rem; text-align: left; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; color: #6b7280; border-bottom: 1px solid #e5e7eb; }}
td {{ padding: 0.7rem 1rem; border-bottom: 1px solid #f3f4f6; font-size: 0.85rem; }}
tr:hover td {{ background: #f9fafb; }}
.mono {{ font-family: 'SF Mono', 'JetBrains Mono', monospace; }}
.num {{ text-align: right; font-family: 'SF Mono', 'JetBrains Mono', monospace; font-weight: 600; }}
.chart-card {{ background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); padding: 1.5rem; margin-bottom: 1.5rem; }}
.chart-card h3 {{ font-size: 1rem; font-weight: 600; margin-bottom: 1rem; color: #374151; }}
.chart-img {{ width: 100%; border-radius: 8px; }}
.bench-info {{ background: white; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); padding: 1rem 1.5rem; margin-bottom: 1.5rem; font-size: 0.9rem; color: #4b5563; }}
.bench-info strong {{ color: #111827; }}
.footer {{ text-align: center; color: #9ca3af; font-size: 0.8rem; margin-top: 3rem; }}
</style>
</head>
<body>
<div class="container">
    <h1>A股 β 分析报告 <span class="report-date">{datetime.now().strftime('%Y-%m-%d %H:%M')}</span></h1>
    <p class="subtitle">基于 yfinance 数据 · 基准指数：{bench_name}（{bench_code}）</p>

    <div class="bench-info">
        基准：<strong>{bench_name}（{bench_code}）</strong>
    </div>

    <table>
        <thead>
            <tr>
                <th>股票</th>
                <th>代码</th>
                <th>近1年 Beta</th>
                <th>风险等级</th>
                <th>近5年 Beta</th>
                <th>风险等级</th>
                <th>备注</th>
            </tr>
        </thead>
        <tbody>
            {rows_html}
        </tbody>
    </table>

    <h2 style="font-size:1.2rem; margin-bottom:1rem; color:#374151;">分析图</h2>
    {combined_scatter_html}
    {combined_rolling_html}

    <div class="footer">由 Hermes Beta Analyzer v2.0 生成</div>
</div>
</body>
</html>"""

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)
    return output_path


# ═══════════════════════════════════════════
# 单只股票分析
# ═══════════════════════════════════════════

def analyze_single(code, bench_code="000300.SS", bench_name="沪深300", do_rolling=True, rolling_window=60):
    """分析单只股票，返回结果字典"""
    name = get_stock_name(code)
    print(f"\n📊 {name}（{code}）β 分析")
    print("=" * 50)

    # 1年β
    beta_1y, days_1y, data_1y = calc_beta(code, bench_code, "1y")
    # 5年β
    beta_5y, days_5y, data_5y = calc_beta(code, bench_code, "5y")

    if beta_1y is not None:
        print(f"  近1年 Beta = {beta_1y:.3f}（基于 {days_1y} 个交易日）→ {risk_level(beta_1y)}")
    else:
        print("  近1年 Beta = 数据不足")
    if beta_5y is not None:
        print(f"  近5年 Beta = {beta_5y:.3f}（基于 {days_5y} 个交易日）→ {risk_level(beta_5y)}")
    else:
        print("  近5年 Beta = 数据不足")

    # 解读
    interp = interpret(beta_1y, beta_5y)
    if interp:
        print(f"\n  解读：{interp}")

    # 获取滚动β数据（供合并图使用）
    code_safe = code.replace(".", "_")
    roll_beta = None
    streak_note = ""
    if do_rolling and beta_1y is not None:
        roll_beta = calc_rolling_beta(code, bench_code, window=rolling_window, period="3y")
        if roll_beta is not None:
            roll_min = roll_beta.min()
            roll_max = roll_beta.max()
            roll_std = roll_beta.std()
            if roll_std > 0.2:
                streak_note = f"Beta波动较大（{roll_min:.2f}~{roll_max:.2f}）"
            else:
                streak_note = f"Beta相对稳定（{roll_min:.2f}~{roll_max:.2f}）"

    result = {
        "name": name,
        "code": code,
        "beta_1y": beta_1y,
        "beta_5y": beta_5y,
        "days_1y": days_1y,
        "days_5y": days_5y,
        "streak_note": streak_note,
        "roll_beta": roll_beta if do_rolling and roll_beta is not None else None,
        "data_1y": data_1y if beta_1y is not None else None,
    }
    return result


# ═══════════════════════════════════════════
# 批量对比输出
# ═══════════════════════════════════════════

def print_batch_summary(results):
    """终端输出批量对比表格"""
    print("\n" + "=" * 70)
    print("📊 批量β对比总览")
    print("=" * 70)
    print(f"{'股票':<20} {'代码':<14} {'近1年Beta':<12} {'风险':<8} {'近5年Beta':<12} {'风险':<8} {'备注':<20}")
    print("-" * 70)
    for r in results:
        b1 = f"{r['beta_1y']:.3f}" if r['beta_1y'] is not None else "—"
        b5 = f"{r['beta_5y']:.3f}" if r['beta_5y'] is not None else "—"
        r1 = risk_level(r['beta_1y']) if r['beta_1y'] is not None else "—"
        r5 = risk_level(r['beta_5y']) if r['beta_5y'] is not None else "—"
        note = r.get('streak_note', '—')
        name_show = r['name'][:18]
        print(f"{name_show:<20} {r['code']:<14} {b1:<10} {r1:<8} {b5:<10} {r5:<8} {note:<20}")


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="A股 β 分析工具 v2.0")
    parser.add_argument("codes", nargs="*", default=[], help="股票代码（如 300750.SZ），支持多个")
    parser.add_argument("--bench", default="000300.SS", help="基准指数代码（默认：沪深300 000300.SS）")
    parser.add_argument("--no-rolling", action="store_true", help="不生成滚动β走势图")
    parser.add_argument("--rolling-window", type=int, default=60, help="滚动β窗口天数（默认：60）")
    parser.add_argument("--no-html", action="store_true", help="不生成HTML报告")
    args = parser.parse_args()

    # 获取基准名称（硬编码常用指数，避免yfinance拉不到数据时显示代码本身）
    bench_code = args.bench
    bench_names = {
        "000300.SS": "沪深300",
        "000001.SS": "上证指数",
        "399001.SZ": "深证成指",
        "399006.SZ": "创业板指",
        "000688.SS": "科创50",
        "000016.SS": "上证50",
        "000905.SS": "中证500",
    }
    bench_name = bench_names.get(bench_code, get_stock_name(bench_code))

    # 确定股票列表
    if args.codes:
        codes = args.codes
    else:
        codes = ["300750.SZ"]
        print("提示：未输入股票代码，默认分析宁德时代")
        print("用法：python beta_analyzer.py 代码1 代码2 ... [--bench 基准代码] [--no-rolling] [--no-html]")

    print(f"\n📊 A股 Beta 分析工具 v2.0")
    print(f"基准指数：{bench_name}（{bench_code}）")
    print(f"股票数量：{len(codes)} 只")
    print("=" * 50)

    # 逐个分析
    results = []
    for code in codes:
        result = analyze_single(
            code,
            bench_code=bench_code,
            bench_name=bench_name,
            do_rolling=not args.no_rolling,
            rolling_window=args.rolling_window,
        )
        results.append(result)

    # 批量对比
    if len(results) > 1:
        print_batch_summary(results)
    elif len(results) == 1:
        r = results[0]
        print(f"\n{'='*50}")
        print(f"📊 {r['name']}（{r['code']}）分析完成")
        print(f"  近1年 Beta = {r['beta_1y']:.3f}" if r['beta_1y'] is not None else "  近1年 Beta = 数据不足")
        print(f"  近5年 Beta = {r['beta_5y']:.3f}" if r['beta_5y'] is not None else "  近5年 Beta = 数据不足")

    # 生成HTML报告
    if not args.no_html:
        # 时间戳：每次运行独立命名
        timestamp = datetime.now().strftime("_%Y%m%d_%H%M%S")
        batch_tag = timestamp

        combined_scatter_path = None
        combined_rolling_path = None

        # 多只股票 → 合并图
        if len(results) > 1 and not args.no_rolling:
            all_rolling = []
            for r in results:
                if r.get("roll_beta") is not None:
                    all_rolling.append((r["name"], r["roll_beta"]))
            if len(all_rolling) >= 2:
                combined_rolling_path = os.path.join(OUTPUT_DIR, f"combined_rolling_beta{batch_tag}.png")
                plot_combined_rolling(all_rolling, bench_name, bench_code, args.rolling_window, combined_rolling_path)
                print(f"  📈 合并β走势图 → {combined_rolling_path}")

        if len(results) > 1:
            all_data = []
            for r in results:
                if r.get("data_1y") is not None and r.get("beta_1y") is not None:
                    all_data.append((r["name"], r["code"], r["beta_1y"], r["data_1y"]))
            if len(all_data) >= 2:
                combined_scatter_path = os.path.join(OUTPUT_DIR, f"combined_scatter{batch_tag}.png")
                plot_combined_scatter(all_data, bench_name, bench_code, combined_scatter_path)
                print(f"  📈 合并散点图 → {combined_scatter_path}")

        # 单只股票 → 个股散点图 + 个股β走势图
        if len(results) == 1:
            r = results[0]
            code_safe = r['code'].replace('.', '_')
            if r.get("data_1y") is not None and r.get("beta_1y") is not None:
                scatter_path = os.path.join(OUTPUT_DIR, f"{code_safe}_scatter_1y{batch_tag}.png")
                plot_beta_scatter(r["data_1y"], r["beta_1y"], r["name"], r["code"], bench_name, "近1年", scatter_path)
                combined_scatter_path = scatter_path
            if not args.no_rolling and r.get("roll_beta") is not None:
                rolling_path = os.path.join(OUTPUT_DIR, f"{code_safe}_rolling_beta{batch_tag}.png")
                plot_rolling_beta(r["roll_beta"], r["name"], r["code"], bench_name, args.rolling_window, rolling_path)
                combined_rolling_path = rolling_path

        # HTML报告：带时间戳 + 同时保留一份 latest 覆盖（方便快速打开）
        html_timestamp = os.path.join(OUTPUT_DIR, f"beta_report{batch_tag}.html")
        html_latest = os.path.join(OUTPUT_DIR, "beta_report.html")
        generate_html_report(results, bench_name, bench_code, html_timestamp,
                             combined_scatter_path=combined_scatter_path,
                             combined_rolling_path=combined_rolling_path)
        print(f"📄 HTML报告 → {html_timestamp}")
        # 也生成一份 latest 覆盖（始终指向最近一次运行）
        generate_html_report(results, bench_name, bench_code, html_latest,
                             combined_scatter_path=combined_scatter_path,
                             combined_rolling_path=combined_rolling_path)
        print(f"📄 最新报告 → {html_latest}")


if __name__ == "__main__":
    main()
