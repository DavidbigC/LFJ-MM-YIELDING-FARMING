# AVAX-BTC.b Liquidity Market Making Strategy

An automated market making strategy for the AVAX-BTC.b Trader Joe liquidity pool on Avalanche. This application implements an optimal bin placement strategy for concentrated liquidity provision and automated rebalancing.

## Market Making Strategy

This project implements a simple yet effective concentrated liquidity market making strategy for the AVAX-BTC.b pair on Trader Joe's Liquidity Book protocol. The strategy works as follows:

1. **Optimal Bin Placement**: 
   - Place AVAX in bins slightly above the current active bin
   - Place BTC.b in bins slightly below the current active bin
   - This ensures your liquidity is close to where trades are happening

2. **Automatic Rebalancing**:
   - The auto-rebalancer continuously monitors price movements
   - When price moves significantly (configurable threshold), it automatically:
     - Withdraws all liquidity from current positions
     - Places it in optimal bins based on the new price

3. **Key Features**:
   - Reduces impermanent loss compared to traditional AMMs
   - Maximizes fee collection by keeping liquidity near active trading range
   - Fully automated operation with customizable parameters
   - Local database tracking of all positions and operations

## Project Structure

```
.
├── main.py                # Main interactive application
├── auto_rebalance.py      # Automated rebalancing script
├── requirements.txt       # Dependencies
├── .env                   # Environment variables (create this yourself)
├── db/                    # Database module
│   ├── __init__.py
│   ├── database.py        # SQLite database handler
│   └── liquidity_tracker.db  # Database file (created on first run)
├── utils/                 # Utility modules
│   ├── __init__.py
│   ├── config.py          # Configuration and constants
│   └── wallet.py          # Wallet management functions
└── contracts/             # Contract interaction modules
    ├── __init__.py
    └── pool.py            # Liquidity pool interaction functions
```

## Installation

1. Clone the repository
2. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Create a `.env` file with your credentials:
   ```
   AVAX_RPC_URL=your_avalanche_rpc_url
   WALLET_ADDRESS=your_wallet_address
   WALLET_PRIVATE_KEY=your_private_key
   ```

4. Download the ABI files:
   - Create an `abi.json` file with the Trader Joe LB Pool ABI
   - Create a `router_abi.json` file with the Trader Joe LB Router ABI

## Security

**IMPORTANT**: This application requires access to your private key to sign transactions. Always:
- Keep your `.env` file secure and never share it
- Run this software only on a secure system
- Start with small amounts of funds until you're comfortable with its operation
- Verify all transaction details before confirming

## Usage

### Interactive Mode

Run the interactive application:

```
python main.py
```

This provides a menu-driven interface to:
- View pool information and your positions
- Add liquidity to specific bins
- Remove liquidity from specific bins
- Remove all liquidity at once
- View transaction history

### Automated Rebalancing

For continuous automated rebalancing:

```
python auto_rebalance.py
```

This will:
1. Check your current positions
2. Monitor price movements
3. Rebalance when price moves beyond the threshold
4. Continue monitoring until stopped (Ctrl+C)

## Configuration

Key parameters can be adjusted in the files:

- `utils/config.py`: Contract addresses, RPC URL, and other constants
- `auto_rebalance.py`: 
  - `CHECK_INTERVAL`: How often to check prices (in seconds)
  - `DISTANCE_THRESHOLD`: How far price must move to trigger rebalance

## Strategy Parameters

The default strategy parameters are:

- **Bin placement**:
  - AVAX: 1 bin above active bin
  - BTC.b: 1 bin below active bin
  
- **Rebalance threshold**: 
  - Rebalance when active bin is 2 or more bins away from your positions

These parameters can be adjusted based on:
- Market volatility
- Fee rates
- Your risk tolerance
- Gas costs vs. potential earnings

## Example Workflow

1. **Initial setup**:
   - Fund your wallet with AVAX and BTC.b
   - Run `main.py` and add initial liquidity in suggested bins

2. **Automated operation**:
   - Run `auto_rebalance.py` in a persistent session
   - The script will monitor and rebalance as needed

3. **Monitoring and adjustments**:
   - Periodically check your positions and earnings with `main.py`
   - Adjust strategy parameters as needed based on performance

## License

MIT

## Disclaimer

This software is provided for educational and informational purposes only. Use at your own risk. The authors are not responsible for any financial losses incurred while using this software. 