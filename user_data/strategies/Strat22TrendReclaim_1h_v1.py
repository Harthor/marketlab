from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat22TrendReclaim_1h_v1(IStrategy):
    """1h trend pullback/reclaim candidate to complement mean reversion baseline."""

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "1h"

    minimal_roi = {"0": 0.02}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 240

    atr_stop_mult: float = 1.8
    max_ema20_extension: float = 0.018

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = dataframe["ema200"] > dataframe["ema200"].shift(12)

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = (dataframe["atr"] / dataframe["close"]).fillna(0.0)

        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_upperband"] = bb["upper"]

        dataframe["pullback_to_ema20"] = (dataframe["low"] <= dataframe["ema20"] * 1.002) & (
            dataframe["close"] >= dataframe["ema50"]
        )
        dataframe["bullish_reclaim"] = (
            (dataframe["close"] > dataframe["ema20"])
            & (dataframe["close"] > dataframe["open"])
            & (dataframe["close"] > dataframe["close"].shift(1))
        )
        dataframe["rsi_reclaim"] = (dataframe["rsi"] > 50) & (dataframe["rsi"].shift(1) <= 50)
        dataframe["ema20_extension"] = (
            (dataframe["close"] - dataframe["ema20"]).abs() / dataframe["ema20"]
        ).fillna(0.0)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema200"])
                & (dataframe["ema200_slope_up"])
                & (dataframe["ema20"] > dataframe["ema50"])
                & (dataframe["adx"] > 15)
                & (dataframe["adx"] < 35)
                & (dataframe["atr_pct"] > 0.004)
                & (dataframe["atr_pct"] < 0.03)
                & (dataframe["pullback_to_ema20"])
                & (dataframe["bullish_reclaim"])
                & (dataframe["rsi_reclaim"])
                & (dataframe["ema20_extension"] < self.max_ema20_extension)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "trend_reclaim_1h_v1")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema20"])
                | (dataframe["rsi"] < 46)
                | (dataframe["close"] > dataframe["bb_upperband"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "trend_reclaim_exit_1h_v1")
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
