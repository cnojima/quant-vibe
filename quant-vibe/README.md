# Quant Vibe Options Trading Strategies

## Overview
Quant Vibe is a backtesting framework designed for options trading strategies. It provides a robust engine for testing various options strategies, including vertical spreads, while allowing for detailed performance analysis.

## Project Structure
```
quant-vibe
├── src
│   └── quant_vibe
│       ├── strategies
│       │   ├── options_base.py       # Base classes and interfaces for options strategies
│       │   ├── bullish_vertical_call.py # Implements the Bullish Vertical Call Spread Strategy
│       │   ├── bullish_vertical_put.py  # Implements the Bullish Vertical Put Spread Strategy
│       │   └── __init__.py             # Marks the strategies directory as a package
│       └── backtesting
│           ├── options_engine.py       # Backtesting engine for options strategies
│           └── __init__.py             # Marks the backtesting directory as a package
├── tests
│   └── test_bullish_vertical_put.py    # Unit tests for the Bullish Vertical Put Spread Strategy
└── README.md                            # Documentation for the project
```

## Installation
To set up the project, clone the repository and install the required dependencies. You can use pip to install any necessary packages.

```bash
git clone <repository-url>
cd quant-vibe
pip install -r requirements.txt
```

## Usage
To run backtests using the provided strategies, you can utilize the `OptionsBacktestEngine` class from the `options_engine.py` file. You will need to provide historical market data for both the underlying asset and the options chain.

### Example
```python
from quant_vibe.backtesting.options_engine import OptionsBacktestEngine
from quant_vibe.strategies.bullish_vertical_call import BullishVerticalCallStrategy
from quant_vibe.strategies.bullish_vertical_put import BullishVerticalPutStrategy

# Initialize backtest engine
engine = OptionsBacktestEngine()

# Load your data
underlying_data = ...  # Load your underlying asset data
options_data = ...     # Load your options chain data

# Initialize strategy
strategy = BullishVerticalCallStrategy()

# Run backtest
results = engine.run(strategy, underlying_data, options_data)
```

## Strategies
### Bullish Vertical Call Spread Strategy
This strategy involves entering a bullish vertical call spread based on market analysis, with specific entry and exit criteria.

### Bullish Vertical Put Spread Strategy
Similar to the call spread strategy, this strategy focuses on entering a bullish vertical put spread, adapting the logic for put options.

## Testing
Unit tests are provided for the Bullish Vertical Put Spread Strategy to ensure its functionality under various market conditions. You can run the tests using a testing framework like pytest.

```bash
pytest tests/test_bullish_vertical_put.py
```

## Contributing
Contributions are welcome! Please submit a pull request or open an issue for any enhancements or bug fixes.

## License
This project is licensed under the MIT License. See the LICENSE file for more details.