"""
Round 3: B/S点预测能力评估 — 发布行为模式 + 情绪周期对齐
从三个维度评估预测能力:
1. 发布时间: 盘前/盘中/盘后的分布反映信息处理模式
2. 波动日发帖密度: 市场剧烈波动时是否增加发帖
3. 拐点响应速度: 情绪极值日前后是否发帖
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
        SELECT v.aweme_id, v.vv_id, v.desc, v.create_time, v.duration, f.name
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
                'aweme_id': r[0], 'vv_id': r[1], 'desc': r[2] or '',
                'create_time': ts, 'duration': r[4] or 0,
                'date': dt.strftime('%Y-%m-%d'), 'hour': dt.hour,
                'weekday': dt.weekday(), 'name': r[5] or r[1],
                'datetime': dt,
            })
    return videos

def analyze_round3():
    sentiment = load_sentiment()
    videos = load_videos()
    all_market_dates = sorted(sentiment.keys())

    # 构建市场状态日历
    market_calendar = {}
    for d, s in sentiment.items():
        level = s['level']
        market_calendar[d] = {
            'level': level,
            'index': s['sentiment_index'],
            'is_extreme': s['sentiment_index'] > 80 or s['sentiment_index'] < 20,
            'is_strong': level == 'STRONG',
            'is_weak': level == 'WEAK',
        }

    # 识别拐点日 (前一日的情绪level与当日不同)
    inflection_dates = set()
    prev_level = None
    for d in all_market_dates:
        cur = market_calendar[d]['level']
        if prev_level and cur != prev_level:
            inflection_dates.add(d)
        prev_level = cur

    # 按大V分析
    by_vv = defaultdict(list)
    for v in videos:
        by_vv[v['vv_id']].append(v)

    results = {}
    for vv_id, vids in by_vv.items():
        name = vids[0]['name']
        total = len(vids)

        # 按日期统计发帖数
        posts_by_date = Counter()
        pre_market_posts = Counter()  # 盘前
        during_posts = Counter()      # 盘中
        posts_by_hour = Counter()

        for v in vids:
            posts_by_date[v['date']] += 1
            posts_by_hour[v['hour']] += 1
            if v['weekday'] < 5:
                if v['hour'] < 9:
                    pre_market_posts[v['date']] += 1
                elif 9 <= v['hour'] < 15:
                    during_posts[v['date']] += 1

        # 1. 拐点日发帖密度
        inflection_posts = sum(posts_by_date.get(d, 0) for d in inflection_dates)
        non_inflection_posts = sum(posts_by_date.get(d, 0) for d in posts_by_date if d not in inflection_dates)
        inflection_density = inflection_posts / len(inflection_dates.intersection(set(d for d in posts_by_date))) if inflection_dates else 0

        # 2. 极端日发帖
        extreme_dates = {d for d, m in market_calendar.items() if m['is_extreme']}
        extreme_posts = sum(posts_by_date.get(d, 0) for d in extreme_dates)
        normal_dates_count = len(set(d for d in posts_by_date if d in market_calendar and d not in extreme_dates))

        # 3. 盘前发帖率 (有预测倾向的信号)
        pre_mkt_dates = set(pre_market_posts.keys())
        pre_mkt_ratio = len(pre_mkt_dates) / len(set(v['date'] for v in vids)) if vids else 0

        # 4. 估值/基本面信号: 描述长度超过50字的比例
        long_desc_count = sum(1 for v in vids if len(v['desc']) > 50)
        has_substance_ratio = long_desc_count / total if total > 0 else 0

        # 5. 视频时长 (短视频<60s vs 长视频>120s)
        short_vids = sum(1 for v in vids if 0 < v['duration'] < 60)
        medium_vids = sum(1 for v in vids if 60 <= v['duration'] <= 180)
        long_vids = sum(1 for v in vids if v['duration'] > 180)

        # 6. 活跃天数 / 时间跨度
        dates_active = sorted(set(v['date'] for v in vids))
        if len(dates_active) >= 2:
            first_date = datetime.strptime(dates_active[0], '%Y-%m-%d')
            last_date = datetime.strptime(dates_active[-1], '%Y-%m-%d')
            span_days = (last_date - first_date).days or 1
            posts_per_active_day = total / len(dates_active)
        else:
            span_days = 1
            posts_per_active_day = total

        # 7. 综合评分 (0-100)
        score = 0
        breakdown = {}

        # 7a. 盘前发帖习惯 (有预判意识) - 25分
        if pre_mkt_ratio > 0.3:
            score += 25
        elif pre_mkt_ratio > 0.15:
            score += 15
        elif pre_mkt_ratio > 0.05:
            score += 5
        breakdown['pre_market_habit'] = min(25, int(pre_mkt_ratio * 50))

        # 7b. 实质内容密度 (长描述比例) - 25分
        if has_substance_ratio > 0.5:
            score += 25
        elif has_substance_ratio > 0.3:
            score += 15
        elif has_substance_ratio > 0.1:
            score += 5
        breakdown['substance'] = min(25, int(has_substance_ratio * 40))

        # 7c. 专注度 (话题集中) - 20分
        # 从描述长度方差判断内容一致性
        desc_lens = [len(v['desc']) for v in vids]
        avg_len = sum(desc_lens) / len(desc_lens) if desc_lens else 0
        # 短描述+一致 = 研报风格
        if 30 < avg_len < 200:
            score += 20
        elif 20 < avg_len < 300:
            score += 10
        breakdown['consistency'] = 10 if 20 < avg_len < 300 else 0

        # 7d. 市场敏感度 (极端日发帖) - 20分
        if extreme_posts > 3:
            score += 20
        elif extreme_posts > 1:
            score += 10
        breakdown['market_sensitivity'] = min(20, extreme_posts * 5)

        # 7e. 信息密度 (日频) - 10分
        if posts_per_active_day >= 3:
            score += 10
        elif posts_per_active_day >= 1.5:
            score += 5
        breakdown['frequency'] = min(10, int(posts_per_active_day * 3))

        results[vv_id] = {
            'name': name,
            'total': total,
            'active_days': len(dates_active),
            'span_days': span_days,
            'posts_per_day': round(posts_per_active_day, 1),
            'avg_desc_len': round(avg_len, 0),
            'has_substance_ratio': round(has_substance_ratio, 3),
            'pre_market_ratio': round(pre_mkt_ratio, 3),
            'extreme_day_posts': extreme_posts,
            'inflection_day_posts': inflection_posts,
            'duration_profile': {'<60s': short_vids, '60-180s': medium_vids, '>180s': long_vids},
            'score': score,
            'score_breakdown': breakdown,
            'posts_by_hour_top': posts_by_hour.most_common(5),
        }

    output_path = f"{DATA_DIR}/vv_round3_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("="*60)
    print("Round 3: 发布行为模式 → B/S预测能力评分")
    print("="*60)
    for vv_id, r in sorted(results.items(), key=lambda x: x[1]['score'], reverse=True):
        bd = r['score_breakdown']
        print(f"\n{'='*50}")
        print(f"{r['name']} (@{vv_id}) — 总分: {r['score']}/100")
        print(f"{'='*50}")
        print(f"  视频: {r['total']} | 活跃{r['active_days']}天 | 跨度{r['span_days']}天 | "
              f"日均{r['posts_per_day']}帖")
        print(f"  盘前习惯: {bd['pre_market_habit']}/25 | 实质内容: {bd['substance']}/25 | "
              f"内容一致: {bd['consistency']}/20 | 市场敏感: {bd['market_sensitivity']}/20 | "
              f"频率: {bd['frequency']}/10")
        print(f"  平均描述: {r['avg_desc_len']}字 | 实质内容比: {r['has_substance_ratio']}")
        print(f"  极端日发帖: {r['extreme_day_posts']} | 拐点日发帖: {r['inflection_day_posts']}")
        print(f"  时长分布: {r['duration_profile']}")
        print(f"  热门时段: {r['posts_by_hour_top'][:3]}")

    print(f"\n结果已保存: {output_path}")
    return results

if __name__ == '__main__':
    analyze_round3()
