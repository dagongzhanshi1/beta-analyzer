# A股 Beta 分析工具

计算A股个股相对于基准指数（默认沪深300）的 Beta（贝塔）系数，评估系统性风险。支持单只股票分析和多只批量对比。

---

## 功能

- **单只股票分析** — 输入股票代码，输出近1年/近5年Beta、风险等级、走势解读
- **批量对比** — 同时输入多只股票，输出对比表格
- **散点图** — 收益率散点图 + Beta回归线
- **滚动Beta走势图** — 60天滑动窗口，观察Beta随时间的变化趋势
- **自定义基准指数** — 可指定沪深300、上证指数、创业板指等作为基准
- **HTML报告** — 自动生成可视化报告，在浏览器中查看

---

## 快速开始

```bash
# 安装依赖
pip install yfinance pandas numpy matplotlib requests

# 单只股票分析
python beta_analyzer.py 600258.SS

# 多只股票对比
python beta_analyzer.py 600258.SS 600754.SS 300750.SZ

# 指定基准指数（默认沪深300）
python beta_analyzer.py 300750.SZ --bench 399006.SZ
```

---

## 命令行参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `codes` | 股票代码（支持多个） | `300750.SZ` |
| `--bench` | 基准指数代码 | `000300.SS`（沪深300） |
| `--no-rolling` | 不生成滚动Beta走势图 | 生成 |
| `--rolling-window` | 滚动窗口天数 | `60` |
| `--no-html` | 不生成HTML报告 | 生成 |

### 支持的基准指数

| 代码 | 名称 |
|---|---|
| `000300.SS` | 沪深300 |
| `000001.SS` | 上证指数 |
| `399001.SZ` | 深证成指 |
| `399006.SZ` | 创业板指 |
| `000688.SS` | 科创50 |
| `000016.SS` | 上证50 |
| `000905.SS` | 中证500 |

---

## 输出

所有输出文件保存在 `output/` 目录：

```
output/
  ├── beta_report.html         # HTML分析报告
  ├── combined_scatter.png     # 批量模式：合并散点图
  ├── combined_rolling_beta.png # 批量模式：合并走势图
  ├── 600258_SS_scatter_1y.png  # 单只模式：个股散点图
  └── 600258_SS_rolling_beta.png # 单只模式：个股走势图
```

---

## 示例

```bash
# 分析首旅酒店
python beta_analyzer.py 600258.SS

# 对比首旅酒店 vs 锦江酒店 vs 宁德时代
python beta_analyzer.py 600258.SS 600754.SS 300750.SZ

# 以创业板指为基准分析宁德时代
python beta_analyzer.py 300750.SZ --bench 399006.SZ
```

---

## 数据来源

- 股票价格数据：Yahoo Finance（`yfinance`）
- 股票名称（备用）：东方财富 API

---

## 环境要求

- Python 3.8+
- macOS / Linux / Windows
- 需要网络连接（拉取股票数据）
