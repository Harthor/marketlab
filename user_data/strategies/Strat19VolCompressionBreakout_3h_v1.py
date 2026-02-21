from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat19VolCompressionBreakout_3h_v1(IStrategy):
    """
    3h-oriented breakout from low-volatility compression.
    Note: Binance/CCXT does not expose 3h timeframe directly, so runtime support
    depends on exchange/timeframe availability in the running setup.
    """

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "3h"

    minimal_roi = {"0": 0.025}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 240

    atr_stop_mult: float = 2.0

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema50"] = ta.EMA(dataframe, timeperiod=50)
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = dataframe["ema200"] > dataframe["ema200"].shift(8)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)
        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bb["lower"]
        dataframe["bb_upperband"] = bb["upper"]
        dataframe["bb_mid"] = bb["mid"]
        dataframe["bb_width"] = (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_mid"]
        dataframe["bb_width_ma"] = dataframe["bb_width"].rolling(30).mean()
        dataframe["squeeze"] = dataframe["bb_width"] < (dataframe["bb_width_ma"] * 0.85)

        dataframe["hh20"] = dataframe["high"].rolling(20).max().shift(1)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema200"])
                & (dataframe["ema200_slope_up"])
                & (dataframe["ema50"] > dataframe["ema200"])
                & (dataframe["adx"] > 16)
                & (dataframe["adx"] < 35)
                & (dataframe["squeeze"].rolling(3).max() > 0)
                & (dataframe["close"] > dataframe["hh20"])
                & (dataframe["rsi"] > 50)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "vol_comp_breakout_3h")
        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] < dataframe["ema50"])
                | (dataframe["close"] < dataframe["bb_mid"])
                | (dataframe["rsi"] < 45)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "breakout_momentum_lost")
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
