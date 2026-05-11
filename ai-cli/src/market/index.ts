#!/usr/bin/env bun
/**
 * A股集合竞价量价统计工具
 * 
 * 用法:
 *   bun run src/market/index.ts              # 立即运行
 *   bun run src/market/index.ts --watch      # 持续监控(每5分钟刷新)
 *   bun run src/market/index.ts --schedule   # 定时在9:25运行
 * 
 * 功能:
 *   - 9:25分集合竞价数据抓取
 *   - 板块/题材/资金流向统计
 *   - 涨停分类(一字板/T字板/换手板/趋势板)
 *   - 强势股筛选(竞价异动)
 *   - 适合30万资金的自选关注
 */

import { generateJingJiaReport, formatReport } from './jingjia.ts'

const args = process.argv.slice(2)
const isWatch = args.includes('--watch')
const isSchedule = args.includes('--schedule')

/** 等待到指定时间 */
function waitUntil(targetHour: number, targetMin: number): Promise<void> {
  return new Promise((resolve) => {
    const now = new Date()
    const target = new Date(now)
    target.setHours(targetHour, targetMin, 0, 0)
    
    if (target <= now) {
      target.setDate(target.getDate() + 1) // 如果已过时间，等明天
    }
    
    const msUntilTarget = target.getTime() - now.getTime()
    const hours = Math.floor(msUntilTarget / 3600000)
    const mins = Math.floor((msUntilTarget % 3600000) / 60000)
    
    console.log(`⏰ 等待到 ${String(targetHour).padStart(2, '0')}:${String(targetMin).padStart(2, '0')} 运行...`)
    console.log(`   (还有 ${hours} 小时 ${mins} 分钟)`)
    
    setTimeout(resolve, msUntilTarget)
  })
}

/** 执行一次分析 */
async function runOnce() {
  try {
    const report = await generateJingJiaReport()
    const output = formatReport(report)
    console.log(output)
    
    // 同时保存到文件
    const filename = `jingjia_${report.date}_${report.time.replace(/:/g, '')}.txt`
    await Bun.write(filename, output)
    console.log(`\n📁 报告已保存到: ${filename}`)
    
    return report
  } catch (err) {
    console.error('❌ 运行出错:', err)
    return null
  }
}

/** 持续监控模式 */
async function watchMode() {
  console.log('👀 持续监控模式 (每5分钟刷新)')
  console.log('按 Ctrl+C 退出\n')
  
  while (true) {
    await runOnce()
    console.log('\n⏳ 5分钟后刷新...\n')
    await new Promise(resolve => setTimeout(resolve, 5 * 60 * 1000))
  }
}

/** 定时模式 - 每天9:25运行 */
async function scheduleMode() {
  console.log('⏰ 定时模式 - 每天9:25自动运行')
  
  while (true) {
    await waitUntil(9, 25)
    console.log('\n🔔 集合竞价数据已出炉!\n')
    await runOnce()
    
    // 运行完后等24小时再继续
    console.log('\n⏰ 等待明天9:25...\n')
    await new Promise(resolve => setTimeout(resolve, 24 * 60 * 60 * 1000))
  }
}

// ========== 主入口 ==========

async function main() {
  console.log(`
╔══════════════════════════════════════════╗
║     📊 A股集合竞价量价统计工具            ║
║     ─────────────────────                ║
║     资金: 30万                           ║
║     策略: 5-6月大容量科技成长            ║
║           7月转短线                      ║
╚══════════════════════════════════════════╝
  `)

  if (isSchedule) {
    await scheduleMode()
  } else if (isWatch) {
    await watchMode()
  } else {
    await runOnce()
  }
}

main().catch(console.error)
