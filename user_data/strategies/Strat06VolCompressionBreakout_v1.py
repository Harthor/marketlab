from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat06VolCompressionBreakout_v1(IStrategy):
    """
    Volatility compression breakout prototype.

    Assumptions:
    - Market is in bullish regime when EMA200 is rising and price is above EMA200.
    - Entries are allowed after low-volatility compression and upside breakout.
    - ATR-based custom stop keeps risk proportional to current volatility.
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
    bbw_quantile_window: int = 200
    breakout_lookback: int = 20

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema20"] = ta.EMA(dataframe, timeperiod=20)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = dataframe["ema200"] > dataframe["ema200"].shift(10)

        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_upper"] = bb["upper"]
        dataframe["bb_mid"] = bb["mid"]
        dataframe["bb_lower"] = bb["lower"]
        dataframe["bb_width"] = (dataframe["bb_upper"] - dataframe["bb_lower"]) / dataframe["bb_mid"].replace(0, 1)

        dataframe["bb_width_threshold"] = dataframe["bb_width"].rolling(self.bbw_quantile_window).quantile(0.25)
        dataframe["is_compressed"] = dataframe["bb_width"] <= dataframe["bb_width_threshold"]

        dataframe["hh20_prev"] = dataframe["high"].rolling(self.breakout_lookback).max().shift(1)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema200"])
                & (dataframe["ema200_slope_up"])
                & (dataframe["adx"] > 18)
                & (dataframe["is_compressed"])
                & (dataframe["close"] > dataframe["hh20_prev"])
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "vol_compression_breakout_v1")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema20"])
                | (dataframe["close"] < dataframe["bb_mid"])
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "vol_breakout_exit_v1")
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
