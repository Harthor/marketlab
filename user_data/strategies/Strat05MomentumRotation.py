from pandas import DataFrame
import talib.abstract as ta

from freqtrade.strategy import IStrategy


class Strat05MomentumRotation(IStrategy):
    """
    Momentum rotation strategy.

    Intended workflow:
    1) Run user_data/scripts/rotation_select.py to generate top-N whitelist.
    2) Backtest this strategy using the generated whitelist.
    """

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "1d"

    minimal_roi = {"0": 0.06}
    stoploss = -0.12

    process_only_new_candles = True
    startup_candle_count: int = 60

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["roc28"] = ta.ROC(dataframe, timeperiod=28)
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["roc28"] > 0)
                & (dataframe["close"] > dataframe["ema20"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "momentum_rotation")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["roc28"] < 0)
                | (dataframe["close"] < dataframe["ema20"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "momentum_rotation_exit")
        return dataframe
