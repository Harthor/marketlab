from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat03RSIBBMeanReversion(IStrategy):
    """Controlled mean reversion using RSI + Bollinger Bands."""

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "1h"

    minimal_roi = {"0": 0.02}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 150

    atr_stop_mult: float = 1.8

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema100"] = ta.EMA(dataframe, timeperiod=100)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)

        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bb["lower"]
        dataframe["bb_middleband"] = bb["mid"]

        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema100"])
                & (dataframe["rsi"] < 40)
                & (dataframe["close"] < dataframe["bb_lowerband"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_bb_meanrev")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] > 55)
                | (dataframe["close"] > dataframe["bb_middleband"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "mean_reversion_exit")
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
