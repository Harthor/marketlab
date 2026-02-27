from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat18RSIBBRegimeReclaim_v1(IStrategy):
    """
    Mean reversion 1h: oversold + reclaim with regime/context filters.

    Idea:
    - Only trade when broader context is not strongly bearish.
    - Wait for an oversold signal, then require a reclaim confirmation candle.
    - Exit quickly on mean reversion or invalidation.
    """

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "1h"

    minimal_roi = {"0": 0.02}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 240

    atr_stop_mult: float = 1.7

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)

        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lower"] = bb["lower"]
        dataframe["bb_mid"] = bb["mid"]

        dataframe["ema200_slope_ok"] = dataframe["ema200"] >= dataframe["ema200"].shift(10)
        dataframe["atr_ratio"] = (dataframe["atr"] / dataframe["close"]).fillna(0.0)
        dataframe["dist_ema20"] = ((dataframe["close"] - dataframe["ema20"]).abs() / dataframe["ema20"]).fillna(0.0)

        # Oversold must happen first, then reclaim on next candle(s).
        dataframe["oversold_now"] = (dataframe["rsi"] < 35) | (dataframe["close"] < dataframe["bb_lower"])
        dataframe["oversold_recent"] = (
            dataframe["oversold_now"].shift(1).fillna(False)
            | dataframe["oversold_now"].shift(2).fillna(False)
        )

        dataframe["reclaim_confirm"] = (
            (dataframe["close"] > dataframe["open"])
            & (dataframe["close"] > dataframe["bb_lower"])
            & (dataframe["close"] >= dataframe["ema20"] * 0.995)
            & (dataframe["rsi"] > dataframe["rsi"].shift(1))
        )

        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        regime_ok = (dataframe["close"] > dataframe["ema200"]) | dataframe["ema200_slope_ok"]
        adx_ok = (dataframe["adx"] >= 12) & (dataframe["adx"] <= 30)
        volatility_ok = (dataframe["atr_ratio"] >= 0.004) & (dataframe["atr_ratio"] <= 0.035)
        structure_ok = dataframe["dist_ema20"] < 0.04

        dataframe.loc[
            (
                regime_ok
                & adx_ok
                & volatility_ok
                & structure_ok
                & dataframe["oversold_recent"]
                & dataframe["reclaim_confirm"]
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_bb_regime_reclaim_v1")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        take_profit = (dataframe["close"] > dataframe["bb_mid"]) | (dataframe["rsi"] > 54)
        invalidation = (dataframe["close"] < dataframe["ema20"]) & (dataframe["rsi"] < 45)

        dataframe.loc[
            (take_profit | invalidation),
            ["exit_long", "exit_tag"],
        ] = (1, "mean_reversion_exit_v1")
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
