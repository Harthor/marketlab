from datetime import datetime

from pandas import DataFrame
import talib.abstract as ta
from technical import qtpylib

from freqtrade.persistence import Trade
from freqtrade.strategy import IStrategy, stoploss_from_absolute


class Strat03RSIBBMeanReversion_v3c(IStrategy):
    """v3c: v3a entry with more aggressive exits and tighter ATR stop."""

    INTERFACE_VERSION = 3
    can_short: bool = False
    timeframe = "1h"

    minimal_roi = {"0": 0.02}
    stoploss = -0.2
    use_custom_stoploss = True

    process_only_new_candles = True
    startup_candle_count: int = 220

    atr_stop_mult: float = 1.4
    debug_social: bool = False
    _social_debug_logged_pairs: set[str] = set()

    def populate_indicators(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe["ema200"] = ta.EMA(dataframe, timeperiod=200)
        dataframe["ema200_slope_up"] = dataframe["ema200"] > dataframe["ema200"].shift(10)
        dataframe["rsi"] = ta.RSI(dataframe, timeperiod=14)
        dataframe["adx"] = ta.ADX(dataframe, timeperiod=14)

        bb = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=20, stds=2)
        dataframe["bb_lowerband"] = bb["lower"]
        dataframe["bb_middleband"] = bb["mid"]

        dataframe["atr"] = ta.ATR(dataframe, timeperiod=14)

        # Social columns are optional in the merged candles input. Keep strategy safe by
        # defaulting to zero and deriving indicators without future-data leakage.
        if "social_mentions_count_1h" not in dataframe.columns:
            dataframe["social_mentions_count_1h"] = 0
        if "social_avg_engagement_score_1h" not in dataframe.columns:
            dataframe["social_avg_engagement_score_1h"] = 0.0

        mentions_mean_48 = dataframe["social_mentions_count_1h"].rolling(window=48, min_periods=12).mean()
        mentions_std_48 = dataframe["social_mentions_count_1h"].rolling(window=48, min_periods=12).std()
        mentions_z = (dataframe["social_mentions_count_1h"] - mentions_mean_48) / mentions_std_48
        dataframe["social_mentions_z"] = mentions_z.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)

        engagement_mean_48 = dataframe["social_avg_engagement_score_1h"].rolling(window=48, min_periods=12).mean()
        engagement_std_48 = dataframe["social_avg_engagement_score_1h"].rolling(window=48, min_periods=12).std()
        engagement_z = (dataframe["social_avg_engagement_score_1h"] - engagement_mean_48) / engagement_std_48
        dataframe["social_engagement_z"] = engagement_z.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
        dataframe["social_hype"] = dataframe["social_mentions_z"] + dataframe["social_engagement_z"]

        pair = str(metadata.get("pair", "UNKNOWN"))
        if self.debug_social and pair not in self.__class__._social_debug_logged_pairs:
            created = [
                "social_mentions_count_1h",
                "social_avg_engagement_score_1h",
                "social_mentions_z",
                "social_engagement_z",
                "social_hype",
            ]
            print(f"[social-debug] pair={pair} social_columns_ready={created}")
            self.__class__._social_debug_logged_pairs.add(pair)
        return dataframe

    def populate_entry_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["ema200"])
                & (dataframe["ema200_slope_up"])
                & (dataframe["rsi"] < 32)
                & (dataframe["close"] < dataframe["bb_lowerband"])
                & (dataframe["adx"] < 20)
                & (dataframe["volume"] > 0)
            ),
            ["enter_long", "enter_tag"],
        ] = (1, "rsi_bb_meanrev_v3c")

        return dataframe

    def populate_exit_trend(self, dataframe: DataFrame, metadata: dict) -> DataFrame:
        dataframe.loc[
            (
                (dataframe["close"] > dataframe["bb_middleband"])
                | (dataframe["rsi"] > 45)
            ),
            ["exit_long", "exit_tag"],
        ] = (1, "mean_reversion_exit_v3c")
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
