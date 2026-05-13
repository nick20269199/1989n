"""
market_pool — A股本地数据池
=============================
本地缓存 + 增量更新，一次性建仓后不再依赖批量API。

用法:
  from market_pool import MarketPool
  pool = MarketPool()
  pool.update_all()                     # 全市场增量更新
  kline = pool.get_kline('002156')      # 获取日K线
  quotes = pool.get_quotes(['002156'])  # 获取实时行情
"""

from .pool import MarketPool

__all__ = ["MarketPool"]
