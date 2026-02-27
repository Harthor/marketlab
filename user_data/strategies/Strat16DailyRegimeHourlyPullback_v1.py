from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair, stoploss_from_absolute


class Strat16DailyRegimeHourlyPullback_v1(IStrategy):
    """
    Daily-regime / hourly-pullback prototype.

    - HTF filter (1d): only long when close_1d > SMA200_1d and SMA200_1d slope is positive.
    - LTF execution (1h): pullback to EMA20 with bullish rebound confirmation.
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

    @property
    def informative_pairs(self):
        if not self.dp:
            return []
        return [(pair, "1d") for pair in self.dp.current_whitelist()]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        if self.dp:
            inf = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="1d")
            inf["sma200"] = ta.SMA(inf, timeperiod=200)
            inf["sma200_slope_up"] = inf["sma200"] > inf["sma200"].shift(5)
            inf["regime_ok"] = (inf["close"] > inf["sma200"]) & inf["sma200_slope_up"]
            dataframe = merge_informative_pair(dataframe, inf, self.timeframe, "1d", ffill=True)
        else:
            dataframe["regime_ok_1d"] = False

        dataframe["regime_ok_1d"] = dataframe["regime_ok_1d"].fillna(False).astype(bool)
        dataframe["pullback_to_ema20"] = (dataframe["low"] <= dataframe["ema20"]) | (dataframe["close"] <= dataframe["ema20"])
        dataframe["bullish_rebound"] = dataframe["close"] > dataframe["open"]
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["regime_ok_1d"])
                & (dataframe["ema20"] > dataframe["ema50"])
                & (dataframe["adx"] > 14)
                & (dataframe["pullback_to_ema20"])
                & (dataframe["bullish_rebound"])
                & (dataframe["rsi"] > 45)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "daily_regime_hourly_pullback_v1")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema20"])
                | (dataframe["rsi"] < 45)
                | (~dataframe["regime_ok_1d"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "daily_regime_exit_v1")
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
