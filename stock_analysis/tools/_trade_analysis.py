#!/usr/bin/env python3
"""交易数据分析 - 从 Table.xls2026.5.25 生成报告"""
import re, json
from collections import defaultdict
from pathlib import Path

with open('D:/1989n/stock_data/Table.xls2026.5.25', 'rb') as f:
    text = f.read().decode('gbk')

trades = []
for line in text.strip().split('\n'):
    line = line.strip()
    if not line or line.startswith('成交日期') or line.startswith('汇总'):
        continue
    fields = line.split('\t')
    if len(fields) < 8:
        continue
    code_match = re.search(r'"(\d+)"', fields[1])
    code = code_match.group(1) if code_match else fields[1].strip()
    trades.append({
        'date': fields[0].strip(), 'code': code,
        'direction': '买入' if '买入' in fields[3] else '卖出',
        'qty': int(fields[4]), 'price': float(fields[5]), 'amount': float(fields[6]),
    })

# 今天(05-25)的交易补充
today = [
    {'code':'002156','direction':'卖出','qty':300,'price':69.277,'amount':20783},
    {'code':'300136','direction':'卖出','qty':400,'price':119.282,'amount':47713},
    {'code':'002077','direction':'卖出','qty':800,'price':18.96,'amount':15168},
    {'code':'002050','direction':'买入','qty':300,'price':53.83,'amount':16149},
    {'code':'600183','direction':'买入','qty':400,'price':114.145,'amount':45658},
]
trades.extend(today)

names = {
    '002156':'通富微电','300136':'信维通信','600498':'烽火通信',
    '002077':'大港股份','300058':'蓝色光标','002050':'三花智控',
    '600183':'生益科技','000062':'深圳华强','000815':'美利云',
    '000981':'山子高科','002208':'合肥城建','002261':'拓维信息',
    '002328':'新朋股份','002407':'多氟多','002565':'顺灏股份',
    '002866':'传艺科技','300339':'润和软件','300342':'天银机电',
    '300480':'光力科技','300739':'明阳电路','300766':'每日互动',
    '300785':'值得买','300792':'壹网壹创','600236':'桂冠电力',
    '600860':'京城股份','601789':'宁波建工','603278':'大业股份',
}
for t in trades:
    if t['code'] in names:
        t['name'] = names[t['code']]
    else:
        t['name'] = t['code']

# 按股票汇总
by_stock = defaultdict(lambda: {'name':'','bqty':0,'bamt':0,'sqty':0,'samt':0})
for t in trades:
    s = by_stock[t['code']]
    s['name'] = t['name']
    if t['direction'] == '买入':
        s['bqty'] += t['qty']; s['bamt'] += t['amount']
    else:
        s['sqty'] += t['qty']; s['samt'] += t['amount']

# 当前市价
cp = {'002156':69.78,'300136':118.67,'600498':54.93,
      '002077':18.96,'300058':16.78,'002050':53.85,'600183':114.15}
held = ['002156','300136','600498','002077','300058','002050','600183']

print('='*60)
print('  2026.04.27 - 2026.05.25 交易分析')
print('='*60)
print()

# ── 一、已清仓股票 ──
print('一、已清仓股票(已实现盈亏)')
print()
realized = 0
for code, s in sorted(by_stock.items()):
    if code in held or s['bqty']==0 or s['sqty']==0 or s['bqty']!=s['sqty']:
        continue
    pnl = s['samt'] - s['bamt']
    pct = pnl/s['bamt']*100
    realized += pnl
    sign = '+' if pnl >= 0 else ''
    print(f'  {s["name"]:4s}({code}) {sign}{pnl:.0f}元({pct:+.1f}%)')

# 净卖出(有持仓继承的)
for code, s in sorted(by_stock.items()):
    if code in held or s['bqty']==0:
        continue
    if s['sqty'] > s['bqty']:
        pnl = s['samt'] - s['bamt']
        realized += pnl
        sign = '+' if pnl >= 0 else ''
        print(f'  {s["name"]:4s}({code}) {sign}{pnl:.0f}元(净卖{s["sqty"]-s["bqty"]}股)')

print(f'  合计: {realized:+.0f}元')
print()

# ── 二、持仓股票 ──
print('二、持仓股票(总盈亏=已回收+持仓市值-总投入)')
print()
ti, tr, tc = 0, 0, 0
for code in held:
    s = by_stock[code]
    inv = s['bamt']
    rec = s['samt']
    rem = s['bqty'] - s['sqty']
    cur_v = rem * cp.get(code, 0)
    ti += inv; tr += rec; tc += cur_v
    tp = rec + cur_v - inv
    tpp = tp/inv*100 if inv > 0 else 0
    sign = '+' if tp >= 0 else ''
    print(f'  {s["name"]:4s} | 投{inv:>7.0f} | 收{rec:>7.0f} | 持{rem:>3}股 | 值{cur_v:>7.0f} | {sign}{tp:.0f}元({tpp:+.1f}%)')

total = tc + tr - ti
total_pct = total/ti*100 if ti > 0 else 0
print(f'  {"-"*50}')
print(f'  总投{ti:.0f} | 已收{tr:.0f} | 持仓{tc:.0f} | 总{total:+.0f}元({total_pct:+.1f}%)')
print()

# ── 三、亏损分析 ──
print('三、亏损分析')
print()
losses = []
for code, s in sorted(by_stock.items()):
    if s['bqty'] == 0:
        continue
    if code in held:
        avg = s['bamt']/s['bqty']
        rem = s['bqty']-s['sqty']
        pnl = s['samt'] + rem*cp.get(code,0) - s['bamt']
        pct = pnl/s['bamt']*100
    else:
        pnl = s['samt'] - s['bamt']
        pct = pnl/s['bamt']*100 if s['bqty']>0 else 0
    if pnl < -500:
        losses.append((pnl, code, s, pct))

losses.sort()
for pnl, code, s, pct in losses:
    name = s['name']
    avg_buy = s['bamt']/s['bqty'] if s['bqty']>0 else 0
    avg_sell = s['samt']/s['sqty'] if s['sqty']>0 else 0
    print(f'  {name}({code}): {pnl:.0f}元({pct:.1f}%)')
    if code in held:
        rem = s['bqty']-s['sqty']
        print(f'    买{s["bqty"]}股@{avg_buy:.2f} 卖{s["sqty"]}股@{avg_sell:.2f} 持{rem}股')
        print(f'    投入{s["bamt"]:.0f} 已回收{s["samt"]:.0f} 剩余市值{rem*cp.get(code,0):.0f}')
        if avg_sell > 0:
            print(f'    已卖部分盈亏:{s["samt"]-s["sqty"]*avg_buy:.0f}元')
    else:
        print(f'    买{s["bqty"]}股@{avg_buy:.2f} 卖{s["sqty"]}股@{avg_sell:.2f}')
        print(f'    亏损绝对值:{abs(pnl):.0f}元')
    print()

# ── 四、盈利分析 ──
print('四、盈利分析')
print()
gains = []
for code, s in sorted(by_stock.items()):
    if s['bqty']==0 or s['sqty']==0:
        continue
    if code in held:
        avg_buy = s['bamt']/s['bqty']
        pnl = s['samt'] - s['sqty']*avg_buy
    else:
        pnl = s['samt'] - s['bamt']
    if pnl > 500:
        gains.append((pnl, code, s))

gains.sort(reverse=True)
for pnl, code, s in gains[:5]:
    name = s['name']
    avg_buy = s['bamt']/s['bqty'] if s['bqty']>0 else 0
    avg_sell = s['samt']/s['sqty'] if s['sqty']>0 else 0
    ret = pnl/(s['sqty']*avg_buy)*100 if s['sqty']>0 and avg_buy>0 else 0
    print(f'  {name}: +{pnl:.0f}元')
    print(f'    买{s["bqty"]}股@{avg_buy:.2f} 卖{s["sqty"]}股@{avg_sell:.2f}')
    print(f'    回报率:{ret:.1f}% | 盈利额:{pnl:.0f}元')
    print()

# ── 五、门禁自验 ──
print('五、一致性门禁自验')
print()
import subprocess, sys as _sys
result = subprocess.run(
    [_sys.executable, 'tools/consistency_gate.py'],
    capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent,
)
print(result.stdout.strip() if result.stdout else result.stderr.strip())
if result.returncode != 0:
    print('  ⚠ 门禁发现异常，请检查上方报告')
else:
    print('  ✓ 门禁全部通过')
print()
