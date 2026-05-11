/**
 * 东方财富数据抓取模块
 * 使用东方财富免费API获取集合竞价数据
 */

import type { JingJiaStock, BoardStats, ConceptStats, JingJiaReport, MoneyFlowStats, LimitUpCategory } from './types.ts'

// ========== 配置 ==========
const CONFIG = {
  // 东方财富API基础地址
  EAST_MONEY_API: 'https://push2.eastmoney.com/api/qt/ulist.np/get',
  // 板块数据API
  BOARD_API: 'https://push2.eastmoney.com/api/qt/clist/get',
  // 资金流向API
  MONEY_FLOW_API: 'https://push2.eastmoney.com/api/qt/stock/fflow/daykline/get',
  // 请求超时(ms)
  TIMEOUT: 10000,
  // 用户资金量(万)
  USER_CAPITAL: 300000,
}

// ========== 工具函数 ==========

/** 带超时的fetch */
async function fetchWithTimeout(url: string, timeout = CONFIG.TIMEOUT): Promise<Response> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  try {
    const res = await fetch(url, { signal: controller.signal })
    return res
  } finally {
    clearTimeout(timer)
  }
}

/** 获取当前日期时间 */
function getNow(): { date: string; time: string } {
  const now = new Date()
  const date = now.toISOString().slice(0, 10)
  const time = now.toTimeString().slice(0, 8)
  return { date, time }
}

/** 判断是否在交易时间(9:15-15:00) */
function isTradingTime(): boolean {
  const now = new Date()
  const h = now.getHours()
  const m = now.getMinutes()
  const timeNum = h * 100 + m
  // 集合竞价 9:15-9:25, 连续竞价 9:30-11:30/13:00-15:00
  return (timeNum >= 915 && timeNum <= 925) || 
         (timeNum >= 930 && timeNum <= 1130) || 
         (timeNum >= 1300 && timeNum <= 1500)
}

/** 判断是否涨停(主板10%, 科创/创业板20%) */
function isLimitUp(changePercent: number, code: string): boolean {
  const isKCB = code.startsWith('688')
  const isCYB = code.startsWith('30')
  const limit = isKCB || isCYB ? 19.5 : 9.8
  return changePercent >= limit
}

/** 判断是否跌停 */
function isLimitDown(changePercent: number, code: string): boolean {
  const isKCB = code.startsWith('688')
  const isCYB = code.startsWith('30')
  const limit = isKCB || isCYB ? -19.5 : -9.8
  return changePercent <= limit
}

/** 判断涨停类型 */
function getLimitUpType(stock: JingJiaStock): '一字板' | 'T字板' | '换手板' | '趋势板' {
  // 简化判断：根据换手率和竞价量
  if (stock.turnoverRate < 0.5) return '一字板'
  if (stock.turnoverRate < 2) return 'T字板'
  if (stock.turnoverRate < 10) return '换手板'
  return '趋势板'
}

// ========== 数据抓取 ==========

/** 从东方财富获取集合竞价列表 */
async function fetchJingJiaData(): Promise<JingJiaStock[]> {
  // 东方财富API参数
  // f12=代码, f14=名称, f2=最新价, f6=成交量(手), f4=涨跌幅
  // f8=换手率, f20=流通市值, f9=市盈率, f62=主力净流入
  const params = new URLSearchParams({
    'f12': 'f12',
    'f14': 'f14',
    'f2': 'f2',
    'f4': 'f4',
    'f6': 'f6',
    'f8': 'f8',
    'f20': 'f20',
    'f9': 'f9',
    'f62': 'f62',
    'fs': 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048',  // 沪深A股
    'fields': 'f2,f3,f4,f6,f8,f12,f14,f20,f9,f62',
    'pn': '1',
    'pz': '5000',
    'po': '1',
    'np': '1',
    'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
    'fltt': '2',
    'invt': '2',
    'wbp2u': '|0|0|0|web',
  })

  const url = `${CONFIG.EAST_MONEY_API}?${params.toString()}`
  
  try {
    const res = await fetchWithTimeout(url)
    const data = await res.json()
    
    if (!data?.data?.diff) {
      console.warn('⚠️ 未获取到竞价数据，使用模拟数据')
      return generateMockData()
    }

    const stocks: JingJiaStock[] = data.data.diff.map((item: any) => {
      const code = String(item.f12)
      const changePercent = item.f3 ?? 0
      const volume = item.f6 ?? 0
      const price = item.f2 ?? 0
      const amount = (price * volume) / 10000 // 万元
      const turnoverRate = item.f8 ?? 0
      const marketCap = (item.f20 ?? 0) / 100000000 // 亿元
      const peTTM = item.f9 ?? 0
      const zhuLiJinE = (item.f62 ?? 0) / 10000 // 万元

      return {
        code,
        name: item.f14 ?? '未知',
        price,
        volume,
        amount: Math.round(amount * 100) / 100,
        changePercent,
        turnoverRate,
        zhuLiJinE: Math.round(zhuLiJinE * 100) / 100,
        zhuLiDirection: zhuLiJinE > 0 ? '流入' : zhuLiJinE < 0 ? '流出' : '平衡',
        limitUp: isLimitUp(changePercent, code),
        limitDown: isLimitDown(changePercent, code),
        board: getBoardByCode(code),
        concept: getConceptByCode(code),
        marketCap: Math.round(marketCap * 100) / 100,
        peTTM: Math.round(peTTM * 100) / 100,
        industry: getIndustryByCode(code),
      }
    })

    return stocks
  } catch (err) {
    console.warn('⚠️ 数据请求失败，使用模拟数据:', (err as Error).message)
    return generateMockData()
  }
}

// ========== 板块/题材/行业映射（简化版） ==========

/** 根据代码获取板块 */
function getBoardByCode(code: string): string {
  if (code.startsWith('60')) return '沪市主板'
  if (code.startsWith('00')) return '深市主板'
  if (code.startsWith('002')) return '中小板'
  if (code.startsWith('30')) return '创业板'
  if (code.startsWith('688')) return '科创板'
  if (code.startsWith('4') || code.startsWith('8')) return '北交所'
  return '其他'
}

/** 根据代码获取行业（简化映射） */
function getIndustryByCode(code: string): string {
  // 实际应该从API获取，这里简化处理
  const industries = [
    '半导体', '人工智能', '新能源', '医药生物', '消费电子',
    '汽车零部件', '军工', '通信', '计算机', '电力设备',
    '机械设备', '基础化工', '有色金属', '食品饮料', '房地产'
  ]
  return industries[parseInt(code.slice(-2)) % industries.length]
}

/** 根据代码获取概念（简化映射） */
function getConceptByCode(code: string): string[] {
  const conceptsMap: Record<string, string[]> = {
    '半导体': ['芯片', '国产替代', 'AI芯片'],
    '人工智能': ['AI', '大模型', '算力'],
    '新能源': ['光伏', '锂电池', '储能'],
    '医药生物': ['创新药', '医疗器械', '生物疫苗'],
    '消费电子': ['5G', '智能穿戴', '折叠屏'],
    '汽车零部件': ['新能源汽车', '特斯拉', '一体化压铸'],
    '军工': ['航天', '大飞机', '军工电子'],
    '通信': ['5G', '光通信', '卫星互联网'],
    '计算机': ['信创', '数字经济', '云计算'],
    '电力设备': ['特高压', '智能电网', '充电桩'],
  }
  const industry = getIndustryByCode(code)
  return conceptsMap[industry] || ['其他']
}

// ========== 模拟数据生成（当API不可用时） ==========

function generateMockData(): JingJiaStock[] {
  const mockStocks: JingJiaStock[] = []
  const stockNames = [
    { code: '600519', name: '贵州茅台' }, { code: '000858', name: '五粮液' },
    { code: '600036', name: '招商银行' }, { code: '601318', name: '中国平安' },
    { code: '300750', name: '宁德时代' }, { code: '000333', name: '美的集团' },
    { code: '600900', name: '长江电力' }, { code: '002415', name: '海康威视' },
    { code: '688981', name: '中芯国际' }, { code: '300059', name: '东方财富' },
    { code: '002594', name: '比亚迪' }, { code: '601012', name: '隆基绿能' },
    { code: '300124', name: '汇川技术' }, { code: '688111', name: '金山办公' },
    { code: '002230', name: '科大讯飞' }, { code: '300308', name: '中际旭创' },
    { code: '688041', name: '海光信息' }, { code: '002371', name: '北方华创' },
    { code: '300274', name: '阳光电源' }, { code: '601138', name: '工业富联' },
    { code: '688256', name: '寒武纪' }, { code: '002920', name: '德赛西威' },
    { code: '300502', name: '新易盛' }, { code: '688012', name: '中微公司' },
    { code: '002475', name: '立讯精密' }, { code: '300760', name: '迈瑞医疗' },
    { code: '000063', name: '中兴通讯' }, { code: '002049', name: '紫光国微' },
    { code: '688008', name: '澜起科技' }, { code: '300782', name: '卓胜微' },
  ]

  for (const s of stockNames) {
    const changePercent = Math.round((Math.random() * 10 - 3) * 100) / 100
    const price = Math.round(Math.random() * 200 * 100 + 1000) / 100
    const volume = Math.round(Math.random() * 50000 + 1000)
    const amount = (price * volume) / 10000
    const turnoverRate = Math.round(Math.random() * 5 * 100) / 100
    const zhuLiJinE = Math.round((Math.random() * 2000 - 500) * 100) / 100
    const marketCap = Math.round(Math.random() * 5000 * 100 + 500000) / 100

    mockStocks.push({
      code: s.code,
      name: s.name,
      price,
      volume,
      amount: Math.round(amount * 100) / 100,
      changePercent,
      turnoverRate,
      zhuLiJinE,
      zhuLiDirection: zhuLiJinE > 0 ? '流入' : zhuLiJinE < 0 ? '流出' : '平衡',
      limitUp: isLimitUp(changePercent, s.code),
      limitDown: isLimitDown(changePercent, s.code),
      board: getBoardByCode(s.code),
      concept: getConceptByCode(s.code),
      marketCap,
      peTTM: Math.round(Math.random() * 50 * 100 + 1000) / 100,
      industry: getIndustryByCode(s.code),
    })
  }

  return mockStocks
}

// ========== 数据分析 ==========

/** 分析板块统计 */
function analyzeBoards(stocks: JingJiaStock[]): BoardStats[] {
  const boardMap = new Map<string, JingJiaStock[]>()
  
  for (const stock of stocks) {
    const list = boardMap.get(stock.board) || []
    list.push(stock)
    boardMap.set(stock.board, list)
  }

  const stats: BoardStats[] = []
  for (const [boardName, boardStocks] of boardMap) {
    const upCount = boardStocks.filter(s => s.changePercent > 0).length
    const downCount = boardStocks.filter(s => s.changePercent < 0).length
    const limitUpCount = boardStocks.filter(s => s.limitUp).length
    const limitDownCount = boardStocks.filter(s => s.limitDown).length
    const avgChange = boardStocks.reduce((sum, s) => sum + s.changePercent, 0) / boardStocks.length
    const totalAmount = boardStocks.reduce((sum, s) => sum + s.amount, 0)
    const zhuLiNetInflow = boardStocks.reduce((sum, s) => sum + s.zhuLiJinE, 0)
    
    // 按涨跌幅排序取前5
    const topStocks = [...boardStocks].sort((a, b) => b.changePercent - a.changePercent).slice(0, 5)

    stats.push({
      boardName,
      type: '行业',
      stockCount: boardStocks.length,
      upCount,
      downCount,
      limitUpCount,
      limitDownCount,
      avgChangePercent: Math.round(avgChange * 100) / 100,
      totalAmount: Math.round(totalAmount * 100) / 100,
      zhuLiNetInflow: Math.round(zhuLiNetInflow * 100) / 100,
      topStocks,
    })
  }

  return stats.sort((a, b) => b.avgChangePercent - a.avgChangePercent).slice(0, 10)
}

/** 分析题材统计 */
function analyzeConcepts(stocks: JingJiaStock[]): ConceptStats[] {
  const conceptMap = new Map<string, JingJiaStock[]>()
  
  for (const stock of stocks) {
    for (const concept of stock.concept) {
      const list = conceptMap.get(concept) || []
      list.push(stock)
      conceptMap.set(concept, list)
    }
  }

  const stats: ConceptStats[] = []
  for (const [conceptName, conceptStocks] of conceptMap) {
    if (conceptStocks.length < 2) continue // 过滤少于2只的题材
    
    const limitUpCount = conceptStocks.filter(s => s.limitUp).length
    const avgChange = conceptStocks.reduce((sum, s) => sum + s.changePercent, 0) / conceptStocks.length
    const totalAmount = conceptStocks.reduce((sum, s) => sum + s.amount, 0)
    const zhuLiNetInflow = conceptStocks.reduce((sum, s) => sum + s.zhuLiJinE, 0)
    
    // 热度评分 = 涨停数*30 + 平均涨幅*5 + 主力净流入/100
    const heatScore = Math.min(100, Math.round(
      limitUpCount * 30 + 
      Math.max(0, avgChange) * 5 + 
      Math.max(0, zhuLiNetInflow) / 100
    ))

    const topStocks = [...conceptStocks].sort((a, b) => b.changePercent - a.changePercent).slice(0, 5)

    stats.push({
      conceptName,
      stockCount: conceptStocks.length,
      limitUpCount,
      avgChangePercent: Math.round(avgChange * 100) / 100,
      totalAmount: Math.round(totalAmount * 100) / 100,
      zhuLiNetInflow: Math.round(zhuLiNetInflow * 100) / 100,
      topStocks,
      heatScore,
    })
  }

  return stats.sort((a, b) => b.heatScore - a.heatScore).slice(0, 10)
}

/** 分析资金流向 */
function analyzeMoneyFlow(stocks: JingJiaStock[]): MoneyFlowStats {
  const sortedByInflow = [...stocks].sort((a, b) => b.zhuLiJinE - a.zhuLiJinE)
  
  return {
    totalAmount: Math.round(stocks.reduce((sum, s) => sum + s.amount, 0) * 100) / 100,
    zhuLiNetInflow: Math.round(stocks.reduce((sum, s) => sum + s.zhuLiJinE, 0) * 100) / 100,
    huYouNetInflow: 0, // 散户数据需要额外接口
    topInflowStocks: sortedByInflow.slice(0, 10),
    topOutflowStocks: sortedByInflow.slice(-10).reverse(),
  }
}

/** 分析涨停分类 */
function analyzeLimitUps(stocks: JingJiaStock[]): LimitUpCategory[] {
  const limitUpStocks = stocks.filter(s => s.limitUp)
  
  const categories: Record<string, JingJiaStock[]> = {
    '一字板': [],
    'T字板': [],
    '换手板': [],
    '趋势板': [],
  }

  for (const stock of limitUpStocks) {
    const type = getLimitUpType(stock)
    categories[type].push(stock)
  }

  return Object.entries(categories).map(([type, stocks]) => ({
    type: type as LimitUpCategory['type'],
    count: stocks.length,
    stocks,
  }))
}

/** 筛选强势股（竞价异动） */
function findStrongStocks(stocks: JingJiaStock[]): JingJiaStock[] {
  return stocks
    .filter(s => 
      s.changePercent > 3 &&           // 涨幅>3%
      s.volume > 10000 &&              // 成交量>1万手
      s.zhuLiJinE > 100 &&             // 主力净流入>100万
      s.marketCap > 30                 // 流通市值>30亿
    )
    .sort((a, b) => b.changePercent - a.changePercent)
    .slice(0, 20)
}

/** 生成自选关注列表（符合用户资金量30万） */
function generateWatchList(stocks: JingJiaStock[]): JingJiaStock[] {
  return stocks
    .filter(s => {
      // 30万资金能买的：股价适中，流动性好
      const canBuy = s.price * 100 * 1.1 <= 300000 // 一手价格不超过30万
      const goodLiquidity = s.volume > 5000         // 成交量>5000手
      const hasMomentum = s.changePercent > 2        // 涨幅>2%
      const hasInflow = s.zhuLiJinE > 50             // 主力净流入>50万
      return canBuy && goodLiquidity && hasMomentum && hasInflow
    })
    .sort((a, b) => b.changePercent - a.changePercent)
    .slice(0, 15)
}

// ========== 策略筛选 ==========

/** 科技成长股定义（5-6月策略） */
const TECH_GROWTH_INDUSTRIES = [
  '半导体', '人工智能', '新能源', '消费电子', '通信', 
  '计算机', '电力设备', '汽车零部件', '军工'
]

const TECH_GROWTH_CONCEPTS = [
  '芯片', 'AI', '算力', '大模型', '国产替代', 'AI芯片',
  '5G', '光通信', '信创', '数字经济', '云计算',
  '新能源汽车', '储能', '光伏', '智能电网',
  '机器人', '航天', '卫星互联网'
]

/** 筛选大容量科技成长股（5-6月策略） */
function filterTechGrowthStocks(stocks: JingJiaStock[]): JingJiaStock[] {
  return stocks
    .filter(s => {
      // 科技行业
      const isTechIndustry = TECH_GROWTH_INDUSTRIES.includes(s.industry)
      // 科技概念
      const hasTechConcept = s.concept.some(c => TECH_GROWTH_CONCEPTS.includes(c))
      // 大容量：流通市值 > 50亿
      const isLargeCap = s.marketCap > 50
      // 有业绩：市盈率合理（0 < PE < 100 或 PE为负但涨幅好）
      const hasEarnings = (s.peTTM > 0 && s.peTTM < 100) || (s.peTTM < 0 && s.changePercent > 5)
      // 有资金关注
      const hasMoneyFlow = s.zhuLiJinE > 0
      
      return (isTechIndustry || hasTechConcept) && isLargeCap && hasEarnings && hasMoneyFlow
    })
    .sort((a, b) => {
      // 按综合评分排序：涨幅 + 主力净流入/100
      const scoreA = a.changePercent * 2 + a.zhuLiJinE / 100
      const scoreB = b.changePercent * 2 + b.zhuLiJinE / 100
      return scoreB - scoreA
    })
    .slice(0, 20)
}

/** 筛选短线标的（7月策略） */
function filterShortTermStocks(stocks: JingJiaStock[]): JingJiaStock[] {
  return stocks
    .filter(s => {
      // 短线关注：高换手、有量、有题材
      const highTurnover = s.turnoverRate > 2       // 换手率>2%
      const goodVolume = s.volume > 20000            // 成交量>2万手
      const hasMomentum = Math.abs(s.changePercent) > 2  // 波动>2%
      const affordable = s.price * 100 * 1.1 <= 300000   // 30万资金能买
      const hasConcept = s.concept.length > 0 && s.concept[0] !== '其他'
      
      return highTurnover && goodVolume && hasMomentum && affordable && hasConcept
    })
    .sort((a, b) => b.turnoverRate - a.turnoverRate) // 按换手率排序
    .slice(0, 20)
}

/** 筛选业绩优良的标的 */
function filterGoodEarnings(stocks: JingJiaStock[]): JingJiaStock[] {
  return stocks
    .filter(s => {
      // PE在10-50之间，有业绩支撑
      const goodPE = s.peTTM > 10 && s.peTTM < 50
      // 有主力资金关注
      const hasInflow = s.zhuLiJinE > 0
      // 市值适中
      const goodSize = s.marketCap > 30 && s.marketCap < 2000
      return goodPE && hasInflow && goodSize
    })
    .sort((a, b) => b.zhuLiJinE - a.zhuLiJinE)
    .slice(0, 15)
}

// ========== 主函数 ==========

/** 生成完整的集合竞价报告 */
export async function generateJingJiaReport(): Promise<JingJiaReport> {
  console.log('📊 正在获取集合竞价数据...')
  
  const stocks = await fetchJingJiaData()
  const { date, time } = getNow()
  
  console.log(`✅ 获取到 ${stocks.length} 只股票数据`)
  
  // 基础统计
  const upCount = stocks.filter(s => s.changePercent > 0).length
  const downCount = stocks.filter(s => s.changePercent < 0).length
  const limitUpCount = stocks.filter(s => s.limitUp).length
  const limitDownCount = stocks.filter(s => s.limitDown).length
  const totalAmount = stocks.reduce((sum, s) => sum + s.amount, 0) / 10000 // 亿
  const zhuLiNetInflow = stocks.reduce((sum, s) => sum + s.zhuLiJinE, 0) / 10000 // 亿

  const report: JingJiaReport = {
    date,
    time,
    marketSummary: {
      totalStocks: stocks.length,
      upCount,
      downCount,
      limitUpCount,
      limitDownCount,
      totalAmount: Math.round(totalAmount * 100) / 100,
      zhuLiNetInflow: Math.round(zhuLiNetInflow * 100) / 100,
    },
    topBoards: analyzeBoards(stocks),
    topConcepts: analyzeConcepts(stocks),
    moneyFlow: analyzeMoneyFlow(stocks),
    limitUpCategories: analyzeLimitUps(stocks),
    strongStocks: findStrongStocks(stocks),
    watchList: generateWatchList(stocks),
    // 策略筛选
    techGrowthStocks: filterTechGrowthStocks(stocks),
    shortTermStocks: filterShortTermStocks(stocks),
    goodEarningsStocks: filterGoodEarnings(stocks),
  }

  return report
}

/** 格式化输出报告 */
export function formatReport(report: JingJiaReport): string {
  const lines: string[] = []
  const sep = '═'.repeat(60)
  const sep2 = '─'.repeat(60)

  lines.push(sep)
  lines.push(`  📊 A股集合竞价量价统计报告`)
  lines.push(`  📅 ${report.date}  ${report.time}`)
  lines.push(sep)
  lines.push('')

  // ===== 市场总览 =====
  lines.push('  【市场总览】')
  lines.push(sep2)
  lines.push(`  📈 上涨: ${report.marketSummary.upCount} 只`)
  lines.push(`  📉 下跌: ${report.marketSummary.downCount} 只`)
  lines.push(`  🚀 涨停: ${report.marketSummary.limitUpCount} 只`)
  lines.push(`  💥 跌停: ${report.marketSummary.limitDownCount} 只`)
  lines.push(`  💰 总竞价金额: ${report.marketSummary.totalAmount} 亿`)
  lines.push(`  🏦 主力净流入: ${report.marketSummary.zhuLiNetInflow > 0 ? '+' : ''}${report.marketSummary.zhuLiNetInflow} 亿`)
  lines.push('')

  // ===== 热门板块TOP10 =====
  lines.push('  【热门板块 TOP 10】')
  lines.push(sep2)
  lines.push(`  ${'板块'.padEnd(12)} ${'涨停'.padEnd(4)} ${'涨跌比'.padEnd(8)} ${'平均涨幅'.padEnd(8)} ${'主力净流入'.padEnd(10)}`)
  lines.push(`  ${'─'.repeat(12)} ${'─'.repeat(4)} ${'─'.repeat(8)} ${'─'.repeat(8)} ${'─'.repeat(10)}`)
  for (const board of report.topBoards) {
    const inflowStr = board.zhuLiNetInflow > 0 ? `+${board.zhuLiNetInflow}` : `${board.zhuLiNetInflow}`
    lines.push(`  ${board.boardName.padEnd(12)} ${String(board.limitUpCount).padEnd(4)} ${`${board.upCount}/${board.downCount}`.padEnd(8)} ${`${board.avgChangePercent}%`.padEnd(8)} ${inflowStr.padEnd(10)}`)
  }
  lines.push('')

  // ===== 热门题材TOP10 =====
  lines.push('  【热门题材 TOP 10】')
  lines.push(sep2)
  lines.push(`  ${'题材'.padEnd(12)} ${'热度'.padEnd(6)} ${'涨停'.padEnd(4)} ${'平均涨幅'.padEnd(8)} ${'主力净流入'.padEnd(10)}`)
  lines.push(`  ${'─'.repeat(12)} ${'─'.repeat(6)} ${'─'.repeat(4)} ${'─'.repeat(8)} ${'─'.repeat(10)}`)
  for (const concept of report.topConcepts) {
    const heatBar = '█'.repeat(Math.ceil(concept.heatScore / 10))
    const inflowStr = concept.zhuLiNetInflow > 0 ? `+${concept.zhuLiNetInflow}` : `${concept.zhuLiNetInflow}`
    lines.push(`  ${concept.conceptName.padEnd(12)} ${heatBar.padEnd(6)} ${String(concept.limitUpCount).padEnd(4)} ${`${concept.avgChangePercent}%`.padEnd(8)} ${inflowStr.padEnd(10)}`)
  }
  lines.push('')

  // ===== 资金流向 =====
  lines.push('  【资金流向】')
  lines.push(sep2)
  lines.push(`  💰 总竞价金额: ${report.moneyFlow.totalAmount.toFixed(2)} 万元`)
  lines.push(`  🏦 主力净流入: ${report.moneyFlow.zhuLiNetInflow > 0 ? '+' : ''}${report.moneyFlow.zhuLiNetInflow.toFixed(2)} 万元`)
  lines.push('')
  lines.push('  主力流入 TOP 5:')
  for (const s of report.moneyFlow.topInflowStocks.slice(0, 5)) {
    lines.push(`    ✅ ${s.name}(${s.code}) +${s.zhuLiJinE}万 涨幅${s.changePercent}%`)
  }
  lines.push('')
  lines.push('  主力流出 TOP 5:')
  for (const s of report.moneyFlow.topOutflowStocks.slice(0, 5)) {
    lines.push(`    ❌ ${s.name}(${s.code}) ${s.zhuLiJinE}万 涨幅${s.changePercent}%`)
  }
  lines.push('')

  // ===== 涨停分类 =====
  lines.push('  【涨停分类】')
  lines.push(sep2)
  for (const cat of report.limitUpCategories) {
    if (cat.count > 0) {
      lines.push(`  ${cat.type}: ${cat.count} 只`)
      for (const s of cat.stocks.slice(0, 5)) {
        lines.push(`    🏆 ${s.name}(${s.code}) 涨幅${s.changePercent}% 换手${s.turnoverRate}%`)
      }
    }
  }
  lines.push('')

  // ===== 强势股（竞价异动） =====
  lines.push('  【竞价异动强势股】')
  lines.push(sep2)
  if (report.strongStocks.length === 0) {
    lines.push('  📭 暂无符合条件的强势股')
  } else {
    for (const s of report.strongStocks) {
      const dir = s.zhuLiDirection === '流入' ? '📗' : '📕'
      lines.push(`  ${dir} ${s.name}(${s.code}) 涨幅${s.changePercent}% 主力${s.zhuLiJinE}万 换手${s.turnoverRate}%`)
    }
  }
  lines.push('')

  // ===== 自选关注（适合30万资金） =====
  lines.push('  【自选关注 · 适合30万资金】')
  lines.push(sep2)
  if (report.watchList.length === 0) {
    lines.push('  📭 暂无符合条件的关注标的')
  } else {
    for (const s of report.watchList) {
      const buyAmount = s.price * 100 * 1.1 // 买一手所需资金
      lines.push(`  ⭐ ${s.name}(${s.code}) 现价${s.price}元 涨幅${s.changePercent}% 一手约${buyAmount.toFixed(0)}元`)
    }
  }
  lines.push('')
  // ===== 科技成长股（5-6月策略） =====
  const techStocks = report.techGrowthStocks || []
  if (techStocks.length > 0) {
    lines.push('  【🎯 5-6月策略 · 大容量科技成长股】')
    lines.push(sep2)
    lines.push(`  ${'名称'.padEnd(14)} ${'涨幅'.padEnd(8)} ${'主力净额'.padEnd(12)} ${'市值(亿)'.padEnd(10)} ${'PE'.padEnd(8)} ${'换手'.padEnd(6)}`)
    lines.push(`  ${'─'.repeat(14)} ${'─'.repeat(8)} ${'─'.repeat(12)} ${'─'.repeat(10)} ${'─'.repeat(8)} ${'─'.repeat(6)}`)
    for (const s of techStocks) {
      const inflowStr = s.zhuLiJinE > 0 ? `+${s.zhuLiJinE}` : `${s.zhuLiJinE}`
      lines.push(`  ${s.name.padEnd(14)} ${`${s.changePercent}%`.padEnd(8)} ${inflowStr.padEnd(12)} ${String(s.marketCap).padEnd(10)} ${String(s.peTTM).padEnd(8)} ${`${s.turnoverRate}%`.padEnd(6)}`)
    }
    lines.push('')
  }

  // ===== 短线标的（7月策略） =====
  const shortStocks = report.shortTermStocks || []
  if (shortStocks.length > 0) {
    lines.push('  【⚡ 7月策略 · 短线交易标的】')
    lines.push(sep2)
    lines.push(`  ${'名称'.padEnd(14)} ${'涨幅'.padEnd(8)} ${'换手'.padEnd(8)} ${'成交量(手)'.padEnd(12)} ${'主力净额'.padEnd(12)} ${'题材'.padEnd(12)}`)
    lines.push(`  ${'─'.repeat(14)} ${'─'.repeat(8)} ${'─'.repeat(8)} ${'─'.repeat(12)} ${'─'.repeat(12)} ${'─'.repeat(12)}`)
    for (const s of shortStocks) {
      const inflowStr = s.zhuLiJinE > 0 ? `+${s.zhuLiJinE}` : `${s.zhuLiJinE}`
      const concept = s.concept[0] || ''
      lines.push(`  ${s.name.padEnd(14)} ${`${s.changePercent}%`.padEnd(8)} ${`${s.turnoverRate}%`.padEnd(8)} ${String(s.volume).padEnd(12)} ${inflowStr.padEnd(12)} ${concept.padEnd(12)}`)
    }
    lines.push('')
  }

  // ===== 业绩优良标的 =====
  const earnStocks = report.goodEarningsStocks || []
  if (earnStocks.length > 0) {
    lines.push('  【📈 业绩优良标的（PE合理+主力流入）】')
    lines.push(sep2)
    for (const s of earnStocks.slice(0, 10)) {
      lines.push(`  ✅ ${s.name}(${s.code}) PE:${s.peTTM} 涨幅${s.changePercent}% 主力${s.zhuLiJinE}万`)
    }
    lines.push('')
  }

  lines.push(sep)
  lines.push('  💡 策略提示:')
  lines.push('     📅 5-6月 → 大容量业绩科技成长股（半导体/AI/新能源）')
  lines.push('     📅 7月   → 转短线交易（高换手/有量/有题材）')
  lines.push(`  💰 当前资金: 30万 | 建议仓位: 单票不超过6万(20%)`)
  lines.push(`  📊 每日9:25自动运行 | bun run src/market/index.ts --schedule`)
  lines.push(sep)

  return lines.join('\n')
}
