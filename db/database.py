import sqlite3
import os
import datetime
from typing import Dict, List, Tuple, Any, Optional

class LiquidityDatabase:
    """Database to track all liquidity operations"""
    
    def __init__(self, db_path: str = 'db/liquidity_tracker.db'):
        """Initialize the database connection"""
        # Ensure the directory exists
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.cursor = self.conn.cursor()
        
        # Create tables if they don't exist
        self._create_tables()
    
    def _create_tables(self):
        """Create the necessary tables if they don't exist"""
        # Table for tracking liquidity positions
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            wallet_address TEXT NOT NULL,
            bin_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            token_x TEXT NOT NULL,
            token_y TEXT NOT NULL,
            pool_address TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            active BOOLEAN DEFAULT 1
        )
        ''')
        
        # Table for tracking operations (add/remove liquidity)
        self.cursor.execute('''
        CREATE TABLE IF NOT EXISTS operations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            operation_type TEXT NOT NULL,
            wallet_address TEXT NOT NULL,
            bin_id INTEGER,
            amount_x REAL,
            amount_y REAL,
            token_x TEXT,
            token_y TEXT,
            pool_address TEXT NOT NULL,
            tx_hash TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        )
        ''')
        
        # Commit the changes
        self.conn.commit()
    
    def add_position(self, wallet_address: str, bin_id: int, amount: float, 
                     token_x: str, token_y: str, pool_address: str) -> int:
        """
        Record a new liquidity position
        
        Args:
            wallet_address: The wallet address that owns the position
            bin_id: The bin ID of the position
            amount: The amount of LP tokens
            token_x: Token X address
            token_y: Token Y address
            pool_address: The liquidity pool address
            
        Returns:
            The ID of the newly added position
        """
        self.cursor.execute('''
        INSERT INTO positions 
        (wallet_address, bin_id, amount, token_x, token_y, pool_address) 
        VALUES (?, ?, ?, ?, ?, ?)
        ''', (wallet_address, bin_id, amount, token_x, token_y, pool_address))
        
        self.conn.commit()
        return self.cursor.lastrowid
    
    def update_position(self, position_id: int, new_amount: float, active: bool = True) -> bool:
        """
        Update an existing position
        
        Args:
            position_id: The ID of the position to update
            new_amount: The new amount of LP tokens
            active: Whether the position is active
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.cursor.execute('''
            UPDATE positions 
            SET amount = ?, active = ?, timestamp = CURRENT_TIMESTAMP
            WHERE id = ?
            ''', (new_amount, active, position_id))
            
            self.conn.commit()
            return True
        except Exception as e:
            print(f"Error updating position: {e}")
            return False
    
    def deactivate_position(self, position_id: int) -> bool:
        """Mark a position as inactive (fully withdrawn)"""
        return self.update_position(position_id, 0, False)
    
    def get_active_positions(self, wallet_address: str, pool_address: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all active positions for a wallet
        
        Args:
            wallet_address: The wallet address to get positions for
            pool_address: Optional pool address to filter by
            
        Returns:
            List of active positions
        """
        query = '''
        SELECT id, wallet_address, bin_id, amount, token_x, token_y, pool_address, timestamp 
        FROM positions 
        WHERE wallet_address = ? AND active = 1
        '''
        params = [wallet_address]
        
        if pool_address:
            query += ' AND pool_address = ?'
            params.append(pool_address)
        
        self.cursor.execute(query, params)
        
        columns = [column[0] for column in self.cursor.description]
        results = []
        
        for row in self.cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        return results
    
    def get_position_by_bin(self, wallet_address: str, bin_id: int, pool_address: str) -> Optional[Dict[str, Any]]:
        """Get a specific position by bin ID"""
        self.cursor.execute('''
        SELECT id, wallet_address, bin_id, amount, token_x, token_y, pool_address, timestamp 
        FROM positions 
        WHERE wallet_address = ? AND bin_id = ? AND pool_address = ? AND active = 1
        ''', (wallet_address, bin_id, pool_address))
        
        row = self.cursor.fetchone()
        if not row:
            return None
            
        columns = [column[0] for column in self.cursor.description]
        return dict(zip(columns, row))
    
    def record_operation(self, operation_type: str, wallet_address: str, pool_address: str, 
                         bin_id: Optional[int] = None, amount_x: Optional[float] = None, 
                         amount_y: Optional[float] = None, token_x: Optional[str] = None, 
                         token_y: Optional[str] = None, tx_hash: Optional[str] = None, 
                         notes: Optional[str] = None) -> int:
        """
        Record an operation (add/remove liquidity)
        
        Args:
            operation_type: Type of operation ('add', 'remove', 'remove_all')
            wallet_address: Wallet performing the operation
            pool_address: Pool address
            bin_id: Bin ID (can be None for operations like remove_all)
            amount_x: Amount of token X
            amount_y: Amount of token Y
            token_x: Token X address
            token_y: Token Y address
            tx_hash: Transaction hash
            notes: Additional notes
            
        Returns:
            The ID of the newly added operation
        """
        self.cursor.execute('''
        INSERT INTO operations 
        (operation_type, wallet_address, bin_id, amount_x, amount_y, token_x, token_y, pool_address, tx_hash, notes) 
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (operation_type, wallet_address, bin_id, amount_x, amount_y, token_x, token_y, pool_address, tx_hash, notes))
        
        self.conn.commit()
        return self.cursor.lastrowid
    
    def get_operations(self, wallet_address: str, operation_type: Optional[str] = None, 
                      limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent operations for a wallet"""
        query = '''
        SELECT * FROM operations 
        WHERE wallet_address = ?
        '''
        params = [wallet_address]
        
        if operation_type:
            query += ' AND operation_type = ?'
            params.append(operation_type)
        
        query += ' ORDER BY timestamp DESC LIMIT ?'
        params.append(limit)
        
        self.cursor.execute(query, params)
        
        columns = [column[0] for column in self.cursor.description]
        results = []
        
        for row in self.cursor.fetchall():
            results.append(dict(zip(columns, row)))
        
        return results
    
    def close(self):
        """Close the database connection"""
        if self.conn:
            self.conn.close()
            
    def __enter__(self):
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close() 