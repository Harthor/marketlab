from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat07DonchianPullbackTrend_v1(IStrategy):
    """
    Donchian breakout + pullback continuation prototype.

    Assumptions:
    - We only trade aligned trends (EMA200 up, EMA20 > EMA50, ADX healthy).
    - Breakout signal is validated first, then pullback entry reduces chasing highs.
    - ATR stop manages volatility spikes.
    """

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "1h"

    minimal_roi = {"0": 0.02}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 260

    atr_stop_mult: float = 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = dataframe["ema200"] > dataframe["ema200"].shift(10)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        dataframe["donchian_high_20"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["donchian_low_10"] = dataframe["low"].rolling(10).min().shift(1)

        # Breakout happened in recent candles -> then wait pullback entry.
        breakout = dataframe["close"] > dataframe["donchian_high_20"]
        dataframe["recent_breakout"] = breakout.rolling(6).max().fillna(0) > 0
        dataframe["pullback_to_ema20"] = (dataframe["low"] <= dataframe["ema20"]) | (dataframe["close"] <= dataframe["ema20"])
        dataframe["bullish_rebound"] = dataframe["close"] > dataframe["open"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema200"])
                & (dataframe["ema200_slope_up"])
                & (dataframe["ema20"] > dataframe["ema50"])
                & (dataframe["adx"] > 18)
                & (dataframe["recent_breakout"])
                & (dataframe["pullback_to_ema20"])
                & (dataframe["bullish_rebound"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "donchian_pullback_trend_v1")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema20"])
                | (dataframe["close"] < dataframe["donchian_low_10"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "donchian_pullback_exit_v1")
        return dataframe

    def custom_stoploss(
        self,
        pair: str,
        trade: Trade,
        current_time: datetime,
        current_rate: float,
        current_profit: float,
        after_fill: bool,
        **kwargs,
    ) -> float:
        if not self.dp:
            return 1

        dataframe, _ = self.dp.get_analyzed_dataframe(pair, self.timeframe)
        if dataframe.empty:
            return 1

        atr = dataframe.iloc[-1].get("atr")
        if atr is None or atr <= 0:
            return 1

        stop_rate = current_rate - (atr * self.atr_stop_mult)
        return stoploss_from_absolute(
            stop_rate,
            current_rate=current_rate,
            is_short=trade.is_short,
            leverage=trade.leverage,
        )
