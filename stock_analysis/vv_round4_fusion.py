"""
Round 4: 情绪周期相位对齐 + 多源数据融合
- 视频发布所在的市场情绪相位 (恐慌/修复/亢奋/退潮)
- 逆向指标: 极端值处的行为模式
- 三轮结果一致性分析
"""
import sqlite3, json
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

TZ = timezone(timedelta(hours=8))
DATA_DIR = "D:/1989n/stock_data"

def load_sentiment():
    with open(f"{DATA_DIR}/emotional_cycle_raw.json", encoding='utf-8') as f:
        data = json.load(f)
    return {h['date']: h for h in data['history']}

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
        if ts and r[2]:  # 必须有描述
            dt = datetime.fromtimestamp(ts, tz=TZ)
            videos.append({
                'aweme_id': r[0], 'vv_id': r[1], 'desc': r[2],
                'create_time': ts, 'date': dt.strftime('%Y-%m-%d'),
                'hour': dt.hour, 'name': r[4] or r[1],
            })
    return videos

def classify_market_phase(history, current_idx):
    """将市场情绪历史分为4个相位"""
    dates = sorted(history.keys())
    if len(dates) < 5:
        return {}

    indices = [history[d]['sentiment_index'] for d in dates]
    avg = sum(indices) / len(indices)
    phases = {}

    for i, d in enumerate(dates):
        idx = history[d]['sentiment_index']
        level = history[d]['level']

        if level == 'WEAK' and idx < 25:
            phase = 'PANIC'     # 恐慌
        elif level == 'WEAK':
            phase = 'DECLINE'   # 退潮
        elif level == 'STRONG' and idx > 75:
            phase = 'EUPHORIA'  # 亢奋
        elif level == 'STRONG':
            phase = 'REBOUND'   # 修复
        elif idx > avg:
            phase = 'RECOVERY'  # 回暖
        else:
            phase = 'TEPID'     # 温吞
        phases[d] = phase
    return phases

def analyze_sentiment_in_desc(desc):
    """分析描述中的情绪"""
    desc_lower = desc.lower()
    bullish_kw = ['涨', '牛市', '起飞', '爆发', '突破', '利好', '大涨', '暴涨', '涨停',
                  '牛市', '加仓', '满仓', '机会', '抄底', '翻倍']
    bearish_kw = ['跌', '熊市', '崩', '暴跌', '危机', '风险', '泡沫', '见顶', '逃顶',
                  '减仓', '清仓', '止损', '亏损']
    neutral_kw = ['分析', '研报', '数据', '估值', '基本面', '季报', '年报', '财报',
                  '宏观', '政策', '利率', 'PMI', 'CPI']

    bull_score = sum(1 for kw in bullish_kw if kw in desc_lower)
    bear_score = sum(1 for kw in bearish_kw if kw in desc_lower)
    neutral_score = sum(1 for kw in neutral_kw if kw in desc_lower)

    if neutral_score >= 2:
        return 'NEUTRAL'
    if bull_score > bear_score + 1:
        return 'BULLISH'
    if bear_score > bull_score + 1:
        return 'BEARISH'
    if bull_score > 0:
        return 'SLIGHTLY_BULLISH'
    if bear_score > 0:
        return 'SLIGHTLY_BEARISH'
    return 'NEUTRAL'

def analyze_round4():
    sentiment = load_sentiment()
    videos = load_videos()
    phases = classify_market_phase(sentiment, sentiment.get('2026-05-07', {}).get('sentiment_index', 50))

    by_vv = defaultdict(list)
    for v in videos:
        if v['date'] in phases:  # 只保留有市场相位映射的
            by_vv[v['vv_id']].append(v)

    results = {}
    for vv_id, vids in by_vv.items():
        name = vids[0]['name']
        total = len(vids)

        # 相位分布
        phase_counter = Counter()
        sentiment_by_video = []
        contrarian_errors = 0  # 市场亢奋时发bullish信号 = 错误
        contrarian_wins = 0    # 市场恐慌时发bullish信号 = 抄底

        for v in vids:
            phase = phases.get(v['date'], 'UNKNOWN')
            phase_counter[phase] += 1
            vid_sent = analyze_sentiment_in_desc(v['desc'])

            # 逆向指标分析
            if phase in ('EUPHORIA',) and vid_sent in ('BULLISH', 'SLIGHTLY_BULLISH'):
                contrarian_errors += 1  # 亢奋时喊多 = 追高
            elif phase in ('PANIC',) and vid_sent in ('BEARISH', 'SLIGHTLY_BEARISH'):
                contrarian_errors += 1  # 恐慌时喊空 = 割肉
            elif phase in ('PANIC',) and vid_sent in ('BULLISH', 'SLIGHTLY_BULLISH'):
                contrarian_wins += 1    # 恐慌时喊多 = 抄底
            elif phase in ('EUPHORIA',) and vid_sent in ('BEARISH', 'SLIGHTLY_BEARISH'):
                contrarian_wins += 1    # 亢奋时喊空 = 止盈

            sentiment_by_video.append({
                'date': v['date'],
                'phase': phase,
                'desc_sentiment': vid_sent,
                'desc_preview': v['desc'][:80],
            })

        total_relevant = contrarian_errors + contrarian_wins
        contrarian_score = 0
        if total_relevant > 0:
            # 范围 -100 (全部追涨杀跌) 到 +100 (完美逆向)
            contrarian_score = round((contrarian_wins - contrarian_errors) / total_relevant * 100)
        elif contrarian_wins > 0:
            contrarian_score = 100
        elif contrarian_errors > 0:
            contrarian_score = -100

        # 最佳相位: 恐慌和退潮时发帖 = 有逆向思维
        panic_recovery_posts = phase_counter.get('PANIC', 0) + phase_counter.get('DECLINE', 0)
        euphoria_posts = phase_counter.get('EUPHORIA', 0)

        # 核心指标: 逆向评分
        results[vv_id] = {
            'name': name,
            'total_with_phase': total,
            'phase_distribution': dict(phase_counter.most_common()),
            'contrarian_score': contrarian_score,
            'contrarian_wins': contrarian_wins,
            'contrarian_errors': contrarian_errors,
            'panic_posts': panic_recovery_posts,
            'euphoria_posts': euphoria_posts,
            'sample_analysis': sentiment_by_video[:3],
        }

    output_path = f"{DATA_DIR}/vv_round4_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("="*60)
    print("Round 4: 情绪周期相位 + 逆向指标")
    print("="*60)
    print("""
市场相位定义:
  PANIC (<25, WEAK) = 恐慌
  DECLINE (<50, WEAK) = 退潮
  EUPHORIA (>75, STRONG) = 亢奋
  REBOUND (>55, STRONG) = 修复
  RECOVERY (>avg) = 回暖
  TEPID (<avg) = 温吞

逆向评分: 亢奋时喊空/恐慌时喊多 = +win
          亢奋时喊多/恐慌时喊空 = -error
""")

    for vv_id, r in sorted(results.items(), key=lambda x: x[1]['contrarian_score'], reverse=True):
        print(f"\n{r['name']} (@{vv_id})")
        print(f"  有效视频: {r['total_with_phase']}")
        print(f"  相位分布: {r['phase_distribution']}")
        print(f"  逆向评分: {r['contrarian_score']} "
              f"(wins={r['contrarian_wins']} errors={r['contrarian_errors']})")
        print(f"  恐慌/退潮发帖: {r['panic_posts']} | 亢奋发帖: {r['euphoria_posts']}")

    print(f"\n结果已保存: {output_path}")
    return results

if __name__ == '__main__':
    analyze_round4()
