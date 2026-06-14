"""集中存放示例/mock 数据入口。

⚠️ 这是**合成示例数据**，仅用于离线演示与测试，**不代表真实行情**。
仪表盘默认禁止显示 mock 数据；只有显式选择 demo 模式（数据源 = sample）时才会使用，
且页面顶部会显示"当前为示例数据"。

真实数据请用 Baostock / AkShare / Wind / iFinD / miniQMT 等数据源。
"""

from aqs.config import SystemConfig, DEFAULT_CONFIG
from aqs.data.market_data import MarketDataManager
from aqs.data.sample_data import generate_dataset


def get_mock_manager(config: SystemConfig = DEFAULT_CONFIG, **kwargs) -> MarketDataManager:
    """返回基于合成数据的 MarketDataManager（演示用）。"""
    mgr = MarketDataManager(config)
    mgr.load_dataset(generate_dataset(**kwargs))
    return mgr


if __name__ == "__main__":
    m = get_mock_manager()
    print("示例数据(mock) 标的:", m.symbols)
    print("⚠️ 这是合成数据，不代表真实行情。")
