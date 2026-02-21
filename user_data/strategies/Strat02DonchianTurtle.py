from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import BooleanParameter, IntParameter, IStrategy, stoploss_from_absolute


class Strat02DonchianTurtle(IStrategy):
    """Donchian Turtle breakout (4h)."""

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "4h"

    minimal_roi = {"0": 0.04}
    stoploss = -0.3
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 80

    enable_adx_filter = BooleanParameter(default=True, space="buy")
    adx_threshold = IntParameter(15, 30, default=18, space="buy")

    atr_stop_mult: float = 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["donchian_high_20"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["donchian_low_10"] = dataframe["low"].rolling(10).min().shift(1)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        base_condition = (
            (dataframe["close"] > dataframe["donchian_high_20"])
            & (dataframe["volume"] > 0)
        )

        adx_condition = dataframe["adx"] > self.adx_threshold.value
        condition = base_condition & (~self.enable_adx_filter.value | adx_condition)

        dataframe.loc[condition, ["enter_long", "enter_tag"]] = (1, "donchian_breakout")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (dataframe["close"] < dataframe["donchian_low_10"]),
            ["exit_long", "exit_tag"],
        ] = (1, "donchian_exit")
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
