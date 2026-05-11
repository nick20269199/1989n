// ========== 数据类型定义 ==========

/** 集合竞价个股数据 */
export interface JingJiaStock {
  code: string           // 股票代码
  name: string           // 股票名称
  price: number          // 竞价价格
  volume: number         // 竞价量(手)
  amount: number         // 竞价金额(万元)
  changePercent: number  // 涨跌幅%
  turnoverRate: number   // 换手率%
  zhuLiJinE: number      // 主力净额(万元)
  zhuLiDirection: '流入' | '流出' | '平衡'
  limitUp: boolean       // 是否涨停
  limitDown: boolean     // 是否跌停
  board: string          // 所属板块
  concept: string[]      // 所属概念/题材
  marketCap: number      // 流通市值(亿元)
  peTTM: number          // 市盈率TTM
  industry: string       // 所属行业
}

/** 板块竞价统计 */
export interface BoardStats {
  boardName: string
  type: '行业' | '概念' | '地域'
  stockCount: number
  upCount: number
  downCount: number
  limitUpCount: number
  limitDownCount: number
  avgChangePercent: number
  totalAmount: number       // 总竞价金额(万元)
  zhuLiNetInflow: number    // 主力净流入(万元)
  topStocks: JingJiaStock[] // 板块内前排个股
}

/** 题材竞价统计 */
export interface ConceptStats {
  conceptName: string
  stockCount: number
  limitUpCount: number
  avgChangePercent: number
  totalAmount: number
  zhuLiNetInflow: number
  topStocks: JingJiaStock[]
  heatScore: number  // 热度评分 0-100
}

/** 资金流向统计 */
export interface MoneyFlowStats {
  totalAmount: number          // 总竞价金额
  zhuLiNetInflow: number       // 主力净流入
  huYouNetInflow: number       // 散户净流入
  topInflowStocks: JingJiaStock[]   // 流入前10
  topOutflowStocks: JingJiaStock[]  // 流出前10
}

/** 涨停分类 */
export interface LimitUpCategory {
  type: '一字板' | 'T字板' | '换手板' | '趋势板'
  count: number
  stocks: JingJiaStock[]
}

/** 完整竞价报告 */
export interface JingJiaReport {
  date: string               // 日期 YYYY-MM-DD
  time: string               // 时间 HH:mm:ss
  marketSummary: {
    totalStocks: number
    upCount: number
    downCount: number
    limitUpCount: number
    limitDownCount: number
    totalAmount: number       // 总竞价金额(亿)
    zhuLiNetInflow: number    // 主力净流入(亿)
  }
  topBoards: BoardStats[]     // 热门板块TOP10
  topConcepts: ConceptStats[] // 热门题材TOP10
  moneyFlow: MoneyFlowStats
  limitUpCategories: LimitUpCategory[]
  strongStocks: JingJiaStock[]  // 强势股(竞价异动)
  watchList: JingJiaStock[]     // 自选关注
  // 策略筛选扩展
  techGrowthStocks?: JingJiaStock[]   // 5-6月科技成长股
  shortTermStocks?: JingJiaStock[]    // 7月短线标的
  goodEarningsStocks?: JingJiaStock[] // 业绩优良标的
}
