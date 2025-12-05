# modules/absurdia_pkg/absurdia_db.py
# Database layer for Absurdia creature battle game

import sqlite3
import json
import threading
import time
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone

class AbsurdiaDatabase:
    """Manages SQLite database for Absurdia game"""

    def __init__(self, db_path: Path, templates_path: Path):
        self.db_path = db_path
        self.templates_path = templates_path
        self._lock = threading.RLock()
        self.templates: Dict[str, Dict[str, Any]] = {}

        self._initialize_db()
        self._load_templates()

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_db(self):
        """Create all tables if they don't exist"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Players table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS players (
                    user_id TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    coins INTEGER DEFAULT 1000,
                    total_arena_wins INTEGER DEFAULT 0,
                    total_arena_losses INTEGER DEFAULT 0,
                    current_win_streak INTEGER DEFAULT 0,
                    best_win_streak INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_daily_reset TIMESTAMP,
                    daily_care_count INTEGER DEFAULT 0,
                    last_explored TIMESTAMP
                )
            ''')

            # Migration: Add daily_care_count column if it doesn't exist
            try:
                cursor.execute('ALTER TABLE players ADD COLUMN daily_care_count INTEGER DEFAULT 0')
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Migration: Add last_explored column if it doesn't exist
            try:
                cursor.execute('ALTER TABLE players ADD COLUMN last_explored TIMESTAMP')
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Creatures table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS creatures (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    nickname TEXT,
                    rarity TEXT NOT NULL,
                    creature_type TEXT NOT NULL,

                    base_hp INTEGER NOT NULL,
                    base_attack INTEGER NOT NULL,
                    base_defense INTEGER NOT NULL,
                    base_speed INTEGER NOT NULL,

                    bonus_hp INTEGER DEFAULT 0,
                    bonus_attack INTEGER DEFAULT 0,
                    bonus_defense INTEGER DEFAULT 0,
                    bonus_speed INTEGER DEFAULT 0,

                    happiness INTEGER DEFAULT 50,
                    owner_local_id INTEGER,
                    last_fed TIMESTAMP,
                    last_played TIMESTAMP,
                    last_petted TIMESTAMP,

                    total_wins INTEGER DEFAULT 0,
                    total_losses INTEGER DEFAULT 0,

                    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    submitted_to_arena BOOLEAN DEFAULT 0,

                    FOREIGN KEY (owner_id) REFERENCES players(user_id),
                    UNIQUE(owner_id, name)
                )
            ''')

            # Migration: Add owner_local_id column if it doesn't exist
            try:
                cursor.execute('ALTER TABLE creatures ADD COLUMN owner_local_id INTEGER')
            except sqlite3.OperationalError:
                pass  # Column already exists

            # Ensure unique index for per-owner numbering
            cursor.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_owner_local
                ON creatures(owner_id, owner_local_id)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_owner_name ON creatures(owner_id, name)
            ''')

            # Pending catches table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS pending_catches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    creature_name TEXT NOT NULL,

                    new_rarity TEXT NOT NULL,
                    new_hp INTEGER NOT NULL,
                    new_attack INTEGER NOT NULL,
                    new_defense INTEGER NOT NULL,
                    new_speed INTEGER NOT NULL,
                    new_creature_type TEXT NOT NULL,

                    trap_quality TEXT NOT NULL,

                    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,

                    FOREIGN KEY (owner_id) REFERENCES players(user_id)
                )
            ''')

            # Active traps table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS active_traps (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    trap_quality TEXT NOT NULL,
                    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    ready_at TIMESTAMP NOT NULL,
                    collected BOOLEAN DEFAULT 0,

                    FOREIGN KEY (owner_id) REFERENCES players(user_id)
                )
            ''')

            # Migration: Add auto_announced column if it doesn't exist
            try:
                cursor.execute('ALTER TABLE active_traps ADD COLUMN auto_announced BOOLEAN DEFAULT 0')
            except sqlite3.OperationalError as e:
                # Only swallow the error if the column already exists
                error_msg = str(e).lower()
                if "duplicate column" in error_msg or "already exists" in error_msg:
                    pass  # Column already exists - migration is idempotent
                else:
                    raise  # Unexpected error - re-raise it

            # Arena matches table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS arena_matches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER NOT NULL,
                    creature1_id INTEGER NOT NULL,
                    creature2_id INTEGER NOT NULL,
                    winner_id INTEGER,

                    creature1_hp_remaining INTEGER,
                    creature2_hp_remaining INTEGER,
                    total_rounds INTEGER,
                    type_advantage TEXT,

                    fought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (creature1_id) REFERENCES creatures(id),
                    FOREIGN KEY (creature2_id) REFERENCES creatures(id),
                    FOREIGN KEY (winner_id) REFERENCES creatures(id)
                )
            ''')

            # Training sessions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS training_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    creature_id INTEGER NOT NULL,
                    stat_trained TEXT NOT NULL,
                    improvement INTEGER NOT NULL,
                    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

                    FOREIGN KEY (creature_id) REFERENCES creatures(id)
                )
            ''')

            # Inventory table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    owner_id TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity INTEGER DEFAULT 1,

                    FOREIGN KEY (owner_id) REFERENCES players(user_id),
                    UNIQUE(owner_id, item_type, item_name)
                )
            ''')

            conn.commit()
            # Backfill owner_local_id if needed
            self._backfill_owner_local_ids(conn)

            conn.close()

    def _backfill_owner_local_ids(self, conn: sqlite3.Connection) -> None:
        """Assign owner_local_id sequentially per owner if missing."""
        cursor = conn.cursor()

        # Check if column exists
        cursor.execute("PRAGMA table_info(creatures)")
        cols = [row[1] for row in cursor.fetchall()]
        if "owner_local_id" not in cols:
            return

        cursor.execute('SELECT COUNT(*) as cnt FROM creatures WHERE owner_local_id IS NULL')
        missing_count = cursor.fetchone()['cnt']
        if missing_count == 0:
            return

        cursor.execute('SELECT owner_id, id FROM creatures WHERE owner_local_id IS NULL ORDER BY owner_id, caught_at, id')
        rows = cursor.fetchall()

        counters = {}
        for row in rows:
            owner_id = row['owner_id']
            counters.setdefault(owner_id, 0)
            counters[owner_id] += 1
            cursor.execute(
                'UPDATE creatures SET owner_local_id = ? WHERE id = ?',
                (counters[owner_id], row['id'])
            )

        conn.commit()

    def _get_next_owner_local_id(self, cursor: sqlite3.Cursor, owner_id: str) -> int:
        """Return the next available per-owner creature number."""
        cursor.execute('SELECT MAX(owner_local_id) as max_local FROM creatures WHERE owner_id = ?', (owner_id,))
        row = cursor.fetchone()
        max_local = row['max_local'] if row and row['max_local'] is not None else 0
        return max_local + 1

    def _load_templates(self):
        """Load creature templates from JSON file"""
        if not self.templates_path.exists():
            print(f"[absurdia] WARNING: Templates file not found at {self.templates_path}")
            return

        try:
            with open(self.templates_path, 'r') as f:
                data = json.load(f)
                creatures = data.get('creatures', [])

                # Index by name for quick lookup
                self.templates = {c['name']: c for c in creatures}
                print(f"[absurdia] Loaded {len(self.templates)} creature templates")
        except Exception as e:
            print(f"[absurdia] ERROR loading templates: {e}")

    # ============= PLAYER OPERATIONS =============

    def get_player(self, user_id: str, username: str) -> Dict[str, Any]:
        """Get player data, creating if doesn't exist"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if row:
                conn.close()
                return dict(row)

            # Create new player
            cursor.execute('''
                INSERT INTO players (user_id, username, coins)
                VALUES (?, ?, 300)
            ''', (user_id, username))
            conn.commit()

            cursor.execute('SELECT * FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()
            return dict(row)

    def update_player_coins(self, user_id: str, amount: int) -> int:
        """Add or subtract coins from player. Returns new total."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Read current coins first
            cursor.execute('SELECT coins FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            current_coins = row['coins']

            # Compute new total and validate
            new_total = current_coins + amount
            if new_total < 0:
                conn.close()
                raise ValueError(f"Insufficient coins: current={current_coins}, amount={amount}, would result in {new_total}")

            # Update only if valid
            cursor.execute('UPDATE players SET coins = ? WHERE user_id = ?', (new_total, user_id))
            conn.commit()
            conn.close()
            return new_total

    def get_player_coins(self, user_id: str) -> int:
        """Get player's current coin balance"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT coins FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            conn.close()
            return row['coins'] if row else 0

    def check_and_reset_daily_care(self, user_id: str) -> int:
        """
        Check if daily reset is needed (midnight UTC), reset if so.
        Returns current care count.
        """
        from datetime import datetime, timezone

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT daily_care_count, last_daily_reset FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()

            if not row:
                conn.close()
                return 0

            current_count = row['daily_care_count'] or 0
            last_reset = row['last_daily_reset']

            # Check if we need to reset (new day in UTC)
            now = datetime.now(timezone.utc)
            today = now.date()

            if last_reset:
                last_reset_date = datetime.fromisoformat(last_reset.replace('Z', '+00:00')).date()
                if last_reset_date < today:
                    # New day - reset count
                    cursor.execute(
                        'UPDATE players SET daily_care_count = 0, last_daily_reset = ? WHERE user_id = ?',
                        (now.isoformat(), user_id)
                    )
                    conn.commit()
                    current_count = 0
            else:
                # First time - set last_daily_reset
                cursor.execute(
                    'UPDATE players SET last_daily_reset = ? WHERE user_id = ?',
                    (now.isoformat(), user_id)
                )
                conn.commit()

            conn.close()
            return current_count

    def increment_daily_care(self, user_id: str) -> int:
        """
        Increment daily care count by 1.
        Returns new count.
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'UPDATE players SET daily_care_count = daily_care_count + 1 WHERE user_id = ?',
                (user_id,)
            )
            cursor.execute('SELECT daily_care_count FROM players WHERE user_id = ?', (user_id,))
            row = cursor.fetchone()
            new_count = row['daily_care_count'] if row else 0

            conn.commit()
            conn.close()
            return new_count

    def update_player_exploration(self, user_id: str):
        """Update last_explored timestamp to now"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            now = datetime.now(timezone.utc).isoformat()
            cursor.execute('UPDATE players SET last_explored = ? WHERE user_id = ?', (now, user_id))
            
            conn.commit()
            conn.close()

    # ============= CREATURE OPERATIONS =============

    def get_creature(self, creature_id: int) -> Optional[Dict[str, Any]]:
        """Get creature by global ID"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM creatures WHERE id = ?', (creature_id,))
            row = cursor.fetchone()
            conn.close()

            return dict(row) if row else None

    def get_creature_by_local(self, owner_id: str, owner_local_id: int) -> Optional[Dict[str, Any]]:
        """Get creature by per-owner number"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT * FROM creatures WHERE owner_id = ? AND owner_local_id = ?',
                (owner_id, owner_local_id)
            )
            row = cursor.fetchone()
            conn.close()

            return dict(row) if row else None

    def get_player_creatures(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all creatures owned by player"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM creatures WHERE owner_id = ? ORDER BY owner_local_id', (user_id,))
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def get_all_creatures(self) -> List[Dict[str, Any]]:
        """Get ALL creatures (for maintenance tasks)"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('SELECT * FROM creatures')
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def has_creature_type(self, user_id: str, creature_name: str) -> bool:
        """Check if player already owns this creature type"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT COUNT(*) as count FROM creatures WHERE owner_id = ? AND name = ?',
                (user_id, creature_name)
            )
            count = cursor.fetchone()['count']
            conn.close()

            return count > 0

    def create_creature(self, owner_id: str, creature_name: str, rarity: str,
                       creature_type: str, hp: int, attack: int, defense: int, speed: int,
                       owner_local_id: Optional[int] = None) -> int:
        """Create a new creature. Returns creature_id."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            if owner_local_id is None:
                owner_local_id = self._get_next_owner_local_id(cursor, owner_id)

            cursor.execute('''
                INSERT INTO creatures (owner_id, name, rarity, creature_type,
                                     base_hp, base_attack, base_defense, base_speed, owner_local_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (owner_id, creature_name, rarity, creature_type, hp, attack, defense, speed, owner_local_id))

            creature_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return creature_id

    def update_creature_happiness(self, creature_id: int, happiness: int):
        """Update creature's happiness (clamped 0-100)"""
        happiness = max(0, min(100, happiness))

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('UPDATE creatures SET happiness = ? WHERE id = ?', (happiness, creature_id))
            conn.commit()
            conn.close()

    def update_creature_care_timestamp(self, creature_id: int, care_type: str):
        """Update last_fed, last_played, or last_petted timestamp"""
        field_map = {
            'feed': 'last_fed',
            'play': 'last_played',
            'pet': 'last_petted'
        }

        field = field_map.get(care_type)
        if not field:
            return

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            now = datetime.now(timezone.utc).isoformat()
            cursor.execute(f'UPDATE creatures SET {field} = ? WHERE id = ?', (now, creature_id))
            conn.commit()
            conn.close()

    def set_creature_nickname(self, creature_id: int, nickname: str):
        """Set creature's nickname"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('UPDATE creatures SET nickname = ? WHERE id = ?', (nickname, creature_id))
            conn.commit()
            conn.close()

    def delete_creature(self, creature_id: int):
        """Delete a creature (for release)"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('DELETE FROM creatures WHERE id = ?', (creature_id,))
            conn.commit()
            conn.close()

    # ============= PENDING CATCH OPERATIONS =============

    def create_pending_catch(self, owner_id: str, creature_name: str, rarity: str,
                            creature_type: str, hp: int, attack: int, defense: int,
                            speed: int, trap_quality: str, timeout_seconds: int = 30) -> int:
        """Create a pending catch for duplicate handling. Returns pending_id."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            now = datetime.now(timezone.utc)
            expires = now + timedelta(seconds=timeout_seconds)

            cursor.execute('''
                INSERT INTO pending_catches
                (owner_id, creature_name, new_rarity, new_hp, new_attack, new_defense,
                 new_speed, new_creature_type, trap_quality, caught_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (owner_id, creature_name, rarity, hp, attack, defense, speed,
                  creature_type, trap_quality, now.isoformat(), expires.isoformat()))

            pending_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return pending_id

    def get_pending_catch(self, owner_id: str) -> Optional[Dict[str, Any]]:
        """Get active pending catch for player. Cleans up expired entries."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Clean up expired
            now = datetime.now(timezone.utc).isoformat()
            cursor.execute('DELETE FROM pending_catches WHERE expires_at < ?', (now,))

            # Get active pending
            cursor.execute(
                'SELECT * FROM pending_catches WHERE owner_id = ? ORDER BY caught_at DESC LIMIT 1',
                (owner_id,)
            )
            row = cursor.fetchone()

            conn.commit()
            conn.close()

            return dict(row) if row else None

    def resolve_pending_catch(self, owner_id: str, keep_new: bool, trap_refund_percent: float, trap_prices: Optional[Dict[str, int]] = None) -> Tuple[int, Optional[int]]:
        """
        Resolve a pending catch.

        Args:
            owner_id: The user ID of the creature owner
            keep_new: Whether to keep the new creature (True) or the existing one (False)
            trap_refund_percent: Percentage of trap cost to refund (0.0-1.0)
            trap_prices: Dict with keys 'basic','standard','premium','deluxe' from config.
                        If None or missing keys, falls back to defaults.

        Returns: (coin_refund, new_creature_id or None)
        """
        pending = self.get_pending_catch(owner_id)
        if not pending:
            return 0, None

        # Default trap costs (fallback if config not provided)
        default_trap_costs = {
            'basic': 50,
            'standard': 150,
            'premium': 400,
            'deluxe': 1000
        }

        # Use provided trap_prices with fallback to defaults for missing keys
        if trap_prices is None:
            trap_prices = default_trap_costs

        trap_cost = trap_prices.get(pending['trap_quality'], default_trap_costs.get(pending['trap_quality'], 50))
        refund = int(trap_cost * trap_refund_percent)

        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            new_creature_id = None

            if keep_new:
                cursor.execute(
                    'SELECT id, owner_local_id FROM creatures WHERE owner_id = ? AND name = ? LIMIT 1',
                    (owner_id, pending['creature_name'])
                )
                current_row = cursor.fetchone()
                current_local_id = current_row['owner_local_id'] if current_row else None

                # Delete old creature
                cursor.execute('DELETE FROM creatures WHERE owner_id = ? AND name = ?',
                             (owner_id, pending['creature_name']))

                if current_local_id is None:
                    current_local_id = self._get_next_owner_local_id(cursor, owner_id)

                # Create new creature
                cursor.execute('''
                    INSERT INTO creatures (owner_id, name, rarity, creature_type,
                                         base_hp, base_attack, base_defense, base_speed, owner_local_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (owner_id, pending['creature_name'], pending['new_rarity'],
                      pending['new_creature_type'], pending['new_hp'], pending['new_attack'],
                      pending['new_defense'], pending['new_speed'], current_local_id))

                new_creature_id = cursor.lastrowid

            # Delete pending catch
            cursor.execute('DELETE FROM pending_catches WHERE id = ?', (pending['id'],))

            # Add refund
            cursor.execute('UPDATE players SET coins = coins + ? WHERE user_id = ?',
                         (refund, owner_id))

            conn.commit()
            conn.close()

            return refund, new_creature_id

    def clear_pending_catch(self, owner_id: str):
        """Clear any pending catch for player"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('DELETE FROM pending_catches WHERE owner_id = ?', (owner_id,))
            conn.commit()
            conn.close()

    # ============= COLLECTION STATS =============

    def get_collection_progress(self, owner_id: str) -> Tuple[int, int]:
        """Returns (owned_count, total_possible_count)"""
        owned = len(self.get_player_creatures(owner_id))
        total = len(self.templates)
        return owned, total

    # ============= TRAP OPERATIONS =============

    def create_trap(self, owner_id: str, trap_quality: str, ready_time: datetime) -> int:
        """Create a new active trap. Returns trap_id."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO active_traps (owner_id, trap_quality, ready_at)
                VALUES (?, ?, ?)
            ''', (owner_id, trap_quality, ready_time.isoformat()))

            trap_id = cursor.lastrowid
            conn.commit()
            conn.close()

            return trap_id

    def get_active_traps(self, owner_id: str) -> List[Dict[str, Any]]:
        """Get all active traps for player"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT * FROM active_traps WHERE owner_id = ? AND collected = 0 ORDER BY ready_at',
                (owner_id,)
            )
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def mark_trap_collected(self, trap_id: int):
        """Mark trap as collected"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('UPDATE active_traps SET collected = 1 WHERE id = ?', (trap_id,))
            conn.commit()
            conn.close()

    def get_traps_for_auto_collect(self, auto_collect_hours: int) -> List[Dict[str, Any]]:
        """Get traps that need auto-collection (ready + auto_collect_hours has passed)"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            # Calculate the cutoff time
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=auto_collect_hours)

            cursor.execute('''
                SELECT * FROM active_traps
                WHERE collected = 0
                AND auto_announced = 0
                AND ready_at <= ?
                ORDER BY ready_at
            ''', (cutoff_time.isoformat(),))

            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def mark_trap_auto_announced(self, trap_id: int):
        """Mark trap as auto-announced"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('UPDATE active_traps SET auto_announced = 1 WHERE id = ?', (trap_id,))
            conn.commit()
            conn.close()

    # ============= INVENTORY OPERATIONS =============

    def add_item(self, owner_id: str, item_type: str, item_name: str, quantity: int = 1):
        """Add items to inventory"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO inventory (owner_id, item_type, item_name, quantity)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(owner_id, item_type, item_name)
                DO UPDATE SET quantity = quantity + ?
            ''', (owner_id, item_type, item_name, quantity, quantity))

            conn.commit()
            conn.close()

    def remove_item(self, owner_id: str, item_type: str, item_name: str, quantity: int = 1) -> bool:
        """Remove items from inventory. Returns True if successful."""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT quantity FROM inventory WHERE owner_id = ? AND item_type = ? AND item_name = ?',
                (owner_id, item_type, item_name)
            )
            row = cursor.fetchone()

            if not row or row['quantity'] < quantity:
                conn.close()
                return False

            new_qty = row['quantity'] - quantity

            if new_qty <= 0:
                cursor.execute(
                    'DELETE FROM inventory WHERE owner_id = ? AND item_type = ? AND item_name = ?',
                    (owner_id, item_type, item_name)
                )
            else:
                cursor.execute(
                    'UPDATE inventory SET quantity = ? WHERE owner_id = ? AND item_type = ? AND item_name = ?',
                    (new_qty, owner_id, item_type, item_name)
                )

            conn.commit()
            conn.close()
            return True

    def get_inventory(self, owner_id: str) -> List[Dict[str, Any]]:
        """Get all items in player's inventory"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT * FROM inventory WHERE owner_id = ? ORDER BY item_type, item_name',
                (owner_id,)
            )
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def get_item_count(self, owner_id: str, item_type: str, item_name: str) -> int:
        """Get quantity of specific item"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT quantity FROM inventory WHERE owner_id = ? AND item_type = ? AND item_name = ?',
                (owner_id, item_type, item_name)
            )
            row = cursor.fetchone()
            conn.close()

            return row['quantity'] if row else 0

    # ============= ARENA METHODS =============

    def submit_creature_to_arena(self, creature_id: int, submitted: bool) -> None:
        """
        Set creature's arena submission status.

        Args:
            creature_id: ID of creature
            submitted: True to submit, False to withdraw
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'UPDATE creatures SET submitted_to_arena = ? WHERE id = ?',
                (1 if submitted else 0, creature_id)
            )

            conn.commit()
            conn.close()

    def get_arena_queue(self) -> List[Dict[str, Any]]:
        """Get all creatures currently in arena queue"""
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            cursor.execute(
                'SELECT * FROM creatures WHERE submitted_to_arena = 1 ORDER BY owner_id, owner_local_id'
            )
            rows = cursor.fetchall()
            conn.close()

            return [dict(row) for row in rows]

    def update_creature_wins_losses(self, creature_id: int, won: bool) -> None:
        """
        Update creature's win/loss record.

        Args:
            creature_id: ID of creature
            won: True if won, False if lost
        """
        with self._lock:
            conn = self._get_connection()
            cursor = conn.cursor()

            if won:
                cursor.execute(
                    'UPDATE creatures SET total_wins = total_wins + 1 WHERE id = ?',
                    (creature_id,)
                )
            else:
                cursor.execute(
                    'UPDATE creatures SET total_losses = total_losses + 1 WHERE id = ?',
                    (creature_id,)
                )

            conn.commit()
            conn.close()
