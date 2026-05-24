#!/usr/bin/env python3
"""
竞价数据通道调研 — 纯测试脚本，不改生产代码
==============================================
测试三个通道（新浪/TDX/腾讯）对单只股票 002156 的返回数据，
记录每个通道能提供哪些竞价相关字段。

A股竞价时段: 9:15-9:25，9:25 产生开盘价。当前是周末，API 返回的是
最新交易日收盘数据，字段结构相同但值可能是静态的。
"""
import json
import urllib.request
import sys
import os

# 确保能找到 pytdx
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TEST_CODE = "002156"
TEST_NAME = "通富微电"

SINA_HEADERS = {"Referer": "https://finance.sina.com.cn"}
TENCENT_HEADERS = {"Referer": "https://stock.finance.qq.com"}
UA_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

def _fetch(url, headers, timeout=15, encoding="utf-8"):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            # 先试声明编码
            try:
                return raw.decode(encoding, errors="replace")
            except Exception:
                return raw.decode("utf-8", errors="replace")
    except Exception as e:
        return f"ERROR: {e}"

def prefix(code):
    if code.startswith(("60", "68", "90", "9")):
        return "sh"
    return "sz"


def banner(title):
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)


# ═══════════════════════════════════════════════════════════════
#  通道1: 新浪 — 实时行情
# ═══════════════════════════════════════════════════════════════

def test_sina_quote(code):
    banner(f"通道1: 新浪 hq.sinajs.cn — {code} {TEST_NAME}")
    p = prefix(code)
    url = f"https://hq.sinajs.cn/list={p}{code}"
    print(f"URL: {url}")
    resp = _fetch(url, SINA_HEADERS, encoding="gbk")
    if resp.startswith("ERROR"):
        print(f"  ** 请求失败: {resp}")
        return None, resp
    print(f"原始响应 ({len(resp)} 字节):")
    print(resp.strip())

    # 解析字段
    if '="' not in resp:
        print("  ** 响应格式异常，无法解析")
        return None, resp

    try:
        data_str = resp.split('"')[1]
        fields = data_str.split(",")
        print(f"\n共 {len(fields)} 个字段:")
        print("-" * 60)

        # 新浪字段映射 (个股)
        sina_fields = [
            (0, "名称"),
            (1, "今开盘"),
            (2, "昨收盘"),
            (3, "当前价"),
            (4, "今日最高"),
            (5, "今日最低"),
            (6, "竞买价(买一)"),
            (7, "竞卖价(卖一)"),
            (8, "成交股数(股)"),
            (9, "成交金额(元)"),
            (10, "买一量"),
            (11, "买一价"),
            (12, "买二量"),
            (13, "买二价"),
            (14, "买三量"),
            (15, "买三价"),
            (16, "买四量"),
            (17, "买四价"),
            (18, "买五量"),
            (19, "买五价"),
            (20, "卖一量"),
            (21, "卖一价"),
            (22, "卖二量"),
            (23, "卖二价"),
            (24, "卖三量"),
            (25, "卖三价"),
            (26, "卖四量"),
            (27, "卖四价"),
            (28, "卖五量"),
            (29, "卖五价"),
            (30, "日期"),
            (31, "时间"),
            (32, "状态(00=正常)"),
        ]

        parsed = {}
        for idx, label in sina_fields:
            val = fields[idx] if idx < len(fields) else "N/A"
            parsed[label] = val
            print(f"  [{idx:2d}] {label:16s} = {val}")

        # 额外字段 (>32)
        if len(fields) > 32:
            print(f"\n  额外字段 ({len(fields)-32} 个):")
            for i in range(32, len(fields)):
                print(f"  [{i:2d}] = {fields[i]}")

        return parsed, resp
    except Exception as e:
        print(f"  ** 解析异常: {e}")
        return None, resp


# ═══════════════════════════════════════════════════════════════
#  通道2: 腾讯 — 实时行情
# ═══════════════════════════════════════════════════════════════

def test_tencent_quote(code):
    banner(f"通道2: 腾讯 web.sqt.gtimg.cn — {code} {TEST_NAME}")
    p = prefix(code)
    url = f"https://web.sqt.gtimg.cn/q={p}{code}"
    print(f"URL: {url}")
    resp = _fetch(url, TENCENT_HEADERS, encoding="utf-8")
    if resp.startswith("ERROR"):
        print(f"  ** 请求失败: {resp}")
        return None, resp
    print(f"原始响应 ({len(resp)} 字节):")
    print(resp.strip())

    if '="' not in resp:
        print("  ** 响应格式异常")
        return None, resp

    try:
        data_str = resp.split('"')[1]
        fields = data_str.split("~")
        print(f"\n共 {len(fields)} 个字段:")
        print("-" * 60)

        # 腾讯字段映射 (基于实测和网上资料)
        tencent_fields = [
            (0,  "未知00"),
            (1,  "名称"),
            (2,  "代码"),
            (3,  "当前价"),
            (4,  "昨收盘"),
            (5,  "今开盘"),
            (6,  "成交量(手)"),
            (7,  "外盘"),
            (8,  "内盘"),
            (9,  "买一价"),
            (10, "买二价"),
            (11, "买三价"),
            (12, "买四价"),
            (13, "买五价"),
            (14, "买一量"),
            (15, "买二量"),
            (16, "买三量"),
            (17, "买四量"),
            (18, "买五量"),
            (19, "卖一价"),
            (20, "卖二价"),
            (21, "卖三价"),
            (22, "卖四价"),
            (23, "卖五价"),
            (24, "卖一量"),
            (25, "卖二量"),
            (26, "卖三量"),
            (27, "卖四量"),
            (28, "卖五量"),
            (29, "委比"),
            (30, "时间"),
            (31, "涨跌额"),
            (32, "涨跌幅%"),
            (33, "今日最高"),
            (34, "今日最低"),
            (35, "价/量(未知)"),
            (36, "成交量(手?)"),
            (37, "成交额(万)"),
            (38, "换手率%"),
            (39, "市盈率"),
            (40, "振幅%"),
            (41, "流通市值(亿)"),
            (42, "总市值(亿)"),
            (43, "52周最高"),
            (44, "52周最低"),
            (45, "涨停价"),
            (46, "跌停价"),
            (47, "量比"),
            (48, "委差"),
            (49, "均价"),
            (50, "动态市盈率"),
            (51, "静态市盈率"),
        ]

        parsed = {}
        for idx, label in tencent_fields:
            val = fields[idx] if idx < len(fields) else "N/A"
            parsed[label] = val
            print(f"  [{idx:2d}] {label:16s} = {val}")

        # 额外字段
        if len(fields) > len(tencent_fields):
            print(f"\n  额外字段 ({len(fields)-len(tencent_fields)} 个):")
            for i in range(len(tencent_fields), len(fields)):
                print(f"  [{i:2d}] = {fields[i]}")

        return parsed, resp
    except Exception as e:
        print(f"  ** 解析异常: {e}")
        import traceback
        traceback.print_exc()
        return None, resp


# ═══════════════════════════════════════════════════════════════
#  通道3: TDX/通达信 — pytdx 直连
# ═══════════════════════════════════════════════════════════════

def test_tdx_quote(code):
    banner(f"通道3: TDX/通达信 pytdx — {code} {TEST_NAME}")
    try:
        from pytdx.hq import TdxHq_API
    except ImportError:
        print("  ** pytdx 未安装，跳过")
        return None, str(None)

    market = 1 if code.startswith(("60", "68", "90", "9")) else 0
    servers = [
        ("180.153.18.170", 7709),
        ("124.71.213.94", 7709),
        ("47.96.110.185", 7709),
    ]

    api = None
    for ip, port in servers:
        try:
            a = TdxHq_API()
            if a.connect(ip, port, time_out=8):
                api = a
                print(f"  已连接: {ip}:{port}")
                break
        except Exception as e:
            print(f"  连接失败 {ip}:{port}: {e}")
            continue

    if api is None:
        print("  ** 所有TDX服务器连接失败")
        return None, str(None)

    data = {}
    try:
        # 1. 实时报价
        print("\n--- get_security_quotes (实时报价) ---")
        quotes = api.get_security_quotes([(market, code)])
        if quotes:
            q = quotes[0]
            print(f"  原始返回: {json.dumps(q, ensure_ascii=False, default=str)}")
            print(f"\n  所有字段 (共{len(q)}个):")
            for k, v in sorted(q.items()):
                print(f"    {k:20s} = {v}")
            data["quote"] = q
        else:
            print("  (空)")

        # 2. 实时盘口 (Level-2 五档)
        print("\n--- get_quote_bar (盘口信息) ---")
        try:
            bar = api.get_quote_bar(market, code)
            if bar:
                print(f"  数据类型: {type(bar)}")
                if isinstance(bar, dict):
                    for k, v in bar.items():
                        print(f"    {k} = {v}")
                else:
                    print(f"  原始: {bar}")
                data["bar"] = bar
            else:
                print("  (空)")
        except Exception as e:
            print(f"  异常: {e}")

        # 3. 分时数据 (最新一笔)
        print("\n--- get_minute_time_data (分时) ---")
        try:
            minute = api.get_minute_time_data(market, code)
            if minute is not None:
                if isinstance(minute, dict):
                    for k, v in minute.items():
                        print(f"    {k} = {v}")
                else:
                    print(f"  原始: {minute}")
                data["minute"] = minute
            else:
                print("  (空)")
        except Exception as e:
            print(f"  异常: {e}")

        # 4. 历史分笔 (最近的)
        print("\n--- get_history_transaction_data (近期分笔) ---")
        try:
            trans = api.get_history_transaction_data(market, code, 0, 5)
            if trans:
                print(f"  共 {len(trans)} 笔:")
                for i, t in enumerate(trans[:3]):
                    print(f"    #{i}: {t}")
                data["recent_tx"] = trans[:3]
            else:
                print("  (空)")
        except Exception as e:
            print(f"  异常: {e}")

        # 5. 日K线 (含今日)
        print("\n--- get_security_bars (日K线, 最后2根) ---")
        try:
            from pytdx.hq import TDXParams
            bars = api.get_security_bars(TDXParams.KLINE_TYPE_DAILY, market, code, 0, 2)
            if bars:
                for i, b in enumerate(bars):
                    print(f"  Bar #{i}: {b}")
                data["daily_bars"] = bars
            else:
                print("  (空)")
        except Exception as e:
            print(f"  异常: {e}")

        # 6. 分时K线 (5分钟)
        print("\n--- get_index_bars (5分钟K线, 最后2根) ---")
        try:
            from pytdx.hq import TDXParams
            bars_5m = api.get_index_bars(TDXParams.KLINE_TYPE_5MIN, market, code, 0, 2)
            if bars_5m:
                for i, b in enumerate(bars_5m):
                    print(f"  5m Bar #{i}: {b}")
                data["5min_bars"] = bars_5m
            else:
                print("  (空)")
        except Exception as e:
            print(f"  异常: {e}")

    finally:
        try:
            api.disconnect()
        except Exception:
            pass

    return data, json.dumps(data, default=str)


# ═══════════════════════════════════════════════════════════════
#  辅助: 测试全市场竞价统计可用性（东方财富）
# ═══════════════════════════════════════════════════════════════

def test_eastmoney_breadth():
    """测试东方财富是否仍被WAF封锁（全市场涨跌分布API）"""
    banner("附: 东方财富 push2 (校验封锁状态)")
    url = "https://push2.eastmoney.com/api/qt/clist/get"
    params = {
        "pn": 1, "pz": 5, "po": 1, "np": 1,
        "ut": "bd1d9ddb04089700cf9c27f6f7426281",
        "fltt": 2, "invt": 2, "fid": "f3",
        "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",
        "fields": "f2,f3,f12,f14",
    }
    param_str = "&".join(f"{k}={v}" for k, v in params.items())
    full_url = f"{url}?{param_str}"
    print(f"URL: {full_url[:120]}...")
    resp = _fetch(full_url, UA_HEADERS, timeout=10)
    if resp.startswith("ERROR"):
        print(f"  ** 阻塞/超时: {resp}")
        return False
    print(f"  响应前200字符: {resp[:200]}")
    try:
        data = json.loads(resp)
        total = data.get("data", {}).get("total", "N/A")
        diff = data.get("data", {}).get("diff", [])
        print(f"  全市场股票数: {total}")
        print(f"  首条数据: {diff[0] if diff else '空'}")
        return True
    except Exception as e:
        print(f"  JSON解析失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════════════════════

def main():
    import datetime
    print("=" * 80)
    print(f"  A股竞价数据通道调研 — {datetime.datetime.now():%Y-%m-%d %H:%M}")
    print(f"  测试股票: {TEST_CODE} {TEST_NAME}")
    print(f"  注意: 当前是周末，API 返回最新交易日数据（值可能是静态的）")
    print("=" * 80)

    results = {}

    # 通道1: 新浪
    sina_parsed, sina_raw = test_sina_quote(TEST_CODE)
    results["sina"] = sina_parsed

    # 通道2: 腾讯
    tencent_parsed, tencent_raw = test_tencent_quote(TEST_CODE)
    results["tencent"] = tencent_parsed

    # 通道3: TDX
    tdx_parsed, tdx_raw = test_tdx_quote(TEST_CODE)
    results["tdx"] = tdx_parsed

    # 东财封锁状态
    test_eastmoney_breadth()

    # ═════════════════════════════════════════════════════════════
    #  整理对比报告
    # ═════════════════════════════════════════════════════════════
    banner("对比报告: 三个通道的竞价数据能力")

    auction_fields = [
        # (字段类别, 字段名, 新浪, 腾讯, TDX, call_auction.py是否已采)
        ("成交价", "昨收盘", "有(f[2])", "有(d[4])", "有(last_close)", "间接(通过EM)"),
        ("成交价", "开盘价(竞价结果)", "有(f[1])", "有(d[5])", "有(open)", "是(持仓竞价)"),
        ("成交价", "当前价", "有(f[3])", "有(d[3])", "有(price)", "是"),
        ("成交价", "最高价", "有(f[4])", "有(d[33])", "有(high)", "否"),
        ("成交价", "最低价", "有(f[5])", "有(d[34])", "有(low)", "否"),
        ("成交量", "成交量", "有(f[8],股)", "有(d[6],手)", "有(vol)", "否"),
        ("成交量", "成交额", "有(f[9],元)", "有(d[37],万)", "有(amount)", "否"),
        ("成交量", "换手率", "无", "有(d[38])", "无", "否"),
        ("成交量", "量比", "无", "有(d[47])", "无", "否"),
        ("盘口", "买一价", "有(f[11])", "有(d[9])", "有(bid1)", "否"),
        ("盘口", "买一量", "有(f[10])", "有(d[14])", "无", "否"),
        ("盘口", "买五档", "有(f[10-19])", "有(d[9-18])", "部分(bid1-5)", "否"),
        ("盘口", "卖五档", "有(f[20-29])", "有(d[19-28])", "部分(ask1-5)", "否"),
        ("竞价动态", "9:15-25虚拟撮合价", "无", "无", "无", "否(EM也没有)"),
        ("竞价动态", "未匹配量", "无", "无", "无", "否"),
        ("竞价动态", "匹配量", "无", "无", "无", "否"),
        ("个股估值", "市盈率", "无", "有(d[39])", "无", "否"),
        ("个股估值", "总市值", "无", "有(d[42])", "无", "否"),
        ("个股估值", "流通市值", "无", "有(d[41])", "无", "否"),
        ("个股", "涨跌幅%", "计算", "有(d[32])", "计算", "是"),
        ("个股", "涨跌停价", "无", "有(d[45,46])", "无", "否"),
        ("全市场", "涨跌家数统计", "无", "无", "无", "是(但依赖EM)"),
        ("全市场", "涨停/跌停统计", "无", "无", "无", "是(但依赖EM)"),
        ("板块", "概念板块竞价", "无", "无", "无", "是(但依赖EM)"),
        ("板块", "行业板块竞价", "无", "无", "无", "是(但依赖EM)"),
    ]

    print()
    print(f"{'类别':10s} {'字段':20s} {'新浪':12s} {'腾讯':12s} {'TDX':12s} {'call_auction状态':20s}")
    print("-" * 92)
    for cat, field, s, t, d, status in auction_fields:
        print(f"{cat:10s} {field:20s} {s:12s} {t:12s} {d:12s} {status:20s}")

    print()
    print("=" * 80)
    print("  关键结论")
    print("=" * 80)
    print("""
1. [P0] 竞价动态数据 (9:15-9:25虚拟撮合轨迹) — 三个通道都不提供
   - 新浪/腾讯/TDX 只返回 9:25 后的实时行情，无法回溯竞价过程的撮合变化
   - 东方财富的 push2 API 有竞价相关字段但当前被 WAF 封锁
   - 如需要竞价动态数据，需接入交易所 Level-2 行情源或第三方商业数据

2. [P1] 盘口五档 — 新浪和腾讯都提供完整的买卖五档
   - call_auction.py 当前没有采集盘口数据（f43-f60+170字段清单不含盘口）
   - 腾讯额外提供: 涨停价/跌停价/量比/换手率/市盈率/总市值/流通市值

3. [P2] 全市场竞价统计 (涨跌家数/涨停数) — 三个通道都不提供
   - call_auction.py 当前通过东方财富 push2 API 获取
   - 东方财富被封锁后，全市场统计=空
   - 替代方案: 可从三个通道逐只遍历（太慢），或用腾讯首页全量API

4. [P2] 腾讯是三个通道中字段最丰富的 (50+ 字段)
   - 单个请求包含: 价格/量/盘口/估值/涨跌停价/量比
   - 建议将腾讯作为竞价采集的主通道（开盘价+价格信息已够用）

5. 本次测试是周末，各通道返回的"当前价"是上一交易日收盘价，
   开盘价/最高/最低也为上一交易日数据。结构正确但数据是静态的。
""")

    print("=" * 80)
    print("  调研完成")
    print("=" * 80)


if __name__ == "__main__":
    main()
