"""
data_source_router.py — 多源行情路由 v1.1
========================================
自动检测可用数据通道，提供统一行情接口。所有任务通过此模块获取数据。
设计原则: 无单点故障，每个接口至少有两个独立通道。

通道实测状态 (2026-05-16):
  ✅ TDX (实时A股个股) — pytdx 直连通达信行情服务器 (主通道)
  ✅ 新浪 (实时A股个股+指数) — hq.sinajs.cn
  ✅ 腾讯 (实时A股个股+指数) — web.sqt.gtimg.cn
  ✅ 搜狐 (K线) — q.stock.sohu.com
  ❌ 东方财富 (全部接口) — WAF封锁, 自动跳过

用法:
  from data_source_router import get_quotes, get_index_quotes, sohu_kline, check_channels
  q = get_quotes(['000062', '002156'])
  indices = get_index_quotes()
  kline = sohu_kline('002156', 60)
  status = check_channels()
"""
import json
import logging
import urllib.request
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("data_source_router")

# ── TDX 实时行情 (直连通达信服务器, 主通道) ──
try:
    from market_pool.fetcher import fetch_quotes_tdx
    _HAS_TDX = True
except ImportError:
    _HAS_TDX = False
    logger.warning("TDX实时行情不可用 (market_pool.fetcher 未找到)")

# ── Headers ──
SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}
TENCENT_HEADERS = {"Referer": "https://stock.finance.qq.com"}


# ── 底层HTTP ──

def _fetch(url, headers, timeout=10, encoding='gbk'):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode(encoding, errors='replace')
    except Exception as e:
        logger.debug("Fetch failed: %s — %s", url[:60], e)
        return None


def _prefix(code):
    """A股个股交易所前缀: 60/68/90/9开头=上海, 其余=深圳"""
    c = code.strip()
    if c.startswith(('60', '68', '90', '9')):
        return 'sh'
    return 'sz'


def _index_prefix(code):
    """A股指数前缀: 00开头=上海, 39/30开头=深圳"""
    c = code.strip()
    if c.startswith('00'):
        return 'sh'
    return 'sz'


# ═══════════════════════════════════════════
# 通道1: 新浪 实时行情 (A股个股)
# ═══════════════════════════════════════════

def sina_quotes(codes: list[str]) -> dict:
    """通过新浪批量获取个股实时行情。
    返回 {code: {name, current, prev_close, change_pct, high, low, volume, amount, time, source}}"""
    if not codes:
        return {}
    url = f"https://hq.sinajs.cn/list={','.join(f'{_prefix(c)}{c}' for c in codes)}"
    resp = _fetch(url, SINA_HEADERS, encoding='gbk')
    if not resp:
        return {}
    result = {}
    for line in resp.strip().split('\n'):
        try:
            if '=' not in line:
                continue
            d = line.split('"')[1].split(',')
            num = ''.join(c for c in line.split('=')[0].split('_')[-1] if c.isdigit())
            if not num or len(d) < 32:
                continue
            prev_close = float(d[2]) if d[2] else 0
            current = float(d[3]) if d[3] else 0
            result[num] = {
                'name': d[0],
                'open': float(d[1]) if d[1] else 0,
                'prev_close': prev_close,
                'current': current,
                'high': float(d[4]) if d[4] else 0,
                'low': float(d[5]) if d[5] else 0,
                'volume': int(d[8]) if d[8] else 0,
                'amount': float(d[9]) if d[9] else 0,
                'time': d[30] if len(d) > 30 else '',
                'change_pct': round((current - prev_close) / prev_close * 100, 2) if prev_close else 0,
                'source': 'sina',
            }
        except Exception:
            continue
    return result


def sina_index_quotes(codes: list[str]) -> dict:
    """通过新浪获取指数行情。
    指数代码格式: 000001(上证), 399001(深证) — 纯数字, 不加前缀。
    返回 {code: {name, current, prev_close, change_pct, ...}}"""
    if not codes:
        return {}
    mapped = [f"{_index_prefix(c)}{c}" for c in codes]
    url = f"https://hq.sinajs.cn/list={','.join(mapped)}"
    resp = _fetch(url, SINA_HEADERS, encoding='gbk')
    if not resp:
        return {}
    result = {}
    for line in resp.strip().split('\n'):
        try:
            if '=' not in line:
                continue
            d = line.split('"')[1].split(',')
            num = ''.join(c for c in line.split('=')[0].split('_')[-1] if c.isdigit())
            if not num or len(d) < 6:
                continue
            prev_close = float(d[2]) if d[2] else 0
            current = float(d[3]) if d[3] else 0
            result[num] = {
                'name': d[0],
                'current': current,
                'prev_close': prev_close,
                'high': float(d[4]) if d[4] else 0,
                'low': float(d[5]) if d[5] else 0,
                'volume': int(d[8]) if d[8] else 0,
                'amount': float(d[9]) if d[9] else 0,
                'change_pct': round((current - prev_close) / prev_close * 100, 2) if prev_close else 0,
                'source': 'sina',
            }
        except Exception:
            continue
    return result


# ═══════════════════════════════════════════
# 通道2: 腾讯 实时行情 (A股个股+指数)
# ═══════════════════════════════════════════

def tencent_quotes(codes: list[str]) -> dict:
    """通过腾讯批量获取实时行情 (个股+指数通用)。
    返回 {code: {name, current, prev_close, change_pct, high, low, volume, amount, time, source}}"""
    if not codes:
        return {}
    url = f"https://web.sqt.gtimg.cn/q={','.join(f'{_prefix(c)}{c}' for c in codes)}"
    resp = _fetch(url, TENCENT_HEADERS, encoding='utf-8')
    if not resp:
        return {}
    result = {}
    for line in resp.strip().split('\n'):
        try:
            if '=' not in line:
                continue
            d = line.split('"')[1].split('~')
            if len(d) < 40:
                continue
            num = ''.join(c for c in d[2] if c.isdigit())
            if not num:
                continue
            result[num] = {
                'name': d[1],
                'current': float(d[3]) if d[3] else 0,
                'prev_close': float(d[4]) if d[4] else 0,
                'open': float(d[5]) if d[5] else 0,
                'high': float(d[33]) if len(d) > 33 and d[33] else 0,
                'low': float(d[34]) if len(d) > 34 and d[34] else 0,
                'volume': int(float(d[6]) * 100) if d[6] else 0,
                'amount': float(d[37]) if len(d) > 37 and d[37] else 0,
                'change_pct': float(d[32]) if len(d) > 32 and d[32] else 0,
                'time': d[30] if len(d) > 30 else '',
                'source': 'tencent',
            }
        except Exception:
            continue
    return result


# ═══════════════════════════════════════════
# 通道3: 搜狐 K线
# ═══════════════════════════════════════════

def sohu_kline(code: str, days: int = 60) -> Optional[list]:
    """获取个股K线数据 (日频)。
    返回 [{date, open, close, high, low, volume, amount, change_pct}, ...]
    或 None (失败时)。"""
    end = datetime.now().strftime('%Y%m%d')
    start = (datetime.now() - timedelta(days=days + 5)).strftime('%Y%m%d')
    url = f"https://q.stock.sohu.com/hisHq?code=cn_{code}&start={start}&end={end}"
    resp = _fetch(url, {}, encoding='utf-8')
    if not resp:
        return None
    try:
        data = json.loads(resp)
        if not data or 'hq' not in data[0]:
            return None
        bars = []
        for row in data[0]['hq']:
            bars.append({
                'date': row[0],
                'open': float(row[1]),
                'close': float(row[2]),
                'change': float(row[3]),
                'change_pct': row[4],
                'low': float(row[5]),
                'high': float(row[6]),
                'volume': int(row[7]) if row[7] else 0,
                'amount': float(row[8]) if row[8] else 0,
            })
        return bars
    except Exception:
        return None


# ═══════════════════════════════════════════
# 统一接口
# ═══════════════════════════════════════════

A_INDICES = [
    ('000001', '上证指数'),
    ('399001', '深证成指'),
    ('399006', '创业板指'),
    ('000688', '科创50'),
]

EASTMONEY_BLOCKED = True  # 2026-05 WAF封锁, 恢复后设为False


def get_quotes(codes: list[str]) -> dict:
    """获取个股实时行情。TDX(主) → 新浪 → 腾讯, 逐级回退。
    返回 {code: {name, current, change_pct, ...}}"""
    if not codes:
        return {}
    result = {}
    if _HAS_TDX:
        result = fetch_quotes_tdx(codes)
    missing = [c for c in codes if c not in result]
    if missing:
        q2 = sina_quotes(missing)
        result.update(q2)
    still_missing = [c for c in codes if c not in result]
    if still_missing:
        logger.info("Sina missing %d codes, Tencent fallback", len(still_missing))
        result.update(tencent_quotes(still_missing))
    return result


def get_index_quotes() -> list[dict]:
    """获取A股主要指数行情。
    返回 [{name, code, price, change_pct, source}, ...]"""
    codes = [c for c, _ in A_INDICES]
    q = sina_index_quotes(codes)
    missing = [c for c in codes if c not in q]
    if missing:
        logger.info("Index: Sina missing %d, Tencent fallback", len(missing))
        # Tencent for indices needs correct prefix (not stock _prefix)
        tc_codes = [f"{_index_prefix(c)}{c}" for c in missing]
        url = f"https://web.sqt.gtimg.cn/q={','.join(tc_codes)}"
        resp = _fetch(url, TENCENT_HEADERS, encoding='utf-8')
        if resp:
            for line in resp.strip().split('\n'):
                try:
                    if '=' not in line: continue
                    d = line.split('"')[1].split('~')
                    if len(d) < 40: continue
                    num = ''.join(c for c in d[2] if c.isdigit())
                    if not num: continue
                    q[num] = {
                        'name': d[1],
                        'current': float(d[3]) if d[3] else 0,
                        'prev_close': float(d[4]) if d[4] else 0,
                        'open': float(d[5]) if d[5] else 0,
                        'high': float(d[33]) if len(d) > 33 and d[33] else 0,
                        'low': float(d[34]) if len(d) > 34 and d[34] else 0,
                        'change_pct': float(d[32]) if len(d) > 32 and d[32] else 0,
                        'source': 'tencent',
                    }
                except Exception:
                    continue
    result = []
    for code, name in A_INDICES:
        if code in q:
            d = q[code]
            result.append({
                'name': name,
                'code': code,
                'price': d.get('current', 0),
                'change_pct': d.get('change_pct', 0),
                'source': d.get('source', ''),
            })
    return result


def get_us_index_quotes() -> list[dict]:
    """通过akshare获取美股指数收盘数据 (盘前使用前一日数据)。
    返回 [{name, price, change_pct, date}, ...]"""
    try:
        import akshare as ak
    except ImportError:
        logger.warning("akshare 不可用, 无法获取美股数据")
        return []

    result = []
    symbols = [("道琼斯", ".DJI"), ("纳斯达克", ".IXIC"), ("标普500", ".INX")]
    for name, symbol in symbols:
        try:
            df = ak.index_us_stock_sina(symbol=symbol)
            if df is not None and len(df) >= 2:
                last = df.iloc[-1]
                prev = df.iloc[-2]
                close_val = float(last["close"])
                prev_close = float(prev["close"])
                change_pct = round((close_val - prev_close) / prev_close * 100, 2) if prev_close else 0
                result.append({
                    'name': name,
                    'price': close_val,
                    'change_pct': change_pct,
                    'date': str(last.get("date", "")),
                    'source': 'akshare',
                })
        except Exception as e:
            logger.debug("US index %s failed: %s", name, e)
    return result


# ═══════════════════════════════════════════
# 通道健康检查
# ═══════════════════════════════════════════

def check_channels() -> dict:
    """测试所有数据通道, 返回 {channel: bool, ...} 状态字典。
    可定时调用以提前发现通道故障。"""
    test_code = '002156'
    status = {}

    # Sina 个股
    try:
        q = sina_quotes([test_code])
        status['sina_stock'] = test_code in q and q[test_code].get('current', 0) > 0
    except Exception:
        status['sina_stock'] = False

    # Sina 指数
    try:
        iq = sina_index_quotes(['000001'])
        status['sina_index'] = '000001' in iq
    except Exception:
        status['sina_index'] = False

    # TDX
    if _HAS_TDX:
        try:
            q = fetch_quotes_tdx([test_code])
            status['tdx'] = test_code in q and q[test_code].get('current', 0) > 0
        except Exception:
            status['tdx'] = False
    else:
        status['tdx'] = False

    # Tencent
    try:
        q = tencent_quotes([test_code])
        status['tencent'] = test_code in q and q[test_code].get('current', 0) > 0
    except Exception:
        status['tencent'] = False

    # Sohu K线
    try:
        k = sohu_kline(test_code, 5)
        status['sohu_kline'] = k is not None and len(k) > 0
    except Exception:
        status['sohu_kline'] = False

    # Eastmoney (检测是否恢复)
    try:
        import urllib.request as _ur
        req = _ur.Request(
            "https://push2.eastmoney.com/api/qt/stock/get",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        _ur.urlopen(req, timeout=5)
        status['eastmoney'] = True
        global EASTMONEY_BLOCKED
        EASTMONEY_BLOCKED = False
    except Exception:
        status['eastmoney'] = False
        EASTMONEY_BLOCKED = True

    logger.info("Channel health: %s", json.dumps(status))
    return status


# ═══════════════════════════════════════════
# 命令行入口: python data_source_router.py check
# ═══════════════════════════════════════════

if __name__ == '__main__':
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'check':
        status = check_channels()
        print(json.dumps(status, indent=2))
        all_ok = all(v for k, v in status.items() if k not in ('eastmoney',))
        print(f"\n核心通道: {'✅ 全部正常' if all_ok else '❌ 有异常'}")
        print("优先级: TDX → Sina → Tencent → Sohu")
    else:
        q = get_quotes(['002156'])
        print(json.dumps(q, ensure_ascii=False, indent=2))
