import os
from dotenv import load_dotenv
from web3 import Web3

# Load environment variables
load_dotenv()

# Network configuration
AVAX_RPC_URL = os.getenv('AVAX_RPC_URL', 'https://api.avax.network/ext/bc/C/rpc')
CHAIN_ID = 43114  # Avalanche C-Chain

# Convert addresses to checksum format
def to_checksum(address):
    return Web3.to_checksum_address(address)

# Contract addresses
POOL_ADDRESS = to_checksum("0x856b38bf1e2e367f747dd4d3951dda8a35f1bf60")  # WAVAX-BTC.b pool
PROXY_ADDRESS = to_checksum("0x7a5b4e301fc2b148cefe57257a236eb845082797")
WAVAX_ADDRESS = to_checksum("0xB31f66AA3C1e785363F0875A1B74E27b85FD66c7")
BTCB_ADDRESS = to_checksum("0x152b9d0fdc40c096757f570a51e494bd4b943e50")  # BTC.b address
ROUTER_ADDRESS = to_checksum("0x18556DA13313f3532c54711497A8FedAC273220E")  # Trader Joe LB Router v2.2

# File paths
ABI_PATH = 'abi.json'
ROUTER_ABI_PATH = 'router_abi.json'
WALLET_PATH = '.env'  # Store wallet in .env file instead of directly
DB_PATH = 'db/liquidity_tracker.db'

# Transaction settings
GAS_LIMIT_BASE = 300000
GAS_LIMIT_LARGE = 1000000
SLIPPAGE_PERCENT = 5  # 5% slippage tolerance

# Default parameters
DEFAULT_BIN_SCAN_RANGE = 10  # Scan 10 bins before/after active ID

# Token decimals
WAVAX_DECIMALS = 18
BTCB_DECIMALS = 8  # BTC.b has 8 decimals 