"""
Round 5: 综合评分 + 最终排行
融合 R1-R4 四个维度:
  R1: 预测密度 (视频日期 vs 次日涨跌)
  R2: 话题专注度 + 意图分布
  R3: 发布行为模式 (盘前习惯/实质内容/市场敏感度)
  R4: 情绪周期逆向指标
"""
import json, os
from collections import defaultdict

DATA_DIR = "D:/1989n/stock_data"

def load_round(path):
    with open(path, encoding='utf-8') as f:
        return json.load(f)

def normalize_score(value, min_val, max_val, target_max=25):
    """归一化到 0-target_max"""
    if max_val == min_val:
        return target_max // 2
    return round((value - min_val) / (max_val - min_val) * target_max, 1)

def analyze_round5():
    r1 = load_round(f"{DATA_DIR}/vv_round1_results.json")
    r2 = load_round(f"{DATA_DIR}/vv_round2_results.json")
    r3 = load_round(f"{DATA_DIR}/vv_round3_results.json")
    r4 = load_round(f"{DATA_DIR}/vv_round4_results.json")

    all_vv = set(r1.keys()) | set(r3.keys())

    results = {}
    for vv_id in all_vv:
        d1 = r1.get(vv_id, {})
        d2 = r2.get(vv_id, {})
        d3 = r3.get(vv_id, {})
        d4 = r4.get(vv_id, {})

        name = d3.get('name') or d1.get('name', vv_id)
        total = d3.get('total') or d1.get('total_videos', 0)

        # ==== R1: 预测密度 (0-25) ====
        pred_score = d1.get('predictive_score', 0)
        # 高预测密度分可能只是因为期间市场好，需要调整
        nd = d1.get('next_day', {})
        r1_adj = pred_score
        # 如果次日几乎全是上涨，说明是牛市期间的数据，需要打折
        if nd.get('total', 0) > 10 and nd.get('next_up', 0) / nd['total'] > 0.85:
            r1_adj = pred_score * 0.5  # 打折: 牛市中"预测"涨价值低

        # ==== R2: 话题专注度 (0-20) ====
        topic_conc = d2.get('topic_concentration', 0)
        # 话题集中度 > 0.3 表示有专长领域
        intent = d2.get('intent_distribution', {})
        analysis_count = intent.get('ANALYSIS', 0)
        hype_count = intent.get('HYPE', 0)
        r2_topic = min(20, topic_conc * 50 + analysis_count * 2 - hype_count * 3)

        # ==== R3: 行为模式 (0-30) ====
        r3_score = d3.get('score', 0)
        r3_breakdown = d3.get('score_breakdown', {})
        r3_behavior = r3_score * 0.3  # 30% of original 100

        # ==== R4: 逆向指标 (0-25) ====
        contrarian = d4.get('contrarian_score', 0)
        # -100 to +100 → 0 to 25
        r4_norm = (contrarian + 100) / 200 * 25 if isinstance(contrarian, (int, float)) else 12.5

        # ==== 补充: 数据覆盖率 (视频是否有描述) ====
        has_desc_ratio = d3.get('has_substance_ratio', 0)
        if has_desc_ratio > 0.3:
            coverage_bonus = 5
        elif has_desc_ratio > 0.1:
            coverage_bonus = 3
        else:
            coverage_bonus = 0

        # ==== 总计 (满分100) ====
        total_score = r1_adj + r2_topic + r3_behavior + r4_norm + coverage_bonus

        results[vv_id] = {
            'name': name,
            'total_videos': total,
            'final_score': round(total_score, 1),
            'breakdown': {
                'R1_预测密度': round(r1_adj, 1),
                'R2_话题专注': round(r2_topic, 1),
                'R3_行为模式': round(r3_behavior, 1),
                'R4_逆向指标': round(r4_norm, 1),
                '数据覆盖Bonus': coverage_bonus,
            },
            'key_strength': '',
            'key_weakness': '',
            'recommendation': '',
        }

    # ==== 确定每个人的优劣势和推荐 ====
    for vv_id, r in results.items():
        bd = r['breakdown']
        d2 = r2.get(vv_id, {})
        d3 = r3.get(vv_id, {})

        # 找优劣势
        max_dim = max(bd.items(), key=lambda x: x[1] if x[0] != '数据覆盖Bonus' else 0)
        min_dim = min(bd.items(), key=lambda x: x[1] if x[0] != '数据覆盖Bonus' else 999)

        r['key_strength'] = max_dim[0]
        r['key_weakness'] = min_dim[0]

        # 推荐等级
        if r['final_score'] >= 60:
            r['recommendation'] = 'A级: 高优先级跟踪，可用于投资决策参考'
        elif r['final_score'] >= 45:
            r['recommendation'] = 'B级: 可以作为某一维度参考，不盲从'
        elif r['final_score'] >= 30:
            r['recommendation'] = 'C级: 谨慎参考，存在明显短板'
        else:
            r['recommendation'] = 'D级: 不建议用于投资决策'

    # ==== 特别调整: 基于原始评估的定性判断 ====
    # 口罩哥虽然数据窗口短，但研报风格+信息密度在定性评估中极高
    if 'yanbao60' in results:
        results['yanbao60']['final_score'] = max(results['yanbao60']['final_score'], 65)
        results['yanbao60']['recommendation'] = 'A级: 研报级信息源，高优先级跟踪'
        results['yanbao60']['key_strength'] = '信息密度+研报风格'
        results['yanbao60']['note'] = '数据窗口仅11天，定量评分偏低，定性评估大幅上调'

    # 创业魔法师定性降级
    if 'guojame' in results:
        results['guojame']['final_score'] = min(results['guojame']['final_score'], 10)
        results['guojame']['recommendation'] = 'D级: 纯流量号，投资价值为零'
        results['guojame']['note'] = '169万粉丝但95%视频无描述，定量+定性均最低'

    # 太阳李博良 — 不是财经号
    if '6052m9121' in results:
        results['6052m9121']['note'] = '非财经号，自我成长/认知类博主，定量高分来自长描述+活跃发帖，但与投资无关'

    output_path = f"{DATA_DIR}/vv_round5_final.json"
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    # ==== 打印最终排名 ====
    print("="*70)
    print("Round 5: 综合评分 — 五维交叉验证最终排行")
    print("="*70)
    print(f"{'排名':<4} {'大V':<18} {'得分':<8} {'评级':<6} {'核心优势':<16} {'视频数'}")
    print("-"*70)

    sorted_vv = sorted(results.items(), key=lambda x: x[1]['final_score'], reverse=True)
    for rank, (vv_id, r) in enumerate(sorted_vv, 1):
        name = r['name'][:16]
        note = r.get('note', '')
        print(f"{rank:<4} {name:<18} {r['final_score']:<8.1f} "
              f"{r['recommendation'][:4]:<6} {r['key_strength']:<16} {r['total_videos']}")
        if note:
            print(f"     ⚠ {note}")

    print("-"*70)
    print(f"\n详细结果: {output_path}")

    # ==== 维度对比 ====
    print(f"\n{'='*70}")
    print("各维度Top3")
    print(f"{'='*70}")
    for dim in ['R1_预测密度', 'R2_话题专注', 'R3_行为模式', 'R4_逆向指标']:
        sorted_dim = sorted(results.items(), key=lambda x: x[1]['breakdown'][dim], reverse=True)
        top3 = [(r['name'][:12], r['breakdown'][dim]) for _, r in sorted_dim[:3]]
        print(f"  {dim}: {top3}")

    return results

if __name__ == '__main__':
    analyze_round5()
