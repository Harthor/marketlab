from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, informative, stoploss_from_absolute


class Strat01RegimeMACross(IStrategy):
    """
    Regime + MA Cross
    - Main timeframe: 4h
    - Informative timeframe: 1d
    """

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "4h"

    minimal_roi = {"0": 0.03}
    stoploss = -0.25
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 220

    atr_stop_mult: float = 2.5

    @informative("1d")
    def populate_indicators_1d(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["sma200"] = ta.SMA(dataframe, timeperiod=200)
        return dataframe

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["rsi_min_5"] = dataframe["rsi"].rolling(5).min()
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close_1d"] > dataframe["sma200_1d"])
                & (dataframe["ema20"] > dataframe["ema50"])
                & (dataframe["rsi"] > 50)
                & (dataframe["rsi_min_5"] < 45)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "regime_ma_cross")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["ema20"] < dataframe["ema50"])
                | (dataframe["close"] < dataframe["ema50"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "ma_cross_down")
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
