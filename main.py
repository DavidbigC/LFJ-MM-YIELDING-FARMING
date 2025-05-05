import os
import traceback
from web3 import Web3

from utils.config import (
    AVAX_RPC_URL, WAVAX_ADDRESS, BTCB_ADDRESS, POOL_ADDRESS, DEFAULT_BIN_SCAN_RANGE
)
from utils.wallet import load_wallet, create_wallet, get_wallet_address
from db.database import LiquidityDatabase
from contracts.pool import LiquidityPool

def print_banner():
    """Print a welcome banner"""
    banner = """
    ╔═══════════════════════════════════════════════════════════════╗
    ║               AVAX-BTC.b Liquidity Pool Manager              ║
    ╚═══════════════════════════════════════════════════════════════╝
    """
    print(banner)

def print_menu():
    """Print the main menu options"""
    print("\nOptions:")
    print("1. Get pool information")
    print("2. Add liquidity")
    print("3. Remove liquidity")
    print("4. Remove all liquidity")
    print("5. View my positions")
    print("6. View transaction history")
    print("7. Scan for new positions (full blockchain scan)")
    print("8. Exit")

def show_pool_info(pool, account_address):
    """Display pool information and user's balances"""
    # Get active bin
    active_id = pool.get_active_bin()
    print(f"\nActive bin ID: {active_id}")
    
    # Get current bin data and nearby bins
    start_bin = max(0, active_id - 2)
    end_bin = active_id + 3
    
    print("\nBin Information:")
    print(f"{'Bin ID':<8} | {'AVAX':<12} | {'BTC.b':<12} | {'Status':<10}")
    print("-" * 45)
    
    for bin_id in range(start_bin, end_bin):
        try:
            avax_amount, btc_amount = pool.get_bin_info(bin_id)
            status = "ACTIVE" if bin_id == active_id else ""
            print(f"{bin_id:<8} | {avax_amount:<12.6f} | {btc_amount:<12.8f} | {status:<10}")
        except Exception as e:
            print(f"{bin_id:<8} | Error getting bin data: {str(e)}")
    
    # Get user's token balances
    avax_balance = pool.get_balance(WAVAX_ADDRESS, account_address)
    btc_balance = pool.get_balance(BTCB_ADDRESS, account_address)
    
    print(f"\nYour WAVAX balance: {avax_balance:.6f}")
    print(f"Your BTC.b balance: {btc_balance:.8f}")
    
    # Get user's LP positions (using database-first approach)
    positions = pool.get_all_lp_balances(account_address, use_db_first=True)
    
    if positions:
        print("\nYour LP Positions:")
        print(f"{'Bin ID':<8} | {'LP Balance':<12} | {'Distance from Active':<20}")
        print("-" * 45)
        
        for pos in positions:
            print(f"{pos['bin_id']:<8} | {pos['lp_balance']:<12.6f} | {pos['distance_from_active']:<20}")
    else:
        print("\nYou don't have any LP positions in this pool.")

def add_liquidity_menu(pool, private_key):
    """Menu for adding liquidity"""
    account_address = get_wallet_address(private_key)
    active_id = pool.get_active_bin()
    
    print("\n=== Add Liquidity ===")
    print(f"Current active bin: {active_id}")
    
    # Get user's token balances
    avax_balance = pool.get_balance(WAVAX_ADDRESS, account_address)
    btc_balance = pool.get_balance(BTCB_ADDRESS, account_address)
    
    print(f"Your WAVAX balance: {avax_balance:.6f}")
    print(f"Your BTC.b balance: {btc_balance:.8f}")
    
    # Input bin ID or suggest optimal bins
    print("\nSuggested bins:")
    print(f"  For WAVAX: {active_id + 1} (above active)")
    print(f"  For BTC.b: {active_id - 1} (below active)")
    
    try:
        bin_id_input = input("\nEnter bin ID (or leave empty for suggested bin): ")
        if not bin_id_input.strip():
            token_type = input("Adding (1) WAVAX or (2) BTC.b? (1/2): ")
            if token_type == "1":
                bin_id = active_id + 1
                token_name = "WAVAX"
            elif token_type == "2":
                bin_id = active_id - 1
                token_name = "BTC.b"
            else:
                print("Invalid choice. Using bin above active.")
                bin_id = active_id + 1
                token_name = "WAVAX"
        else:
            bin_id = int(bin_id_input)
            # Get the token based on distance from active
            if bin_id > active_id:
                token_name = "WAVAX"
            else:
                token_name = "BTC.b"
        
        # Get amount to add
        if token_name == "WAVAX":
            amount_input = input(f"Enter WAVAX amount (max {avax_balance:.6f}): ")
            if not amount_input.strip():
                print("Amount is required.")
                return
            avax_amount = float(amount_input)
            btc_amount = 0
            
            if avax_amount > avax_balance:
                print(f"Insufficient WAVAX balance. You only have {avax_balance:.6f}")
                return
        else:
            amount_input = input(f"Enter BTC.b amount (max {btc_balance:.8f}): ")
            if not amount_input.strip():
                print("Amount is required.")
                return
            btc_amount = float(amount_input)
            avax_amount = 0
            
            if btc_amount > btc_balance:
                print(f"Insufficient BTC.b balance. You only have {btc_balance:.8f}")
                return
        
        # Confirm the transaction
        if token_name == "WAVAX":
            print(f"\nYou are about to add {avax_amount} WAVAX to bin {bin_id}")
        else:
            print(f"\nYou are about to add {btc_amount} BTC.b to bin {bin_id}")
        
        confirm = input("Confirm? (y/n): ")
        if confirm.lower() != 'y':
            print("Transaction cancelled")
            return
        
        # Add liquidity
        success = pool.add_liquidity(bin_id, avax_amount, btc_amount, private_key)
        
        if success:
            # Show updated balances
            avax_balance = pool.get_balance(WAVAX_ADDRESS, account_address)
            btc_balance = pool.get_balance(BTCB_ADDRESS, account_address)
            print(f"Updated WAVAX balance: {avax_balance:.6f}")
            print(f"Updated BTC.b balance: {btc_balance:.8f}")
        
    except ValueError as e:
        print(f"Invalid input: {e}")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

def remove_liquidity_menu(pool, private_key):
    """Menu for removing liquidity from a specific bin"""
    account_address = get_wallet_address(private_key)
    
    print("\n=== Remove Liquidity ===")
    
    # Get user's LP positions (using database-first approach)
    positions = pool.get_all_lp_balances(account_address, use_db_first=True)
    
    if not positions:
        print("You don't have any LP positions in this pool.")
        return
    
    print("\nYour LP Positions:")
    print(f"{'#':<3} | {'Bin ID':<8} | {'LP Balance':<12} | {'Distance from Active':<20}")
    print("-" * 50)
    
    for i, pos in enumerate(positions):
        print(f"{i+1:<3} | {pos['bin_id']:<8} | {pos['lp_balance']:<12.6f} | {pos['distance_from_active']:<20}")
    
    try:
        choice_input = input("\nEnter position number to remove (or 0 to cancel): ")
        if not choice_input.strip() or choice_input == "0":
            print("Operation cancelled.")
            return
        
        choice = int(choice_input) - 1
        if choice < 0 or choice >= len(positions):
            print("Invalid position number.")
            return
        
        position = positions[choice]
        bin_id = position['bin_id']
        lp_balance = position['lp_balance']
        
        amount_input = input(f"Enter amount to remove (max {lp_balance:.6f}, or 0 for all): ")
        if not amount_input.strip():
            print("Amount is required.")
            return
        
        amount = float(amount_input)
        if amount > lp_balance:
            print(f"Cannot remove more than your balance ({lp_balance:.6f}).")
            return
        
        # Confirm the transaction
        if amount == 0:
            print(f"\nYou are about to remove ALL liquidity from bin {bin_id}")
        else:
            print(f"\nYou are about to remove {amount} LP tokens from bin {bin_id}")
        
        confirm = input("Confirm? (y/n): ")
        if confirm.lower() != 'y':
            print("Transaction cancelled")
            return
        
        # Remove liquidity
        success = pool.remove_liquidity(bin_id, amount, private_key)
        
        if success:
            # Show updated positions
            positions = pool.get_all_lp_balances(account_address, use_db_first=True)
            
            print("\nUpdated LP Positions:")
            if positions:
                print(f"{'Bin ID':<8} | {'LP Balance':<12} | {'Distance from Active':<20}")
                print("-" * 45)
                
                for pos in positions:
                    print(f"{pos['bin_id']:<8} | {pos['lp_balance']:<12.6f} | {pos['distance_from_active']:<20}")
            else:
                print("You don't have any LP positions in this pool.")
    
    except ValueError as e:
        print(f"Invalid input: {e}")
    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()

def remove_all_liquidity_menu(pool, private_key):
    """Menu for removing all liquidity"""
    account_address = get_wallet_address(private_key)
    
    print("\n=== Remove All Liquidity ===")
    
    # Get user's LP positions (using database-first approach)
    positions = pool.get_all_lp_balances(account_address, use_db_first=True)
    
    if not positions:
        print("You don't have any LP positions in this pool.")
        return
    
    print("\nYour LP Positions:")
    print(f"{'Bin ID':<8} | {'LP Balance':<12} | {'Distance from Active':<20}")
    print("-" * 45)
    
    for pos in positions:
        print(f"{pos['bin_id']:<8} | {pos['lp_balance']:<12.6f} | {pos['distance_from_active']:<20}")
    
    print(f"\nYou are about to remove ALL liquidity from {len(positions)} bins.")
    confirm = input("Confirm? (y/n): ")
    
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        return
    
    # Set scan range for remove_all_liquidity to be wide enough
    scan_range = max(DEFAULT_BIN_SCAN_RANGE, 100)
    
    # Remove all liquidity
    success = pool.remove_all_liquidity(private_key, scan_range=scan_range)
    
    if success:
        print("All liquidity removed successfully!")

def view_positions_menu(pool, db, account_address):
    """Menu for viewing positions"""
    print("\n=== View Positions ===")
    
    # Get active positions first
    active_positions = pool.get_all_lp_balances(account_address, use_db_first=True)
    
    # Display active positions
    print("\nACTIVE POSITIONS:")
    if active_positions:
        print(f"{'Bin ID':<8} | {'LP Balance':<12} | {'Distance from Active':<20}")
        print("-" * 45)
        
        for pos in active_positions:
            print(f"{pos['bin_id']:<8} | {pos['lp_balance']:<12.6f} | {pos['distance_from_active']:<20}")
    else:
        print("You don't have any active LP positions in this pool.")
    
    # Get inactive positions from database
    print("\nHISTORICAL POSITIONS (no longer active):")
    query = """
    SELECT bin_id, amount, timestamp
    FROM positions 
    WHERE wallet_address = ? AND pool_address = ? AND active = 0
    ORDER BY timestamp DESC
    LIMIT 20
    """
    
    db.cursor.execute(query, (account_address, POOL_ADDRESS))
    inactive_positions = db.cursor.fetchall()
    
    if inactive_positions:
        print(f"{'Bin ID':<8} | {'LP Amount':<12} | {'Date':<20}")
        print("-" * 45)
        
        for pos in inactive_positions:
            bin_id, amount, timestamp = pos
            print(f"{bin_id:<8} | {amount:<12.6f} | {timestamp:<20}")
    else:
        print("No historical positions found.")

def view_history_menu(db, account_address):
    """Menu for viewing transaction history"""
    print("\n=== Transaction History ===")
    
    # Get operations from database
    operations = db.get_operations(account_address, limit=20)
    
    if operations:
        print(f"{'Operation':<10} | {'Bin ID':<8} | {'Token X':<10} | {'Token Y':<10} | {'Date':<20}")
        print("-" * 65)
        
        for op in operations:
            operation_type = op['operation_type']
            bin_id = op['bin_id'] if op['bin_id'] is not None else "N/A"
            amount_x = f"{op['amount_x']:.6f}" if op['amount_x'] is not None else "N/A"
            amount_y = f"{op['amount_y']:.6f}" if op['amount_y'] is not None else "N/A"
            timestamp = op['timestamp']
            
            print(f"{operation_type:<10} | {bin_id:<8} | {amount_x:<10} | {amount_y:<10} | {timestamp:<20}")
    else:
        print("No transaction history found.")

def scan_all_positions(pool, private_key):
    """Menu for scanning all positions on blockchain"""
    account_address = get_wallet_address(private_key)
    
    print("\n=== Scan All Positions ===")
    print("This will scan a wide range of bins to find all your positions.")
    print("This may take a while...")
    
    confirm = input("Continue? (y/n): ")
    if confirm.lower() != 'y':
        print("Operation cancelled.")
        return
    
    # Use a very wide scan range
    scan_range = 1000  # 1000 bins before/after active ID
    
    # Scan for positions (don't use DB first)
    positions = pool.get_all_lp_balances(account_address, scan_range=scan_range, use_db_first=False)
    
    print(f"\nFound {len(positions)} positions across {scan_range*2} bins:")
    
    if positions:
        print(f"{'Bin ID':<8} | {'LP Balance':<12} | {'Distance from Active':<20}")
        print("-" * 45)
        
        for pos in positions:
            print(f"{pos['bin_id']:<8} | {pos['lp_balance']:<12.6f} | {pos['distance_from_active']:<20}")
    else:
        print("No positions found.")

def main():
    """Main function"""
    print_banner()
    
    # Initialize Web3
    w3 = Web3(Web3.HTTPProvider(AVAX_RPC_URL))
    
    if not w3.is_connected():
        print("Failed to connect to Avalanche network! Check your internet connection or RPC URL.")
        return
    
    print("Connected to Avalanche network")
    
    # Load or create wallet
    private_key = load_wallet()
    if not private_key:
        print("No wallet found. You need to create one.")
        create_choice = input("Create a new wallet? (y/n): ")
        if create_choice.lower() == 'y':
            address, private_key = create_wallet()
            if not private_key:
                print("Failed to create wallet. Exiting.")
                return
        else:
            print("Wallet is required to use this application. Exiting.")
            return
    
    account_address = get_wallet_address(private_key)
    print(f"Using wallet address: {account_address}")
    
    # Initialize database
    db = LiquidityDatabase()
    
    # Initialize pool
    pool = LiquidityPool(w3, db)
    
    try:
        while True:
            print_menu()
            choice = input("\nEnter your choice (1-8): ")
            
            if choice == '1':
                show_pool_info(pool, account_address)
                
            elif choice == '2':
                add_liquidity_menu(pool, private_key)
                
            elif choice == '3':
                remove_liquidity_menu(pool, private_key)
                
            elif choice == '4':
                remove_all_liquidity_menu(pool, private_key)
                
            elif choice == '5':
                view_positions_menu(pool, db, account_address)
                
            elif choice == '6':
                view_history_menu(db, account_address)
                
            elif choice == '7':
                scan_all_positions(pool, private_key)
                
            elif choice == '8':
                print("Exiting...")
                break
                
            else:
                print("Invalid choice. Please try again.")
            
            input("\nPress Enter to continue...")
    
    except KeyboardInterrupt:
        print("\nExiting...")
    
    except Exception as e:
        print(f"Unexpected error: {e}")
        traceback.print_exc()
    
    finally:
        # Close database connection
        db.close()

if __name__ == "__main__":
    main() 