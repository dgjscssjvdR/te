import os
import logging
import ccxt
import pandas as pd
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_KEY = os.getenv('BINANCE_API_KEY')
SECRET_KEY = os.getenv('BINANCE_SECRET_KEY')
SYMBOL = os.getenv('SYMBOL', 'BTC/USDT')
FAST_MA = int(os.getenv('FAST_MA', 5))
SLOW_MA = int(os.getenv('SLOW_MA', 20))
DRY_RUN = os.getenv('DRY_RUN', 'true').lower() == 'true'

if not API_KEY or not SECRET_KEY:
    logger.error("请设置 BINANCE_API_KEY 和 BINANCE_SECRET_KEY")
    exit(1)

exchange = ccxt.binance({
    'apiKey': API_KEY,
    'secret': SECRET_KEY,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

def get_klines(symbol, timeframe='1h', limit=100):
    try:
        ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['close'] = df['close'].astype(float)
        return df
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return None

def get_balance():
    try:
        balance = exchange.fetch_balance()
        return balance['USDT']['free']
    except Exception as e:
        logger.error(f"获取余额失败: {e}")
        return 0

def get_position(symbol):
    try:
        balance = exchange.fetch_balance()
        symbol_clean = symbol.split('/')[0]
        return balance[symbol_clean]['free']
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return 0

def create_order(symbol, side, amount):
    try:
        if side == 'buy':
            order = exchange.create_market_buy_order(symbol, amount)
        else:
            order = exchange.create_market_sell_order(symbol, amount)
        logger.info(f"订单成功: {order}")
        return order
    except Exception as e:
        logger.error(f"下单失败: {e}")
        return None

def main():
    logger.info(f"启动币安机器人 | 模拟模式: {DRY_RUN} | 交易对: {SYMBOL}")
    df = get_klines(SYMBOL)
    if df is None or len(df) < SLOW_MA:
        logger.error("数据不足")
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
        logger.info("无信号")
        return

    balance = get_balance()
    position = get_position(SYMBOL)
    logger.info(f"USDT余额: {balance:.2f}, 持仓: {position:.6f}")

    if DRY_RUN:
        logger.warning(f"【模拟模式】触发 {signal} 信号，价格 {latest_price}，不下单")
        return

    logger.warning("!!! 实盘模式 !!!")
    try:
        if signal == "BUY" and position == 0:
            amount = 100 / latest_price
            create_order(SYMBOL, 'buy', amount)
        elif signal == "SELL" and position > 0:
            create_order(SYMBOL, 'sell', position)
        else:
            logger.info("条件不满足，跳过")
    except Exception as e:
        logger.error(f"执行失败: {e}")

if __name__ == "__main__":
    main()
