from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, merge_informative_pair, stoploss_from_absolute


class Strat17HTFTrendLTFReversion_v1(IStrategy):
    """
    HTF trend (1d) + LTF (1h) pullback/reclaim timing.

    - Only trades when daily trend is structurally bullish.
    - Enters on controlled pullback and momentum reclaim in 1h.
    - Avoids chasing extended candles relative to EMA20.
    """

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "1h"

    minimal_roi = {"0": 0.02}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 320

    atr_stop_mult: float = 1.9
    htf_slope_shift: int = 5

    @property
    def informative_pairs(self):
        if not self.dp:
            return []
        return [(pair, "1d") for pair in self.dp.current_whitelist()]

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        # LTF context and timing indicators.
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_mid"] = bb["mid"]

        # Extension control to avoid late entries.
        dataframe["ema20_extension"] = ((dataframe["close"] - dataframe["ema20"]).abs() / dataframe["ema20"]).fillna(0.0)
        dataframe["atr_ratio"] = (dataframe["atr"] / dataframe["close"]).fillna(0.0)

        if self.dp:
            inf = self.dp.get_pair_dataframe(pair=metadata["pair"], timeframe="1d")
            inf["ema200"] = ta.EMA(inf, timeperiod=200)
            inf["ema200_slope_up"] = inf["ema200"] > inf["ema200"].shift(self.htf_slope_shift)
            inf["adx"] = ta.ADX(inf, timeperiod=14)
            inf["htf_regime_ok"] = (
                (inf["close"] > inf["ema200"])
                & (inf["ema200_slope_up"])
                & (inf["adx"] > 12)
            )
            dataframe = merge_informative_pair(dataframe, inf, self.timeframe, "1d", ffill=True)
        else:
            dataframe["htf_regime_ok_1d"] = False

        dataframe["htf_regime_ok_1d"] = dataframe["htf_regime_ok_1d"].fillna(False).astype(bool)

        # Pullback/reclaim signals in 1h.
        dataframe["pulled_back"] = (dataframe["low"] <= dataframe["ema20"]) | (dataframe["close"] <= dataframe["bb_mid"])
        dataframe["reclaim_confirm"] = (
            (dataframe["close"] > dataframe["open"])
            & (dataframe["close"] > dataframe["ema20"])
            & (dataframe["rsi"] > 48)
        )
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["htf_regime_ok_1d"])
                & (dataframe["ema20"] > dataframe["ema50"])
                & (dataframe["adx"] > 12)
                & (dataframe["adx"] < 35)
                & (dataframe["atr_ratio"] < 0.035)
                & (dataframe["pulled_back"])
                & (dataframe["reclaim_confirm"])
                & (dataframe["ema20_extension"] < 0.018)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "htf_trend_ltf_reversion_v1")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema20"])
                | (dataframe["rsi"] < 45)
                | (~dataframe["htf_regime_ok_1d"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "htf_ltf_exit_v1")
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
