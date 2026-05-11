"""
Round 1: 基础时间轴对齐
- 视频发布日期 vs 当日市场情绪
- 视频发布 vs 次日涨跌 (是否有预测性)
- 视频发布时间戳 vs 日内走势
"""
import sqlite3, json
from datetime import datetime, timezone, timedelta
from collections import defaultdict

TZ = timezone(timedelta(hours=8))
DATA_DIR = "D:/1989n/stock_data"

def load_sentiment():
    with open(f"{DATA_DIR}/emotional_cycle_raw.json", encoding='utf-8') as f:
        data = json.load(f)
    return {h['date']: h for h in data['history']}

def load_intel_reports():
    """加载所有intel_report"""
    import os, glob
    reports = []
    for f in sorted(glob.glob(f"{DATA_DIR}/intel_report_*.json")):
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
            reports.append(data)
        except:
            pass
    return reports

def load_30min_analysis():
    import os, glob
    analyses = []
    for f in sorted(glob.glob(f"{DATA_DIR}/analysis_30min_*.json")):
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
            analyses.append(data)
        except:
            pass
    return analyses

def load_videos():
    conn = sqlite3.connect(f"{DATA_DIR}/vv_radar.db")
    c = conn.cursor()
    c.execute('''
        SELECT v.aweme_id, v.vv_id, v.desc, v.create_time, f.name
        FROM vv_videos v
        LEFT JOIN vv_follows f ON v.vv_id = f.id
        ORDER BY v.create_time
    ''')
    rows = c.fetchall()
    conn.close()

    videos = []
    for r in rows:
        ts = r[3]
        if ts:
            dt = datetime.fromtimestamp(ts, tz=TZ)
            videos.append({
                'aweme_id': r[0],
                'vv_id': r[1],
                'desc': r[2] or '',
                'create_time': ts,
                'date': dt.strftime('%Y-%m-%d'),
                'hour': dt.hour,
                'name': r[4] or r[1],
            })
    return videos

def analyze_round1():
    sentiment = load_sentiment()
    videos = load_videos()

    # 按大V分组
    by_vv = defaultdict(list)
    for v in videos:
        by_vv[v['vv_id']].append(v)

    results = {}
    for vv_id, vids in by_vv.items():
        name = vids[0]['name']
        total = len(vids)
        dates_covered = sorted(set(v['date'] for v in vids))

        # 分析每个视频
        analyzed = []
        for v in vids:
            d = v['date']
            s_today = sentiment.get(d, {})
            # 找下一个交易日
            all_dates = sorted(sentiment.keys())
            next_trade_date = None
            try:
                idx = all_dates.index(d)
                if idx + 1 < len(all_dates):
                    next_trade_date = all_dates[idx + 1]
            except ValueError:
                # date not in trading days, find next
                for td in all_dates:
                    if td > d:
                        next_trade_date = td
                        break

            s_next = sentiment.get(next_trade_date, {}) if next_trade_date else {}

            analyzed.append({
                'date': d,
                'hour': v['hour'],
                'desc': v['desc'][:100],
                'sentiment_today': {
                    'index': s_today.get('sentiment_index'),
                    'level': s_today.get('level'),
                    'up_pct': s_today.get('up_pct'),
                    'limit_up': s_today.get('limit_up_count'),
                    'limit_down': s_today.get('limit_down_count'),
                },
                'sentiment_next': {
                    'date': next_trade_date,
                    'index': s_next.get('sentiment_index'),
                    'level': s_next.get('level'),
                    'up_pct': s_next.get('up_pct'),
                }
            })

        # 统计
        before_strong = 0  # 发布在STRONG日前一天
        before_weak = 0    # 发布在WEAK日前一天
        on_strong = 0      # 发布在STRONG日当天
        on_weak = 0        # 发布在WEAK日当天
        on_normal = 0
        next_is_up = 0     # 次日上涨
        next_is_down = 0   # 次日下跌
        next_big_up = 0    # 次日大涨(>70%)
        next_big_down = 0  # 次日大跌(<30%)
        total_with_next = 0

        for a in analyzed:
            s_t = a['sentiment_today']
            s_n = a['sentiment_next']

            if s_t.get('level') == 'STRONG':
                on_strong += 1
            elif s_t.get('level') == 'WEAK':
                on_weak += 1
            else:
                on_normal += 1

            if s_n.get('index') is not None:
                total_with_next += 1
                if s_n['index'] > 55:
                    next_is_up += 1
                    if s_n['index'] > 70:
                        next_big_up += 1
                elif s_n['index'] < 35:
                    next_is_down += 1
                    if s_n['index'] < 20:
                        next_big_down += 1

        # 计算"预测密度": 视频集中出现在强/弱转换前的比例
        predictive_score = 0
        if total_with_next > 0:
            predictive_score = round((next_big_up + next_big_down) / total_with_next * 100, 1)

        results[vv_id] = {
            'name': name,
            'total_videos': total,
            'date_range': f'{dates_covered[0]} ~ {dates_covered[-1]}' if dates_covered else 'N/A',
            'sentiment_distribution': {
                'on_strong': on_strong,
                'on_normal': on_normal,
                'on_weak': on_weak,
            },
            'next_day': {
                'total': total_with_next,
                'next_up': next_is_up,
                'next_down': next_is_down,
                'next_big_up': next_big_up,
                'next_big_down': next_big_down,
            },
            'predictive_score': predictive_score,
            'sample_videos': analyzed[:3],
        }

    # 保存
    output_path = f"{DATA_DIR}/vv_round1_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # 打印摘要
    print("="*60)
    print("Round 1: 基础时间轴对齐 — 视频 vs 市场情绪")
    print("="*60)
    sorted_vv = sorted(results.items(), key=lambda x: x[1]['predictive_score'], reverse=True)
    for vv_id, r in sorted_vv:
        nd = r['next_day']
        print(f"\n{r['name']} (@{vv_id})")
        print(f"  视频数: {r['total_videos']} | 日期: {r['date_range']}")
        print(f"  情绪分布: STRONG={r['sentiment_distribution']['on_strong']} "
              f"NORMAL={r['sentiment_distribution']['on_normal']} "
              f"WEAK={r['sentiment_distribution']['on_weak']}")
        print(f"  次日可对齐: {nd['total']} | ↑{nd['next_up']} ↓{nd['next_down']} "
              f"大涨前{nd['next_big_up']} 大跌前{nd['next_big_down']}")
        print(f"  预测密度分: {r['predictive_score']} (大涨/大跌前发布占比)")

    print(f"\n结果已保存: {output_path}")
    return results

if __name__ == '__main__':
    analyze_round1()
