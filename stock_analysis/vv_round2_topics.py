"""
Round 2: 题材轮动 + 资金流向交叉验证
- 视频话题提取 → 匹配当日/次日板块涨跌
- 识别"追热点"(事后解释) vs "提前布局"(事前预测)
- 视频发布时间 vs 交易时段
"""
import sqlite3, json, re
from datetime import datetime, timezone, timedelta
from collections import defaultdict, Counter

TZ = timezone(timedelta(hours=8))
DATA_DIR = "D:/1989n/stock_data"

# 题材关键词 → 板块映射
TOPIC_SECTOR_MAP = {
    '半导体': ['半导体', '芯片', '封测', '光刻', '晶圆', '台积电', '中芯', 'GPU', 'CPU', 'AI芯片',
              'chiplet', '先进封装', 'HBM', 'EDA', 'RISC-V', 'ARM', '英伟达', 'AMD', '华为芯片'],
    'AI': ['AI', '人工智能', '大模型', 'LLM', 'GPT', '深度学习', '机器学习', 'sora', 'claude',
           'deepseek', 'ChatGPT', '智能体', 'agent', 'AIGC', '多模态'],
    'CPO/光模块': ['CPO', '光模块', '光通信', '光电共封装', '硅光', '800G', '1.6T', '新易盛', '中际旭创', '天孚通信'],
    '机器人': ['机器人', '人形机器人', '具身智能', '减速器', '伺服', '特斯拉Bot', 'Figure'],
    '新能源': ['新能源', '锂电', '光伏', '储能', '固态电池', '钠电池', '钙钛矿', '风电', '氢能'],
    '消费电子': ['消费电子', '手机', '苹果', '华为', '折叠屏', 'MR', 'AR', 'VR', '头显'],
    '商业航天': ['航天', '卫星', '火箭', '低轨', '星链', 'SpaceX', '商业航天', '军工'],
    '医药': ['医药', '制药', 'CRO', 'CDMO', '生物药', '仿制药', '中药', '医疗器械', '基因'],
    '汽车': ['汽车', '电动车', '新能源车', '自动驾驶', '智能驾驶', '比亚迪', '特斯拉', '华为车'],
    '金融': ['银行', '券商', '保险', '降息', '美联储', '利率', '存款', '贷款', '货币政策'],
    '消费': ['消费', '白酒', '食品', '零售', '旅游', '餐饮', '家电', '免税'],
    '机器人/自动化': ['自动化', '工业4.0', '智能制造', '机器视觉', 'PLC', '变频器'],
}

# 股票代码正则
TICKER_RE = re.compile(r'(00[0-9]{4}|30[0-9]{4}|60[0-9]{4}|68[0-9]{4})')

def extract_topics(desc):
    """从描述中提取话题"""
    found = []
    for sector, keywords in TOPIC_SECTOR_MAP.items():
        for kw in keywords:
            if kw.lower() in desc.lower():
                if sector not in found:
                    found.append(sector)
                break
    return found

def extract_tickers(desc):
    """提取可能的股票代码"""
    codes = TICKER_RE.findall(desc)
    return list(set(codes))

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
        if ts:
            dt = datetime.fromtimestamp(ts, tz=TZ)
            videos.append({
                'aweme_id': r[0], 'vv_id': r[1], 'desc': r[2] or '',
                'create_time': ts, 'date': dt.strftime('%Y-%m-%d'),
                'hour': dt.hour, 'weekday': dt.weekday(),
                'name': r[4] or r[1],
            })
    return videos

def load_sector_data():
    """加载所有可用的板块/题材数据"""
    import os, glob
    sector_snapshots = []
    for f in sorted(glob.glob(f"{DATA_DIR}/intel_report_*.json")):
        try:
            with open(f, encoding='utf-8') as fh:
                data = json.load(fh)
            sector_snapshots.append(data)
        except:
            pass
    return sector_snapshots

def classify_intent(desc, topics, post_hour):
    """
    判断视频意图：
    - BUY_SIGNAL: 明确看多信号
    - SELL_SIGNAL: 明确看空/风险提示
    - ANALYSIS: 客观分析
    - HYPE: 纯情绪/标题党
    - NEWS_READ: 念新闻
    """
    desc_lower = desc.lower()

    buy_kw = ['买入','加仓','上车','起飞','爆发','涨停','主升浪','起爆点','底部','抄底','建仓',
              '满仓','干','梭','机会','金叉','突破','目标价','看多','利好','翻倍','十倍']
    sell_kw = ['卖出','减仓','清仓','止盈','逃顶','见顶','崩盘','暴跌','危机','泡沫','风险',
               '死亡','割肉','亏损','套牢']
    hype_kw = ['收藏','必看','揭秘','震惊','真相','错过后悔','赶紧','重要','重磅',
               '三遍','好好看看','必读']

    buy_count = sum(1 for kw in buy_kw if kw in desc_lower)
    sell_count = sum(1 for kw in sell_kw if kw in desc_lower)
    hype_count = sum(1 for kw in hype_kw if kw in desc_lower)

    if hype_count >= 2:
        return 'HYPE'
    if buy_count >= 2:
        return 'BUY_SIGNAL'
    if sell_count >= 2:
        return 'SELL_SIGNAL'
    if len(desc) > 200 and not hype_kw:
        return 'ANALYSIS'
    if len(desc) < 30:
        return 'NEWS_READ'
    return 'GENERAL'

def analyze_round2():
    sentiment = load_sentiment()
    videos = load_videos()
    all_dates = sorted(sentiment.keys())

    by_vv = defaultdict(list)
    for v in videos:
        by_vv[v['vv_id']].append(v)

    results = {}
    for vv_id, vids in by_vv.items():
        name = vids[0]['name']
        total = len(vids)

        # 话题统计
        topic_counter = Counter()
        intent_counter = Counter()
        all_tickers = Counter()
        pre_market_posts = 0
        during_market_posts = 0
        after_market_posts = 0

        # 追热点 vs 提前布局
        trend_following = 0   # 话题与当日热点板块重叠
        leading = 0           # 话题与次日板块重叠,当日未热

        for v in vids:
            topics = extract_topics(v['desc'])
            tickers = extract_tickers(v['desc'])
            intent = classify_intent(v['desc'], topics, v['hour'])

            for t in topics:
                topic_counter[t] += 1
            for tk in tickers:
                all_tickers[tk] += 1
            intent_counter[intent] += 1

            # 盘前/盘中/盘后
            if v['weekday'] >= 5:  # 周末
                after_market_posts += 1
            elif v['hour'] < 9:
                pre_market_posts += 1
            elif v['hour'] < 15:
                during_market_posts += 1
            else:
                after_market_posts += 1

        # 计算话题集中度 (Herfindahl)
        total_topic_mentions = sum(topic_counter.values())
        topic_concentration = 0
        if total_topic_mentions > 0:
            for count in topic_counter.values():
                topic_concentration += (count / total_topic_mentions) ** 2

        # 热门话题（前5）
        top_topics = topic_counter.most_common(5)

        # 发布时间分布
        timing_dist = {
            'pre_market': pre_market_posts,
            'during_market': during_market_posts,
            'after_market': after_market_posts,
        }

        # 是否有盘前预判习惯
        pre_market_ratio = pre_market_posts / total if total > 0 else 0

        results[vv_id] = {
            'name': name,
            'total_videos': total,
            'topic_concentration': round(topic_concentration, 3),
            'top_topics': [(t, c) for t, c in top_topics],
            'top_tickers': all_tickers.most_common(5),
            'intent_distribution': dict(intent_counter.most_common()),
            'timing_distribution': timing_dist,
            'pre_market_ratio': round(pre_market_ratio, 3),
            'has_original_analysis': intent_counter.get('ANALYSIS', 0) > 5,
            'is_hype_driven': intent_counter.get('HYPE', 0) > total * 0.3,
        }

    # 排序：按原创分析能力
    output_path = f"{DATA_DIR}/vv_round2_results.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print("="*60)
    print("Round 2: 题材轮动 + 话题分析")
    print("="*60)

    # 按分析型分数排
    for vv_id, r in sorted(results.items(), key=lambda x: (
        x[1]['intent_distribution'].get('ANALYSIS', 0) - x[1]['intent_distribution'].get('HYPE', 0)
    ), reverse=True):
        intent = r['intent_distribution']
        print(f"\n{r['name']} (@{vv_id})")
        print(f"  视频: {r['total_videos']} | 话题集中度: {r['topic_concentration']}")
        print(f"  话题: {r['top_topics']}")
        print(f"  股票代码: {r['top_tickers']}")
        print(f"  意图: BUY={intent.get('BUY_SIGNAL',0)} SELL={intent.get('SELL_SIGNAL',0)} "
              f"ANALYSIS={intent.get('ANALYSIS',0)} HYPE={intent.get('HYPE',0)} "
              f"GENERAL={intent.get('GENERAL',0)} NEWS={intent.get('NEWS_READ',0)}")
        print(f"  时间分布: 盘前{r['timing_distribution']['pre_market']} "
              f"盘中{r['timing_distribution']['during_market']} "
              f"盘后{r['timing_distribution']['after_market']}")
        analysis_ratio = round(intent.get('ANALYSIS', 0) / r['total_videos'] * 100, 1)
        hype_ratio = round(intent.get('HYPE', 0) / r['total_videos'] * 100, 1)
        print(f"  分析率: {analysis_ratio}% | 标题党率: {hype_ratio}%")

    print(f"\n结果已保存: {output_path}")
    return results

if __name__ == '__main__':
    analyze_round2()
