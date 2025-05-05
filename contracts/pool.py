import json
import traceback
from web3 import Web3
from typing import Tuple, List, Dict, Optional, Any

from utils.config import (
    POOL_ADDRESS, ROUTER_ADDRESS, WAVAX_ADDRESS, BTCB_ADDRESS,
    ABI_PATH, ROUTER_ABI_PATH, CHAIN_ID,
    WAVAX_DECIMALS, BTCB_DECIMALS,
    GAS_LIMIT_BASE, GAS_LIMIT_LARGE
)
from db.database import LiquidityDatabase
from utils.wallet import sign_transaction, build_transaction

class LiquidityPool:
    """Trader Joe Liquidity Pool Interface"""
    
    def __init__(self, w3: Web3, db: LiquidityDatabase):
        """
        Initialize the pool interface
        
        Args:
            w3: Web3 instance
            db: Database instance for tracking
        """
        self.w3 = w3
        self.db = db
        
        # Load ABIs
        with open(ABI_PATH, 'r') as f:
            self.abi = json.load(f)
            
        with open(ROUTER_ABI_PATH, 'r') as f:
            self.router_abi = json.load(f)
            
        # Initialize contracts
        self.pool_contract = self.w3.eth.contract(address=POOL_ADDRESS, abi=self.abi)
        self.router_contract = self.w3.eth.contract(address=ROUTER_ADDRESS, abi=self.router_abi)
        
        # Get token contracts
        self.token_abi = [
            {
                "inputs": [{"internalType": "address", "name": "account", "type": "address"}],
                "name": "balanceOf",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "spender", "type": "address"},
                    {"internalType": "uint256", "name": "amount", "type": "uint256"}
                ],
                "name": "approve",
                "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {
                "inputs": [
                    {"internalType": "address", "name": "owner", "type": "address"},
                    {"internalType": "address", "name": "spender", "type": "address"}
                ],
                "name": "allowance",
                "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        self.wavax_contract = self.w3.eth.contract(address=WAVAX_ADDRESS, abi=self.token_abi)
        self.btcb_contract = self.w3.eth.contract(address=BTCB_ADDRESS, abi=self.token_abi)
        
        # Cache token order
        self.token_x = self.pool_contract.functions.getTokenX().call()
        self.token_y = self.pool_contract.functions.getTokenY().call()
        self.bin_step = self.pool_contract.functions.getBinStep().call()
        
        # Check if WAVAX is X or Y
        self.is_wavax_x = self.token_x.lower() == WAVAX_ADDRESS.lower()
    
    def get_active_bin(self) -> int:
        """Get the current active bin ID"""
        return self.pool_contract.functions.getActiveId().call()
    
    def get_bin_info(self, bin_id: int) -> Tuple[float, float]:
        """
        Get the reserves for a specific bin
        
        Args:
            bin_id: The bin ID
            
        Returns:
            Tuple of (avax_amount, btc_amount)
        """
        bin_x, bin_y = self.pool_contract.functions.getBin(bin_id).call()
        
        # Convert to readable format
        if self.is_wavax_x:
            avax_amount = self.w3.from_wei(bin_x, 'ether')
            btc_amount = bin_y / (10 ** BTCB_DECIMALS)
        else:
            avax_amount = self.w3.from_wei(bin_y, 'ether')
            btc_amount = bin_x / (10 ** BTCB_DECIMALS)
            
        return avax_amount, btc_amount
    
    def get_balance(self, token_address: str, wallet_address: str) -> float:
        """Get token balance of an address"""
        token_contract = self.w3.eth.contract(address=token_address, abi=self.token_abi)
        balance = token_contract.functions.balanceOf(wallet_address).call()
        
        # Format based on token
        if token_address.lower() == WAVAX_ADDRESS.lower():
            return self.w3.from_wei(balance, 'ether')
        elif token_address.lower() == BTCB_ADDRESS.lower():
            return balance / (10 ** BTCB_DECIMALS)
        
        return balance
    
    def get_lp_balance(self, bin_id: int, wallet_address: str) -> float:
        """Get LP token balance for a specific bin"""
        balance = self.pool_contract.functions.balanceOf(wallet_address, bin_id).call()
        return balance / (10 ** 18)  # LP tokens typically have 18 decimals
    
    def get_all_lp_balances(self, wallet_address: str, scan_range: int = 50, use_db_first: bool = True) -> List[Dict[str, Any]]:
        """
        Get all LP positions for a wallet
        
        Args:
            wallet_address: The wallet address
            scan_range: How many bins to scan before/after active bin (only used if use_db_first is False)
            use_db_first: Whether to prioritize database lookups over on-chain scanning
            
        Returns:
            List of LP positions
        """
        positions = []
        
        # If prioritizing DB, get positions from database first
        if use_db_first:
            db_positions = self.db.get_active_positions(wallet_address, POOL_ADDRESS)
            
            if db_positions:
                print("Using database to find positions...")
                active_id = self.get_active_bin()
                
                # For each position in DB, verify it still exists on-chain and get current balance
                for pos in db_positions:
                    bin_id = pos['bin_id']
                    try:
                        balance = self.pool_contract.functions.balanceOf(wallet_address, bin_id).call()
                        if balance > 0:
                            # Get bin reserves
                            bin_x, bin_y = self.pool_contract.functions.getBin(bin_id).call()
                            
                            positions.append({
                                'bin_id': bin_id,
                                'lp_balance': balance / (10 ** 18),
                                'token_x': self.token_x,
                                'token_y': self.token_y,
                                'reserve_x': bin_x,
                                'reserve_y': bin_y,
                                'distance_from_active': bin_id - active_id
                            })
                            
                            # Update position in database if balance has changed
                            if abs(pos['amount'] - (balance / (10 ** 18))) > 0.000001:
                                self.db.update_position(pos['id'], balance / (10 ** 18))
                        else:
                            # Position no longer exists, mark as inactive
                            self.db.deactivate_position(pos['id'])
                    except Exception as e:
                        # Continue if there's an issue with a specific bin
                        pass
                
                # If we found positions from DB, return them
                if positions:
                    return positions
        
        # If no DB records or use_db_first is False, fall back to scanning bins
        # This is slower but will catch any positions not in the database
        print("Scanning blockchain for positions (this may take a while)...")
        active_id = self.get_active_bin()
        start_bin = max(0, active_id - scan_range)
        end_bin = active_id + scan_range
        
        for bin_id in range(start_bin, end_bin + 1):
            try:
                balance = self.pool_contract.functions.balanceOf(wallet_address, bin_id).call()
                if balance > 0:
                    # Get bin reserves
                    bin_x, bin_y = self.pool_contract.functions.getBin(bin_id).call()
                    
                    positions.append({
                        'bin_id': bin_id,
                        'lp_balance': balance / (10 ** 18),
                        'token_x': self.token_x,
                        'token_y': self.token_y,
                        'reserve_x': bin_x,
                        'reserve_y': bin_y,
                        'distance_from_active': bin_id - active_id
                    })
                    
                    # Check if position exists in DB, if not, add it
                    if use_db_first:
                        pos = self.db.get_position_by_bin(wallet_address, bin_id, POOL_ADDRESS)
                        if not pos:
                            self.db.add_position(
                                wallet_address, bin_id, balance / (10 ** 18),
                                self.token_x, self.token_y, POOL_ADDRESS
                            )
            except Exception as e:
                # Continue if there's an issue with a specific bin
                pass
        
        return positions
    
    def approve_token(self, token_address: str, spender_address: str, amount: float, private_key: str) -> bool:
        """
        Approve a token to be spent by a spender
        
        Args:
            token_address: Token address to approve
            spender_address: Address that will spend the tokens
            amount: Amount to approve (in token units)
            private_key: Private key to sign the transaction
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get contract and account
            token_contract = self.w3.eth.contract(address=token_address, abi=self.token_abi)
            account_address = self.w3.eth.account.from_key(private_key).address
            
            # Convert amount to proper format based on token
            if token_address.lower() == WAVAX_ADDRESS.lower():
                # WAVAX has 18 decimals
                amount_wei = self.w3.to_wei(amount, 'ether')
            elif token_address.lower() == BTCB_ADDRESS.lower():
                # BTC.b has 8 decimals
                amount_wei = int(amount * (10 ** BTCB_DECIMALS))
            else:
                # Default to 18 decimals
                amount_wei = int(amount * (10 ** 18))
            
            # Check current allowance
            current_allowance = token_contract.functions.allowance(
                account_address, spender_address
            ).call()
            
            # If allowance is already sufficient, return success
            if current_allowance >= amount_wei:
                return True
            
            # Send approve transaction
            approve_function = token_contract.functions.approve(spender_address, amount_wei)
            tx = build_transaction(self.w3, approve_function, account_address, GAS_LIMIT_BASE)
            signed_tx = sign_transaction(self.w3, tx, private_key)
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            
            # Wait for transaction to be mined
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # Check if transaction was successful
            if receipt.status == 1:
                print(f"Token {token_address} approved successfully")
                return True
            else:
                print(f"Token approval failed: {receipt}")
                return False
                
        except Exception as e:
            print(f"Error approving token: {e}")
            traceback.print_exc()
            return False
            
    def approve_lp_tokens(self, spender_address: str, private_key: str) -> bool:
        """Approve LP tokens for all positions"""
        try:
            # Get account address
            account_address = self.w3.eth.account.from_key(private_key).address
            
            # Prepare the approval function call
            approve_function = self.pool_contract.functions.setApprovalForAll(spender_address, True)
            
            # Build and sign transaction
            tx = build_transaction(self.w3, approve_function, account_address, GAS_LIMIT_BASE)
            signed_tx = sign_transaction(self.w3, tx, private_key)
            
            # Send transaction and wait for receipt
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # Check if transaction was successful
            if receipt.status == 1:
                print(f"LP tokens approved successfully")
                return True
            else:
                print(f"LP token approval failed: {receipt}")
                return False
                
        except Exception as e:
            print(f"Error approving LP tokens: {e}")
            traceback.print_exc()
            return False
            
    def add_liquidity(self, bin_id: int, avax_amount: float, btc_amount: float, private_key: str) -> bool:
        """
        Add liquidity to a specific bin
        
        Args:
            bin_id: Bin ID to add liquidity to
            avax_amount: Amount of AVAX to add
            btc_amount: Amount of BTC.b to add
            private_key: Private key to sign the transaction
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get account address
            account_address = self.w3.eth.account.from_key(private_key).address
            
            # Convert amounts to wei
            avax_wei = 0
            btc_wei = 0
            
            if avax_amount > 0:
                avax_wei = self.w3.to_wei(avax_amount, 'ether')
                
                # Approve WAVAX if needed
                approval_result = self.approve_token(WAVAX_ADDRESS, ROUTER_ADDRESS, avax_amount, private_key)
                if not approval_result:
                    print("Failed to approve WAVAX")
                    return False
            
            if btc_amount > 0:
                btc_wei = int(btc_amount * (10 ** BTCB_DECIMALS))
                
                # Approve BTC.b if needed
                approval_result = self.approve_token(BTCB_ADDRESS, ROUTER_ADDRESS, btc_amount, private_key)
                if not approval_result:
                    print("Failed to approve BTC.b")
                    return False
            
            # Determine token X and Y amounts based on pool configuration
            amount_x = avax_wei if self.is_wavax_x else btc_wei
            amount_y = btc_wei if self.is_wavax_x else avax_wei
            
            # Prepare add liquidity parameters
            token_x = self.token_x
            token_y = self.token_y
            bin_ids = [bin_id]  # Single bin for this operation
            amounts_x = [amount_x]
            amounts_y = [amount_y]
            
            # 5 minutes from now
            deadline = self.w3.eth.get_block('latest').timestamp + 300
            
            # Call router to add liquidity
            add_liquidity_function = self.router_contract.functions.addLiquidity(
                token_x,
                token_y,
                bin_ids,
                amounts_x,
                amounts_y,
                0,  # min amount X
                0,  # min amount Y
                deadline,
                account_address
            )
            
            # Build and sign transaction
            tx = build_transaction(self.w3, add_liquidity_function, account_address, GAS_LIMIT_LARGE)
            signed_tx = sign_transaction(self.w3, tx, private_key)
            
            # Send transaction and wait for receipt
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # Check if transaction was successful
            if receipt.status == 1:
                print(f"Liquidity added successfully to bin {bin_id}")
                
                # Record in database
                self.db.record_operation(
                    operation_type="add",
                    wallet_address=account_address,
                    pool_address=POOL_ADDRESS,
                    bin_id=bin_id,
                    amount_x=avax_amount if self.is_wavax_x else btc_amount,
                    amount_y=btc_amount if self.is_wavax_x else avax_amount,
                    token_x=token_x,
                    token_y=token_y,
                    tx_hash=tx_hash.hex()
                )
                
                # Get LP balance for this bin
                lp_balance = self.get_lp_balance(bin_id, account_address)
                
                # Check if position exists in DB, if not add it
                pos = self.db.get_position_by_bin(account_address, bin_id, POOL_ADDRESS)
                if pos:
                    self.db.update_position(pos['id'], lp_balance)
                else:
                    self.db.add_position(
                        account_address, bin_id, lp_balance,
                        token_x, token_y, POOL_ADDRESS
                    )
                
                return True
            else:
                print(f"Add liquidity failed: {receipt}")
                return False
                
        except Exception as e:
            print(f"Error adding liquidity: {e}")
            traceback.print_exc()
            return False
            
    def remove_liquidity(self, bin_id: int, liquidity_amount: float, private_key: str) -> bool:
        """
        Remove liquidity from a specific bin
        
        Args:
            bin_id: Bin ID to remove liquidity from
            liquidity_amount: Amount of LP tokens to remove (set to 0 to remove all)
            private_key: Private key to sign transaction
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get account address
            account_address = self.w3.eth.account.from_key(private_key).address
            
            # If liquidity_amount is 0, get all available LP tokens
            if liquidity_amount <= 0:
                liquidity_amount = self.get_lp_balance(bin_id, account_address)
                if liquidity_amount <= 0:
                    print(f"No liquidity found in bin {bin_id}")
                    return False
            
            # Convert LP amount to wei (LP tokens have 18 decimals)
            liquidity_wei = int(liquidity_amount * (10 ** 18))
            
            # Approve LP tokens if needed
            approval_result = self.approve_lp_tokens(ROUTER_ADDRESS, private_key)
            if not approval_result:
                print("Failed to approve LP tokens")
                return False
            
            # 5 minutes from now
            deadline = self.w3.eth.get_block('latest').timestamp + 300
            
            # Prepare parameters for remove liquidity
            token_x = self.token_x
            token_y = self.token_y
            bin_ids = [bin_id]
            amounts = [liquidity_wei]
            
            # Call router to remove liquidity
            remove_liquidity_function = self.router_contract.functions.removeLiquidity(
                token_x,
                token_y,
                account_address,
                bin_ids,
                amounts,
                0,  # min amount X
                0,  # min amount Y
                deadline
            )
            
            # Build and sign transaction
            tx = build_transaction(self.w3, remove_liquidity_function, account_address, GAS_LIMIT_LARGE)
            signed_tx = sign_transaction(self.w3, tx, private_key)
            
            # Send transaction and wait for receipt
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # Check if transaction was successful
            if receipt.status == 1:
                print(f"Liquidity removed successfully from bin {bin_id}")
                
                # Record in database
                self.db.record_operation(
                    operation_type="remove",
                    wallet_address=account_address,
                    pool_address=POOL_ADDRESS,
                    bin_id=bin_id,
                    tx_hash=tx_hash.hex(),
                    notes=f"Removed {liquidity_amount} LP tokens"
                )
                
                # Get current LP balance
                current_lp_balance = self.get_lp_balance(bin_id, account_address)
                
                # Update position in database
                pos = self.db.get_position_by_bin(account_address, bin_id, POOL_ADDRESS)
                if pos:
                    if current_lp_balance <= 0:
                        self.db.deactivate_position(pos['id'])
                    else:
                        self.db.update_position(pos['id'], current_lp_balance)
                
                return True
            else:
                print(f"Remove liquidity failed: {receipt}")
                return False
                
        except Exception as e:
            print(f"Error removing liquidity: {e}")
            traceback.print_exc()
            return False
            
    def remove_all_liquidity(self, private_key: str, scan_range: int = 100) -> bool:
        """
        Remove all liquidity from all bins
        
        Args:
            private_key: Private key to sign transaction
            scan_range: How many bins to scan before/after active bin
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get account address
            account_address = self.w3.eth.account.from_key(private_key).address
            
            # Get all positions
            positions = self.get_all_lp_balances(account_address, scan_range=scan_range)
            
            if not positions:
                print("No positions found")
                return False
            
            print(f"Found {len(positions)} positions")
            
            # Approve LP tokens if needed
            approval_result = self.approve_lp_tokens(ROUTER_ADDRESS, private_key)
            if not approval_result:
                print("Failed to approve LP tokens")
                return False
            
            # Prepare parameters for remove liquidity
            bin_ids = []
            amounts = []
            token_x = self.token_x
            token_y = self.token_y
            
            for pos in positions:
                bin_ids.append(pos['bin_id'])
                # Convert LP balance to wei
                lp_amount_wei = int(pos['lp_balance'] * (10 ** 18))
                amounts.append(lp_amount_wei)
            
            # 5 minutes from now
            deadline = self.w3.eth.get_block('latest').timestamp + 300
            
            # Call router to remove liquidity
            remove_liquidity_function = self.router_contract.functions.removeLiquidity(
                token_x,
                token_y,
                account_address,
                bin_ids,
                amounts,
                0,  # min amount X
                0,  # min amount Y
                deadline
            )
            
            # Build and sign transaction
            tx = build_transaction(self.w3, remove_liquidity_function, account_address, GAS_LIMIT_LARGE)
            signed_tx = sign_transaction(self.w3, tx, private_key)
            
            # Send transaction and wait for receipt
            tx_hash = self.w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            print(f"Transaction sent: {tx_hash.hex()}")
            
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
            
            # Check if transaction was successful
            if receipt.status == 1:
                print(f"All liquidity removed successfully from {len(positions)} positions")
                
                # Record in database
                bin_id_list = ", ".join([str(pos['bin_id']) for pos in positions])
                self.db.record_operation(
                    operation_type="remove_all",
                    wallet_address=account_address,
                    pool_address=POOL_ADDRESS,
                    tx_hash=tx_hash.hex(),
                    notes=f"Removed liquidity from bins: {bin_id_list}"
                )
                
                # Mark all positions as inactive
                for pos in positions:
                    db_pos = self.db.get_position_by_bin(account_address, pos['bin_id'], POOL_ADDRESS)
                    if db_pos:
                        self.db.deactivate_position(db_pos['id'])
                
                return True
            else:
                print(f"Remove all liquidity failed: {receipt}")
                return False
                
        except Exception as e:
            print(f"Error removing all liquidity: {e}")
            traceback.print_exc()
            return False 