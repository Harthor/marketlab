from pandas import DataFrame

from freqtrade.strategy import IStrategy


class Strat04FundingCarryFutures(IStrategy):
    """
    Funding carry placeholder for futures.

    This strategy intentionally does not generate entries in backtesting because
    funding-rate historical logic requires an external source/feature pipeline.
    Runner scripts should flag this as live-only by default.
    """

    INTERFACE_VERSION = 3
    can_short: bool = True
    timeframe = "1h"

    minimal_roi = {"0": 0.01}
    stoploss = -0.1

    process_only_new_candles = True
    startup_candle_count: int = 50

    requires_external_data: bool = True

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # Deliberately disabled for standard backtesting.
        dataframe["enter_long"] = 0
        dataframe["enter_short"] = 0
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["exit_long"] = 0
        dataframe["exit_short"] = 0
        return dataframe
