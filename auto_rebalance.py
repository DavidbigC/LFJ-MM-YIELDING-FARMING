import time
import traceback
from web3 import Web3
import signal
import sys

from utils.config import (
    AVAX_RPC_URL, WAVAX_ADDRESS, BTCB_ADDRESS, POOL_ADDRESS, DEFAULT_BIN_SCAN_RANGE
)
from utils.wallet import load_wallet, get_wallet_address
from db.database import LiquidityDatabase
from contracts.pool import LiquidityPool

# Configuration
CHECK_INTERVAL = 120  # Check every 2 minutes
DISTANCE_THRESHOLD = 2  # Rebalance if active bin is 2 or more bins away from our positions

def signal_handler(sig, frame):
    """Handle Ctrl+C to exit gracefully"""
    print("\nStopping automatic rebalancer...")
    sys.exit(0)

def print_banner():
    """Print a welcome banner"""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║            AUTOMATIC LIQUIDITY REBALANCER (AVAX-BTC.b)        ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)

def get_optimal_bin(pool, active_id, token_type="WAVAX"):
    """
    Determine the optimal bin based on the token type
    
    Args:
        pool: LiquidityPool instance
        active_id: Current active bin ID
        token_type: "WAVAX" or "BTC.b"
        
    Returns:
        Optimal bin ID
    """
    if token_type == "WAVAX":
        return active_id + 1  # Place WAVAX in bin above active
    else:
        return active_id - 1  # Place BTC.b in bin below active

def should_rebalance(pool, positions, active_id):
    """
    Determine if rebalancing is needed
    
    Args:
        pool: LiquidityPool instance
        positions: List of user positions
        active_id: Current active bin ID
        
    Returns:
        (bool, str): Tuple of (should_rebalance, reason)
    """
    if not positions:
        return False, "No positions found"
    
    # Check if any position is more than DISTANCE_THRESHOLD bins away from active
    for pos in positions:
        bin_id = pos['bin_id']
        distance = abs(bin_id - active_id)
        
        if distance >= DISTANCE_THRESHOLD:
            return True, f"Position in bin {bin_id} is {distance} bins away from active bin {active_id}"
    
    return False, "All positions are within threshold distance"

def add_initial_positions(pool, private_key):
    """
    Add initial positions to optimal bins using all available tokens
    
    Args:
        pool: LiquidityPool instance
        private_key: Wallet private key
        
    Returns:
        bool: Success or failure
    """
    account_address = get_wallet_address(private_key)
    
    print("\n=== ADDING INITIAL POSITIONS ===")
    
    # Get current active bin
    active_id = pool.get_active_bin()
    print(f"Current active bin: {active_id}")
    
    # Check current token balances
    avax_balance = float(pool.get_balance(WAVAX_ADDRESS, account_address))
    btc_balance = float(pool.get_balance(BTCB_ADDRESS, account_address))
    
    print(f"\nAvailable tokens:")
    print(f"WAVAX: {avax_balance:.6f}")
    print(f"BTC.b: {btc_balance:.8f}")
    
    if avax_balance < 0.01 and btc_balance < 0.0001:
        print("Insufficient tokens to add positions.")
        return False
    
    # Reserve amounts to keep in wallet
    AVAX_RESERVE = 0.000001  # Keep a tiny amount of AVAX for gas fees
    BTC_RESERVE = 0.0000000001  # Keep a tiny amount of BTC.b in reserve
    
    # Calculate amounts to add to liquidity (leave some reserves)
    avax_to_add = max(0, avax_balance - AVAX_RESERVE)
    btc_to_add = max(0, btc_balance - BTC_RESERVE)
    
    print(f"Reserving {AVAX_RESERVE} AVAX and {BTC_RESERVE} BTC.b in wallet")
    print(f"Using {avax_to_add:.6f} AVAX and {btc_to_add:.8f} BTC.b for liquidity")
    
    # Determine optimal bins
    wavax_bin = get_optimal_bin(pool, active_id, "WAVAX")
    btc_bin = get_optimal_bin(pool, active_id, "BTC.b")
    
    print(f"\nAdding liquidity to optimal bins:")
    print(f"WAVAX -> Bin {wavax_bin} (above active)")
    print(f"BTC.b -> Bin {btc_bin} (below active)")
    
    # Add liquidity to optimal bins
    success_count = 0
    
    # Add WAVAX if we have any
    if avax_to_add > 0.01:
        print(f"\nAdding {avax_to_add:.6f} WAVAX to bin {wavax_bin}...")
        if pool.add_liquidity(wavax_bin, avax_to_add, 0, private_key):
            success_count += 1
        else:
            print("Failed to add WAVAX liquidity")
    
    # Add BTC.b if we have any
    if btc_to_add > 0.0001:
        print(f"\nAdding {btc_to_add:.8f} BTC.b to bin {btc_bin}...")
        if pool.add_liquidity(btc_bin, 0, btc_to_add, private_key):
            success_count += 1
        else:
            print("Failed to add BTC.b liquidity")
    
    if success_count > 0:
        print("\nSuccessfully added initial positions!")
        
        # Check remaining balances
        avax_remaining = pool.get_balance(WAVAX_ADDRESS, account_address)
        btc_remaining = pool.get_balance(BTCB_ADDRESS, account_address)
        print(f"Remaining balances:")
        print(f"WAVAX: {avax_remaining:.6f}")
        print(f"BTC.b: {btc_remaining:.8f}")
        
        return True
    else:
        print("\nFailed to add any positions.")
        return False

def rebalance_liquidity(pool, private_key, active_id):
    """
    Rebalance liquidity by removing from all bins and adding to optimal bins
    
    Args:
        pool: LiquidityPool instance
        private_key: Wallet private key
        active_id: Current active bin ID
        
    Returns:
        bool: Success or failure
    """
    account_address = get_wallet_address(private_key)
    
    print("\n=== REBALANCING LIQUIDITY ===")
    print(f"Current active bin: {active_id}")
    
    # Step 1: Remove all liquidity
    print("\nStep 1: Removing all liquidity...")
    success = pool.remove_all_liquidity(private_key, scan_range=DEFAULT_BIN_SCAN_RANGE)
    
    if not success:
        print("Failed to remove liquidity. Aborting rebalance.")
        return False
    
    # Step 2: Get token balances
    avax_balance = float(pool.get_balance(WAVAX_ADDRESS, account_address))
    btc_balance = float(pool.get_balance(BTCB_ADDRESS, account_address))
    
    print(f"\nAvailable tokens after removal:")
    print(f"WAVAX: {avax_balance:.6f}")
    print(f"BTC.b: {btc_balance:.8f}")
    
    # Reserve amounts to keep in wallet
    AVAX_RESERVE = 0.000001  # Keep 0.1 AVAX for gas fees
    BTC_RESERVE = 0.0000000001  # Keep a small amount of BTC.b in reserve
    
    # Calculate amounts to add to liquidity (leave some reserves)
    avax_to_add = max(0, avax_balance - AVAX_RESERVE)
    btc_to_add = max(0, btc_balance - BTC_RESERVE)
    
    print(f"Reserving {AVAX_RESERVE} AVAX and {BTC_RESERVE} BTC.b in wallet")
    print(f"Using {avax_to_add:.6f} AVAX and {btc_to_add:.8f} BTC.b for liquidity")
    
    # Step 3: Determine optimal bins
    wavax_bin = get_optimal_bin(pool, active_id, "WAVAX")
    btc_bin = get_optimal_bin(pool, active_id, "BTC.b")
    
    print(f"\nStep 2: Adding liquidity to optimal bins:")
    print(f"WAVAX -> Bin {wavax_bin} (above active)")
    print(f"BTC.b -> Bin {btc_bin} (below active)")
    
    # Step 4: Add liquidity to optimal bins
    success_count = 0
    
    # Add WAVAX if we have any
    if avax_to_add > 0.01:  # Small threshold to avoid dust
        print(f"\nAdding {avax_to_add:.6f} WAVAX to bin {wavax_bin}...")
        if pool.add_liquidity(wavax_bin, avax_to_add, 0, private_key):
            success_count += 1
        else:
            print("Failed to add WAVAX liquidity")
    
    # Add BTC.b if we have any
    if btc_to_add > 0.0001:  # Small threshold to avoid dust
        print(f"\nAdding {btc_to_add:.8f} BTC.b to bin {btc_bin}...")
        if pool.add_liquidity(btc_bin, 0, btc_to_add, private_key):
            success_count += 1
        else:
            print("Failed to add BTC.b liquidity")
    
    if success_count > 0:
        print("\nRebalancing completed successfully!")
        
        # Check remaining balances
        avax_remaining = pool.get_balance(WAVAX_ADDRESS, account_address)
        btc_remaining = pool.get_balance(BTCB_ADDRESS, account_address)
        print(f"Remaining balances:")
        print(f"WAVAX: {avax_remaining:.6f}")
        print(f"BTC.b: {btc_remaining:.8f}")
        
        return True
    else:
        print("\nRebalancing failed. No liquidity was added.")
        return False

def main():
    """Main function to monitor and rebalance"""
    print_banner()
    
    # Set up signal handler for Ctrl+C
    signal.signal(signal.SIGINT, signal_handler)
    
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(AVAX_RPC_URL))
    
    if not w3.is_connected():
        print("Failed to connect to Avalanche network! Check your internet connection or RPC URL.")
        return
    
    print("Connected to Avalanche network")
    
    # Initialize database
    db = LiquidityDatabase()
    
    # Load wallet
    private_key = load_wallet()
    if not private_key:
        print("No wallet found. Please set your wallet private key in the .env file first.")
        return
    
    account_address = get_wallet_address(private_key)
    print(f"Using wallet address: {account_address}")
    
    # Initialize pool
    pool = LiquidityPool(w3, db)
    
    # Check for existing positions
    positions = pool.get_all_lp_balances(account_address, use_db_first=True)
    
    if not positions:
        print("\nNo existing positions found.")
        add_initial = input("Would you like to add initial positions now? (y/n): ")
        if add_initial.lower() == 'y':
            add_initial_positions(pool, private_key)
    
    # Monitor and rebalance loop
    print(f"\nStarting automatic monitoring (checking every {CHECK_INTERVAL//60} minutes)...")
    print("Press Ctrl+C to stop")
    
    last_check_time = 0
    
    try:
        while True:
            current_time = time.time()
            
            # Check if it's time to monitor
            if current_time - last_check_time >= CHECK_INTERVAL:
                last_check_time = current_time
                
                print(f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] Checking positions...")
                
                try:
                    # Get current active bin
                    active_id = pool.get_active_bin()
                    print(f"Current active bin: {active_id}")
                    
                    # Get user's positions
                    positions = pool.get_all_lp_balances(account_address, use_db_first=True)
                    
                    if positions:
                        print(f"Found {len(positions)} positions:")
                        for pos in positions:
                            print(f"  Bin {pos['bin_id']}: {pos['lp_balance']:.6f} LP tokens, {pos['distance_from_active']} bins from active")
                        
                        # Check if rebalancing is needed
                        should_rebal, reason = should_rebalance(pool, positions, active_id)
                        
                        if should_rebal:
                            print(f"\nRebalancing needed: {reason}")
                            rebalance_liquidity(pool, private_key, active_id)
                        else:
                            print(f"\nNo rebalancing needed: {reason}")
                    else:
                        print("No positions found. Adding new positions to optimal bins...")
                        
                        # Check if we have tokens to add
                        avax_balance = float(pool.get_balance(WAVAX_ADDRESS, account_address))
                        btc_balance = float(pool.get_balance(BTCB_ADDRESS, account_address))
                        
                        print(f"Available tokens:")
                        print(f"WAVAX: {avax_balance:.6f}")
                        print(f"BTC.b: {btc_balance:.8f}")
                        
                        if avax_balance > 0.01 or btc_balance > 0.0001:
                            # Add liquidity directly
                            add_initial_positions(pool, private_key)
                        else:
                            print("Insufficient tokens to add positions.")
                
                except Exception as e:
                    print(f"Error during check: {str(e)}")
                    traceback.print_exc()
            
            # Sleep to prevent CPU usage
            time.sleep(5)
    
    except KeyboardInterrupt:
        print("\nStopping automatic rebalancer...")
    
    finally:
        # Close database connection
        db.close()

if __name__ == "__main__":
    main() 