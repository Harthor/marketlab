from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat20DonchianRegimePullback_4h_v1(IStrategy):
    """4h trend-pullback strategy with Donchian guardrails."""

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "4h"

    minimal_roi = {"0": 0.025}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 260

    atr_stop_mult: float = 2.0
    max_extension_to_ema20: float = 0.03

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = dataframe["ema200"] > dataframe["ema200"].shift(12)

        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        dataframe["atr_pct"] = (dataframe["atr"] / dataframe["close"]).fillna(0.0)

        dataframe["hh20"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["ll20"] = dataframe["low"].rolling(20).min().shift(1)
        dataframe["ll10"] = dataframe["low"].rolling(10).min().shift(1)
        dataframe["donchian_mid20"] = (dataframe["hh20"] + dataframe["ll20"]) / 2.0

        dataframe["pullback_to_ema20"] = (dataframe["low"] <= dataframe["ema20"]) | (
            dataframe["close"] <= dataframe["ema20"] * 1.005
        )
        dataframe["bullish_reclaim"] = (dataframe["close"] > dataframe["ema20"]) & (
            dataframe["close"] > dataframe["open"]
        )
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
                & (dataframe["adx"] > 17)
                & (dataframe["adx"] < 38)
                & (dataframe["atr_pct"] > 0.006)
                & (dataframe["atr_pct"] < 0.045)
                & (dataframe["pullback_to_ema20"])
                & (dataframe["bullish_reclaim"])
                & (dataframe["close"] > dataframe["donchian_mid20"])
                & (dataframe["rsi"] > 48)
                & (dataframe["ema20_extension"] < self.max_extension_to_ema20)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "trend_pullback_donchian_4h")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema20"])
                | (dataframe["close"] < dataframe["ll10"])
                | (dataframe["rsi"] < 45)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "pullback_momentum_lost_4h")
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
