from typing import Optional
from datetime import datetime
import sqlite3
from dataclasses import dataclass


@dataclass
class Run:
    id: Optional[int]
    dttm: datetime
    completion_token_usage: int
    prompt_token_usage: int
    server_knowledge: str

    @classmethod
    def from_row(cls, row):
        return cls(
            id=row[0],
            dttm=datetime.fromisoformat(row[1]),
            completion_token_usage=row[2],
            prompt_token_usage=row[3],
            server_knowledge=row[4]
        )


@dataclass
class TouchedTransaction:
    transaction_id: str
    payee: str
    category_name: Optional[str]  # None means the tool looked at it but couldn't resolve it -- see `note`
    source: str
    is_override: bool
    dttm: datetime
    note: Optional[str] = None  # why it's unresolved, when category_name is None

    @classmethod
    def from_row(cls, row):
        return cls(
            transaction_id=row[0],
            payee=row[1],
            category_name=row[2],
            source=row[3],
            is_override=bool(row[4]),
            dttm=datetime.fromisoformat(row[5]),
            note=row[6],
        )


class RunStore:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = sqlite3.connect(self.db_path)
        self.create_table()

    def create_table(self):
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS runs (
                id INTEGER PRIMARY KEY,
                dttm TIMESTAMP,
                completion_token_usage INTEGER,
                prompt_token_usage INTEGER,
                server_knowledge TEXT
            )
        ''')
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS touched_transactions (
                transaction_id TEXT PRIMARY KEY,
                payee TEXT,
                category_name TEXT,
                source TEXT,
                is_override INTEGER,
                dttm TIMESTAMP
            )
        ''')
        try:
            cursor.execute('ALTER TABLE touched_transactions ADD COLUMN note TEXT')
        except sqlite3.OperationalError:
            pass  # already migrated
        self.conn.commit()

    def record_touched(self, touched: list['TouchedTransaction']):
        """Upserts, so re-touching a transaction (e.g. Claude changes its mind on a later run,
        or an unresolved item gets picked up successfully next time) updates the existing row
        instead of duplicating it.
        """
        cursor = self.conn.cursor()
        cursor.executemany('''
            INSERT INTO touched_transactions (transaction_id, payee, category_name, source, is_override, dttm, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(transaction_id) DO UPDATE SET
                payee=excluded.payee, category_name=excluded.category_name,
                source=excluded.source, is_override=excluded.is_override, dttm=excluded.dttm,
                note=excluded.note
        ''', [
            (t.transaction_id, t.payee, t.category_name, t.source, int(t.is_override), t.dttm.isoformat(), t.note)
            for t in touched
        ])
        self.conn.commit()

    def get_touched(self) -> dict[str, 'TouchedTransaction']:
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM touched_transactions')
        return {row[0]: TouchedTransaction.from_row(row) for row in cursor.fetchall()}

    def forget_touched(self, transaction_ids: list[str]):
        """Drops rows once a transaction is no longer unapproved (approved in the app, or its
        category was wiped back to blank), so the pending-approval table doesn't grow stale.
        """
        cursor = self.conn.cursor()
        cursor.executemany('DELETE FROM touched_transactions WHERE transaction_id = ?', [(tid,) for tid in transaction_ids])
        self.conn.commit()

    def add_run(self, run: Run):
        cursor = self.conn.cursor()
        cursor.execute('''
            INSERT INTO runs (id, dttm, completion_token_usage, prompt_token_usage, server_knowledge)
            VALUES (?, ?, ?, ?, ?)
        ''', (run.id, run.dttm.isoformat(), run.completion_token_usage, run.prompt_token_usage, run.server_knowledge))
        self.conn.commit()

    def get_runs(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM runs')
        rows = cursor.fetchall()
        return [
            Run.from_row(row)
            for row in rows
        ]
    

    def get_last_run(self):
        cursor = self.conn.cursor()
        cursor.execute('SELECT * FROM runs ORDER BY dttm DESC LIMIT 1')
        row = cursor.fetchone()
        if row:
            return Run.from_row(row)
        else:
            return None

    def close(self):
        self.conn.close()
