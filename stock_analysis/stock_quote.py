"""
stock_quote.py — 多源行情工具 v2.0
通道: 新浪(实时) + 腾讯(实时) + 搜狐(K线) + CLS(新闻经由morning_brief.py)
东方财富WAF封锁不影响本工具。

用法:
  python stock_quote.py check                        # 所有持仓盈亏
  python stock_quote.py quote 000062 002156          # 指定股票行情
  python stock_quote.py kline 000062 --days 60       # K线
  python stock_quote.py sources                      # 测试所有数据源
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

HEADERS = {"Referer": "https://finance.sina.com.cn"}

# ── 辅助 ─────────────────────────────────────────

def to_sina(code):
    c = code.strip().lower()
    if c.startswith(('sh', 'sz')): return c
    if c.startswith(('60', '68', '90', '9')): return f"sh{c}"
    return f"sz{c}"

def to_sohu(code):
    c = code.strip()
    if c.startswith(('60', '68')): return f"cn_{c}"
    return f"cn_{c}"

def fetch(url, headers=None, timeout=10, encoding='gbk'):
    req = urllib.request.Request(url, headers=headers or HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(encoding, errors='replace')
    except Exception:
        return None

# ── 通道1: 新浪 实时行情 ─────────────────────────

def sina_quotes(codes):
    url = f"https://hq.sinajs.cn/list={','.join([to_sina(c) for c in codes])}"
    resp = fetch(url)
    if not resp: return {}
    result = {}
    for line in resp.strip().split('\n'):
        try:
            if '=' not in line: continue
            d = line.split('"')[1].split(',')
            num = ''.join(c for c in line.split('=')[0].split('_')[-1] if c.isdigit())
            result[num] = {
                'name': d[0], 'open': float(d[1]), 'prev_close': float(d[2]),
                'current': float(d[3]), 'high': float(d[4]), 'low': float(d[5]),
                'volume': int(d[8]) if d[8] else 0, 'amount': float(d[9]) if d[9] else 0,
                'time': d[30] if len(d) > 30 else '',
                'change_pct': round((float(d[3]) - float(d[2])) / float(d[2]) * 100, 2) if float(d[2]) > 0 else 0
            }
        except: continue
    return result

# ── 通道2: 腾讯 实时行情 ─────────────────────────

def tencent_quotes(codes):
    url = f"https://web.sqt.gtimg.cn/q={','.join([to_sina(c) for c in codes])}"
    resp = fetch(url)
    if not resp: return {}
    result = {}
    for line in resp.strip().split('\n'):
        try:
            if '=' not in line: continue
            d = line.split('"')[1].split('~')
            if len(d) < 40: continue
            num = ''.join(c for c in d[2] if c.isdigit())
            result[num] = {
                'name': d[1], 'current': float(d[3]) if d[3] else 0,
                'prev_close': float(d[4]) if d[4] else 0,
                'open': float(d[5]) if d[5] else 0,
                'high': float(d[33]) if len(d) > 33 and d[33] else 0,
                'low': float(d[34]) if len(d) > 34 and d[34] else 0,
                'volume': int(float(d[6]) * 100) if d[6] else 0,
                'amount': float(d[37]) if len(d) > 37 and d[37] else 0,
                'change_pct': float(d[32]) if len(d) > 32 and d[32] else 0,
                'time': d[33] if len(d) > 33 else '',
            }
        except: continue
    return result

# ── 通道3: 搜狐 K线 ──────────────────────────────

def sohu_kline(code, days=60):
    """返回 [{date, open, close, high, low, volume, change_pct}, ...]"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days + 5)).strftime('%Y%m%d')
    url = f"https://q.stock.sohu.com/hisHq?code={to_sohu(code)}&start={start}&end={end}"
    resp = fetch(url, encoding='utf-8')
    if not resp: return None
    try:
        data = json.loads(resp)
        if not data or 'hq' not in data[0]: return None
        bars = []
        for row in data[0]['hq']:
            bars.append({
                'date': row[0], 'open': float(row[1]), 'close': float(row[2]),
                'change': float(row[3]), 'change_pct': row[4],
                'low': float(row[5]), 'high': float(row[6]),
                'volume': int(row[7]) if row[7] else 0,
                'amount': float(row[8]) if row[8] else 0,
            })
        return bars
    except: return None

# ── 混合行情（新浪主用 → 腾讯备用） ────────────

def get_quotes(codes):
    q = sina_quotes(codes)
    missing = [c for c in codes if c not in q]
    if missing:
        q2 = tencent_quotes(missing)
        q.update(q2)
    return q

# ── 持仓配置 ─────────────────────────────────────

def _load_portfolio():
    """从 portfolio.json 加载持仓，避免硬编码成本数据不同步。"""
    import json
    from pathlib import Path
    p = Path(__file__).parent / "data" / "portfolio.json"
    if not p.exists():
        print(f"[WARN] {p} 不存在，使用空持仓")
        return {}
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    return {
        item["code"]: {
            "cost": item["cost"],
            "shares": item["shares"],
            "name": item["name"],
        }
        for item in data.get("holdings", [])
    }

PORTFOLIO = _load_portfolio()

# ── 命令实现 ─────────────────────────────────────

def cmd_quote(args):
    codes = args if args else list(PORTFOLIO.keys())
    q = get_quotes(codes)
    if not q: print('{"error": "所有行情源均不可用"}'); return
    pf = {k: v for k, v in PORTFOLIO.items() if k in q}
    if pf and all(k in q for k in pf):
        total_cost = sum(v['cost'] * v['shares'] for v in pf.values())
        total_mkt = sum(q[k]['current'] * pf[k]['shares'] for k in pf)
        items = [{
            'code': k, 'name': pf[k]['name'],
            'cost': pf[k]['cost'], 'current': q[k]['current'],
            'pnl_pct': round((q[k]['current'] - pf[k]['cost']) / pf[k]['cost'] * 100, 2),
            'pnl_amount': round((q[k]['current'] - pf[k]['cost']) * pf[k]['shares'], 2),
            'market_value': round(q[k]['current'] * pf[k]['shares'], 2),
            'shares': pf[k]['shares'],
            'change_pct': q[k]['change_pct'],
        } for k in sorted(pf.keys())]
        print(json.dumps({
            'time': datetime.now().strftime('%H:%M:%S'),
            'results': items,
            'total_cost': round(total_cost, 2),
            'total_market': round(total_mkt, 2),
            'total_pnl': round(total_mkt - total_cost, 2),
            'total_pnl_pct': round((total_mkt - total_cost) / total_cost * 100, 2),
        }, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(list(q.values()), ensure_ascii=False, indent=2))

def cmd_check(args):
    q = get_quotes(list(PORTFOLIO.keys()))
    if not q: print("⚠ 所有行情源均不可用"); return
    now = datetime.now().strftime('%H:%M:%S')
    total_cost = total_mkt = 0
    print(f"\n=== 持仓检查 | {now} ===")
    print(f"{'代码':<8} {'名称':<10} {'成本':>8} {'现价':>8} {'盈亏%':>8} {'浮盈':>10} {'市值':>10}")
    print("-" * 65)
    for code in sorted(PORTFOLIO.keys()):
        p = PORTFOLIO[code]; qd = q.get(code)
        if not qd: continue
        pnl = round((qd['current'] - p['cost']) / p['cost'] * 100, 2)
        amt = round((qd['current'] - p['cost']) * p['shares'], 2)
        mkv = round(qd['current'] * p['shares'], 2)
        total_cost += p['cost'] * p['shares']
        total_mkt += mkv
        flag = " 🔥" if pnl > 10 else " ⬆" if pnl > 5 else " ⚠" if pnl < -3 else " ▼" if pnl < 0 else ""
        print(f"{code:<8} {p['name']:<10} {p['cost']:>8.2f} {qd['current']:>8.2f} {pnl:>7.2f}% {amt:>10.2f} {mkv:>10.2f}{flag}")
    print("-" * 65)
    total_pnl = total_mkt - total_cost
    print(f"总成本 {total_cost:>10.2f} | 总市值 {total_mkt:>10.2f} | 总盈亏 {total_pnl:>+10.2f} ({total_pnl/total_cost*100:>+.2f}%)")
    print(f"数据源: 新浪(主) + 腾讯(备)\n")

def cmd_kline(args):
    if not args: print("用法: python stock_quote.py kline CODE [--days N]"); return
    code = args[0]; days = 60
    if '--days' in args:
        idx = args.index('--days')
        if idx + 1 < len(args): days = int(args[idx + 1])
    bars = sohu_kline(code, days)
    if not bars: print(f"⚠ {code} K线获取失败"); return
    print(f"\n=== {code} K线(近{days}天) | 搜狐源 ===")
    print(f"{'日期':<12} {'开盘':>8} {'收盘':>8} {'最高':>8} {'最低':>8} {'涨跌幅':>8} {'成交量':>10}")
    print("-" * 62)
    for b in bars[-30:]:  # 显示最近30条
        print(f"{b['date']:<12} {b['open']:>8.2f} {b['close']:>8.2f} {b['high']:>8.2f} {b['low']:>8.2f} {b['change_pct']:>8} {b['volume']:>10}")
    print(f"\n... 共 {len(bars)} 条记录\n")

def cmd_sources(args):
    code = args[0] if args else '002156'
    print(f"\n=== 数据源诊断 | {code} ===\n")
    for name, fn in [('新浪实时', lambda: sina_quotes([code])), ('腾讯实时', lambda: tencent_quotes([code]))]:
        try:
            q = fn()
            if q and code in q:
                print(f"  ✅ {name}: 现价 {q[code]['current']} ({q[code].get('name','')})")
            else:
                print(f"  ❌ {name}: 无数据")
        except Exception as e:
            print(f"  ❌ {name}: {e}")
    try:
        k = sohu_kline(code, 5)
        if k: print(f"  ✅ 搜狐K线: 最近 {k[0]['date']} 收{k[0]['close']}")
        else: print(f"  ❌ 搜狐K线: 无数据")
    except Exception as e:
        print(f"  ❌ 搜狐K线: {e}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python stock_quote.py <check|quote|kline|sources> [codes...]")
        sys.exit(1)
    mode = sys.argv[1]; args = sys.argv[2:]
    {'check': cmd_check, 'quote': cmd_quote, 'kline': cmd_kline, 'sources': cmd_sources}.get(mode, lambda _: print(f"未知模式: {mode}"))(args)
