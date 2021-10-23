
import pandas as pd
from tradingstrategy.timebucket import TimeBucket
from tradingstrategy.chain import ChainId

from tradingstrategy.client import Client

client = Client.create_jupyter_client()


TARGET_PAIR = ("GRT", "WETH")

# The backtest only consider Ethereum mainnet
BLOCKCHAIN = ChainId.ethereum

# The backtest only considers Sushiswap v2 exchange
EXCHANGE = "sushiswap"

# Use 4h candles for backtesting
CANDLE_KIND = TimeBucket.h1

# How many USD is our play money wallet
INITIAL_CASH = 10_000

# The moving average must be above of this number for us to buy
MOVING_AVERAGE_CANDLES = 50

# How many previous candles we sample for the low close value
LOW_CANDLES = 7

# How many previous candles we sample for the high close value
HIGH_CANDLES = 7

# When do we start the backtesting - limit the candle set from the data dump from the server
BACKTESTING_BEGINS = pd.Timestamp("2021-01-01")

# When do we end backtesting
BACKTESTING_ENDS = pd.Timestamp("2021-10-01")

# If the price drops 15% we trigger a stop loss
STOP_LOSS = 0.97

# Sushi fee
COMMISSION = 0.003


from typing import Optional
import backtrader as bt
from backtrader import indicators

from tradingstrategy.analysis.tradehint import TradeHint, TradeHintType
from tradingstrategy.frameworks.backtrader import DEXStrategy
from backtrader import analyzers, Position


class Double7(DEXStrategy):
    """An example of double-77 strategy for DEX spot trading.

    The original description: https://www.thechartist.com.au/double-7-s-strategy/
    """

    def start(self):
        # Set up indicators used in this strategy

        # Moving average that tells us when we are in the bull market
        self.moving_average = indicators.SMA(period=MOVING_AVERAGE_CANDLES)

        # The highest close price for the N candles
        # "exit" in pine script
        self.highest = indicators.Highest(self.data.close, period=HIGH_CANDLES, plot=True, subplot=False)

        # The lowest close price for the N candles
        # "entry" in pine script
        self.lowest = indicators.Lowest(self.data.close, period=LOW_CANDLES, plot=True, subplot=False)

    def next(self):
        """Execute a decision making tick for each candle."""

        # print("Tick", self.tick)
        # print("Tick", self.tick)

        close = self.data.close[0]
        low = self.lowest[-1]
        high = self.highest[-1]
        avg = self.moving_average[0]

        if not all([close, low, high, avg]):
            # Do not try to make any decision if we have nan or zero data
            return

        position: Optional[Position] = self.position

        price = close
        assert price > 0

        if not position:
            # We are not in the markets, check entry
            if close >= avg and close <= low and not position:
                # Enter when we are above moving average and the daily close was
                assert close > 0

                # Always buy with 95% of available cash
                cash = self.broker.get_cash()
                size = cash * 0.95 / price

                print(f"Tick {self.tick} buy at {price}, size {size}, spent {size * price}")
                # self.buy(price=price, size=size, hint=TradeHint(type=TradeHintType.open))
                self.buy(price=price, hint=TradeHint(type=TradeHintType.open))

                self.entry_price = price
        else:
            # We are in the markets, check exit
            if close >= high:
                # If the price closes above its 7 day high, exit from the markets
                #print("Exited the position")
                print(f"Tick {self.tick} - exiting at {price}")
                self.close(hint=TradeHint(type=TradeHintType.close))
            else:
                # Check the exit from the market through stop loss

                # Because AMMs do not support complex order types,
                # only swaps, we do not manual stop loss here by
                # brute market sell in the case the price falls below the stop loss threshold

                entry_price = self.entry_price
                if close <= entry_price * STOP_LOSS:
                    print(f"Tick {self.tick}, stop loss triggered. Now {close}, opened at {entry_price}")
                    self.close(hint=TradeHint(type=TradeHintType.stop_loss_triggered))
                    # self.close(hint=TradeHint(type=TradeHintType.stop_loss_triggered))

                    cash = self.broker.get_cash()



from tradingstrategy.frameworks.backtrader import prepare_candles_for_backtrader, add_dataframes_as_feeds, TradeRecorder
from tradingstrategy.pair import PandasPairUniverse

# Operate on daily candles
strategy_time_bucket = CANDLE_KIND

exchange_universe = client.fetch_exchange_universe()
columnar_pair_table = client.fetch_pair_universe()
all_pairs_dataframe = columnar_pair_table.to_pandas()
pair_universe = PandasPairUniverse(all_pairs_dataframe)

# Filter down to pairs that only trade on Sushiswap
sushi_swap = exchange_universe.get_by_name_and_chain(BLOCKCHAIN, EXCHANGE)
pair = pair_universe.get_one_pair_from_pandas_universe(
    sushi_swap.exchange_id,
    TARGET_PAIR[0],
    TARGET_PAIR[1])

assert pair, f"Could no find trading pair {TARGET_PAIR}"

all_candles = client.fetch_all_candles(strategy_time_bucket).to_pandas()
pair_candles: pd.DataFrame = all_candles.loc[all_candles["pair_id"] == pair.pair_id]
pair_candles = prepare_candles_for_backtrader(pair_candles)

# We limit candles to a specific date range to make this notebook deterministic
pair_candles = pair_candles[(pair_candles.index >= BACKTESTING_BEGINS) & (pair_candles.index <= BACKTESTING_ENDS)]

print(f"Dataset size is {len(pair_candles)} candles")

# This strategy requires data for 100 days. Because we are operating on new exchanges,
# there simply might not be enough data there
assert len(pair_candles) > MOVING_AVERAGE_CANDLES, "We do not have enough data to execute the strategy"

# Create the Backtrader back testing engine "Cebebro"
cerebro = bt.Cerebro(stdstats=True)

cerebro.broker.setcommission(commission=COMMISSION)
cerebro.broker.setcash(INITIAL_CASH)

# Add out strategy
cerebro.addstrategy(Double7)

# Add two analyzers for the strategy performance
cerebro.addanalyzer(bt.analyzers.SharpeRatio, riskfreerate=0.0)
cerebro.addanalyzer(bt.analyzers.Returns)
cerebro.addanalyzer(bt.analyzers.DrawDown)
cerebro.addanalyzer(TradeRecorder)

add_dataframes_as_feeds(
    cerebro,
    pair_universe,
    [pair_candles],
    BACKTESTING_BEGINS,
    BACKTESTING_ENDS,
    strategy_time_bucket,
    plot=True)


# Run the backtest using the backtesting engine and store the results
results = cerebro.run()

from tradingstrategy.frameworks.backtrader import analyse_strategy_trades

strategy: Double7 = results[0]

print(f"Backtesting range {BACKTESTING_BEGINS.date()} - {BACKTESTING_ENDS.date()}")
sharpe = strategy.analyzers.sharperatio.get_analysis()
# import ipdb ; ipdb.set_trace()
# print(f"Sharpe: {sharpe['sharperatio']:.3f}")
print(f"Normalised annual return: {strategy.analyzers.returns.get_analysis()['rnorm100']:.2f}%")
print(f"Max drawdown: {strategy.analyzers.drawdown.get_analysis()['max']['drawdown']:.2f}%")

trades = strategy.analyzers.traderecorder.trades
trade_analysis = analyse_strategy_trades(trades)

