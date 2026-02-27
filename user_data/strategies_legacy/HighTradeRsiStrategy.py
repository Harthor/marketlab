from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class HighTradeRsiStrategy(IStrategy):
    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "5m"

    # Tight ROI/stop settings to close positions faster and allow more cycles.
    minimal_roi = {"0": 0.003}
    stoploss = -0.03
    trailing_stop = False

    process_only_new_candles = True
    startup_candle_count: int = 30

    use_exit_signal = True
    exit_profit_only = False
    ignore_roi_if_entry_signal = False

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["rsi_fast"] = ta.RSI(dataframe, timeperiod=4)
        dataframe["ema_fast"] = ta.EMA(dataframe, timeperiod=9)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] < 48)
                & (dataframe["rsi_fast"] < 40)
                & (dataframe["close"] < dataframe["ema_fast"] * 1.001)
                & (dataframe["volume"] > 0)
            ),
            "enter_long",
        ] = 1
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["rsi"] > 55)
                | (dataframe["rsi_fast"] > 70)
                | (dataframe["close"] > dataframe["ema_fast"] * 1.004)
            ),
            "exit_long",
        ] = 1
        return dataframe
