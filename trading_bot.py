import os
import logging
from datetime import datetime, timedelta
import pandas as pd
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.data.historical import CryptoHistoricalDataClient
from alpaca.data.requests import CryptoBarsRequest
from alpaca.data.timeframe import TimeFrame

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_KEY = os.getenv('APCA_API_KEY_ID')
SECRET_KEY = os.getenv('APCA_SECRET_KEY_ID')
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'
SYMBOL = os.getenv('SYMBOL', 'BTC/USD')
FAST_MA = int(os.getenv('FAST_MA', 5))
SLOW_MA = int(os.getenv('SLOW_MA', 20))

if not API_KEY or not SECRET_KEY:
    logger.error("错误：未设置 API Key，请在 GitHub Secrets 中添加")
    exit(1)

trading_client = TradingClient(API_KEY, SECRET_KEY, paper=True)
data_client = CryptoHistoricalDataClient()

def get_prices():
    try:
        now = datetime.now()
        start = now - timedelta(days=30)
        symbol_clean = SYMBOL.replace('/', '')
        request = CryptoBarsRequest(
            symbol_or_symbols=symbol_clean,
            timeframe=TimeFrame.Hour,
            start=start,
            end=now
        )
        bars = data_client.get_crypto_bars(request)
        df = bars.df
        if df.empty:
            return None
        df = df.reset_index()
        if 'symbol' in df.columns:
            df = df[df['symbol'] == symbol_clean]
        df = df.sort_values('timestamp')
        df['close'] = df['close'].astype(float)
        return df
    except Exception as e:
        logger.error(f"获取数据失败: {e}")
        return None

def get_position_qty():
    try:
        positions = trading_client.get_all_positions()
        symbol_clean = SYMBOL.replace('/', '')
        for pos in positions:
            if pos.symbol == symbol_clean:
                return float(pos.qty)
        return 0
    except Exception as e:
        logger.warning(f"查询持仓失败: {e}")
        return 0

def main():
    logger.info(f"启动机器人 | 模拟模式: {DRY_RUN} | 交易对: {SYMBOL}")
    df = get_prices()
    if df is None or len(df) < SLOW_MA:
        logger.error("数据不足，无法计算均线")
        return

    df['fast_ma'] = df['close'].rolling(window=FAST_MA).mean()
    df['slow_ma'] = df['close'].rolling(window=SLOW_MA).mean()
    
    last_two = df.tail(2)
    if len(last_two) < 2:
        return
        
    prev_fast, prev_slow = last_two.iloc[0]['fast_ma'], last_two.iloc[0]['slow_ma']
    curr_fast, curr_slow = last_two.iloc[1]['fast_ma'], last_two.iloc[1]['slow_ma']
    latest_price = last_two.iloc[1]['close']

    logger.info(f"最新价: {latest_price:.2f} | 快线: {curr_fast:.2f} | 慢线: {curr_slow:.2f}")

    signal = None
    if prev_fast <= prev_slow and curr_fast > curr_slow:
        signal = "BUY"
    elif prev_fast >= prev_slow and curr_fast < curr_slow:
        signal = "SELL"

    if not signal:
        logger.info("无交叉信号，保持等待")
        return

    qty = get_position_qty()
    logger.info(f"当前持仓: {qty}")

    if DRY_RUN:
        logger.warning(f"【模拟模式】触发 {signal} 信号，价格 {latest_price}，但不执行真实下单")
        return

    logger.warning("!!! 实盘模式已开启，即将下单 !!!")
    try:
        if signal == "BUY" and qty > 0:
            logger.info("已有持仓，跳过重复买入")
            return
        if signal == "SELL" and qty <= 0:
            logger.info("无持仓可卖，跳过")
            return

        symbol_clean = SYMBOL.replace('/', '')
        if signal == "BUY":
            order_data = MarketOrderRequest(
                symbol=symbol_clean,
                notional=100,
                side=OrderSide.BUY,
                time_in_force=TimeInForce.GTC
            )
        else:
            order_data = MarketOrderRequest(
                symbol=symbol_clean,
                qty=qty,
                side=OrderSide.SELL,
                time_in_force=TimeInForce.GTC
            )
        order = trading_client.submit_order(order_data)
        logger.info(f"订单提交成功: {order}")
    except Exception as e:
        logger.error(f"交易执行失败: {e}")

if __name__ == "__main__":
    main()
