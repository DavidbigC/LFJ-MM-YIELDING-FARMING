import json
import os
from web3 import Web3
from dotenv import load_dotenv, set_key
from .config import CHAIN_ID

# Load environment variables
load_dotenv()

def load_wallet():
    """
    Load wallet from environment variable
    
    Returns:
        str: The private key if found, None otherwise
    """
    private_key = os.getenv('WALLET_PRIVATE_KEY')
    if not private_key:
        print("No wallet found. Please create one first or set your WALLET_PRIVATE_KEY in .env file.")
        return None
    return private_key

def get_wallet_address(private_key):
    """
    Get the wallet address from a private key
    
    Args:
        private_key (str): The private key
        
    Returns:
        str: The wallet address
    """
    if not private_key:
        return None
        
    try:
        account = Web3().eth.account.from_key(private_key)
        return account.address
    except Exception as e:
        print(f"Error getting wallet address: {e}")
        return None

def create_wallet():
    """
    Create a new EVM wallet
    
    Returns:
        tuple: (address, private_key) if successful, (None, None) otherwise
    """
    try:
        account = Web3().eth.account.create()
        private_key = account._private_key.hex()
        address = account.address
        
        print(f"New wallet created!")
        print(f"Address: {address}")
        print("IMPORTANT: Save your private key in a secure place. It will only be shown once.")
        print(f"Private Key: {private_key}")
        
        # Ask user if they want to save to .env
        save_choice = input("Do you want to save this wallet to .env file? (y/n): ")
        if save_choice.lower() == 'y':
            # Create .env file if it doesn't exist
            if not os.path.exists('.env'):
                with open('.env', 'w') as f:
                    f.write("# Environment Variables\n")
            
            # Save to .env file
            set_key('.env', 'WALLET_ADDRESS', address)
            set_key('.env', 'WALLET_PRIVATE_KEY', private_key)
            print("Wallet information saved to .env file.")
            print("WARNING: Keep your .env file secure and never share it.")
        
        return address, private_key
    
    except Exception as e:
        print(f"Error creating wallet: {e}")
        return None, None

def sign_transaction(w3, tx, private_key):
    """
    Sign a transaction with a private key
    
    Args:
        w3 (Web3): Web3 instance
        tx (dict): Transaction object
        private_key (str): Private key
        
    Returns:
        HexBytes: Signed transaction
    """
    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
    return signed_tx

def build_transaction(w3, function_call, account_address, gas_limit, value=0):
    """
    Build a transaction for a contract function call
    
    Args:
        w3 (Web3): Web3 instance
        function_call: The contract function call
        account_address (str): The sender address
        gas_limit (int): Gas limit for the transaction
        value (int): ETH value to send with the transaction
        
    Returns:
        dict: Transaction object
    """
    return function_call.build_transaction({
        'from': account_address,
        'nonce': w3.eth.get_transaction_count(account_address),
        'gas': gas_limit,
        'gasPrice': w3.eth.gas_price,
        'chainId': CHAIN_ID,
        'value': value
    }) 