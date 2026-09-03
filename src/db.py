"""SQLite storage for the explorer, on the standard library's sqlite3.

One connection, used from the event loop thread; every method runs one
transaction. There are no schema migrations: on a schema change, delete the
database file and let the explorer backfill from the node.
"""

import logging
import sqlite3
from typing import Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, TypeVar

from pydantic import TypeAdapter

from models.block import Block
from models.channel_operation import ChannelOperation, channel_operations_of
from models.header.proof_of_leadership import ProofOfLeadership
from models.header.uncle import UncleHeader
from models.transactions.operations.operation import Operation
from models.transactions.transaction import Transaction

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS block (
    id                  INTEGER PRIMARY KEY,
    hash                BLOB    NOT NULL UNIQUE,
    parent_block        BLOB    NOT NULL,
    slot                INTEGER NOT NULL,
    height              INTEGER NOT NULL DEFAULT 0,
    -- True for blocks on the chain the node reports as canonical. Set by
    -- set_canonical_tip; a reorg flips it on the blocks above the common ancestor.
    canonical           INTEGER NOT NULL DEFAULT 0,
    -- Monotonic stamp taken whenever a block becomes canonical. Live streams
    -- cursor on it, so a block that turns canonical in a reorg is still
    -- delivered even though its row id is older than blocks already sent.
    canonical_seq       INTEGER NOT NULL DEFAULT 0,
    block_root          BLOB    NOT NULL,
    proof_of_leadership TEXT    NOT NULL,  -- JSON
    uncles              TEXT    NOT NULL   -- JSON list of uncle headers
);
-- (canonical, height) serves every "walk the chain newest-first" query;
-- parent_block serves ingestion's parent lookups.
CREATE INDEX IF NOT EXISTS ix_block_parent_block ON block (parent_block);
CREATE INDEX IF NOT EXISTS ix_block_height ON block (height);
CREATE INDEX IF NOT EXISTS ix_block_canonical_seq ON block (canonical_seq);
CREATE INDEX IF NOT EXISTS ix_block_canonical_height ON block (canonical, height);

CREATE TABLE IF NOT EXISTS tx (
    id         INTEGER PRIMARY KEY,
    block_id   INTEGER NOT NULL REFERENCES block (id),
    -- Not unique: the same transaction can be included by competing blocks.
    hash       BLOB    NOT NULL,
    operations TEXT    NOT NULL  -- JSON list of operations
);
CREATE INDEX IF NOT EXISTS ix_tx_block_id ON tx (block_id);
CREATE INDEX IF NOT EXISTS ix_tx_hash ON tx (hash);

-- One row per channel operation, written in the same transaction as its
-- block, so channel counts are exact and can be restricted to the canonical chain.
CREATE TABLE IF NOT EXISTS channel_operation (
    id             INTEGER PRIMARY KEY,
    block_id       INTEGER NOT NULL REFERENCES block (id),
    transaction_id INTEGER NOT NULL REFERENCES tx (id),
    channel_id     BLOB    NOT NULL,
    op_type        TEXT    NOT NULL,
    op_index       INTEGER NOT NULL  -- position inside the transaction's operations list
);
CREATE INDEX IF NOT EXISTS ix_channel_operation_block_id ON channel_operation (block_id);
CREATE INDEX IF NOT EXISTS ix_channel_operation_transaction_id ON channel_operation (transaction_id);
CREATE INDEX IF NOT EXISTS ix_channel_operation_channel_id ON channel_operation (channel_id);
"""

_PROOF_JSON = TypeAdapter(ProofOfLeadership)
_UNCLES_JSON = TypeAdapter(List[UncleHeader])
_OPERATIONS_JSON = TypeAdapter(List[Operation])

BLOCK_COLUMNS = (
    "id, hash, parent_block, slot, height, canonical, canonical_seq, block_root, proof_of_leadership, uncles"
)
TX_COLUMNS = "id, block_id, hash, operations"
_BLOCK_COLUMNS_B = ", ".join(f"b.{column}" for column in BLOCK_COLUMNS.split(", "))
_TX_COLUMNS_T = ", ".join(f"t.{column}" for column in TX_COLUMNS.split(", "))

# SQLite's default bound-parameter limit is 32766; stay well under it.
IN_CHUNK = 500

T = TypeVar("T")
TransactionWithBlock = Tuple[Transaction, Block]
ChannelOperationRow = Tuple[ChannelOperation, Transaction, Block]


def _chunks(items: Sequence[T], size: int = IN_CHUNK) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _marks(items: Sequence) -> str:
    return ", ".join("?" * len(items))


def _block(values: Sequence, transactions: Iterable[Transaction] = ()) -> Block:
    id_, hash_, parent, slot, height, canonical, canonical_seq, block_root, proof, uncles = values
    return Block(
        id=id_,
        hash=hash_,
        parent_block=parent,
        slot=slot,
        height=height,
        canonical=bool(canonical),
        canonical_seq=canonical_seq,
        block_root=block_root,
        proof_of_leadership=_PROOF_JSON.validate_json(proof),
        uncles=_UNCLES_JSON.validate_json(uncles),
        transactions=list(transactions),
    )


def _transaction(values: Sequence) -> Transaction:
    id_, block_id, hash_, operations = values
    return Transaction(id=id_, block_id=block_id, hash=hash_, operations=_OPERATIONS_JSON.validate_json(operations))


class Database:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    # --- Blocks --- #

    def store_blocks(self, blocks: List[Block], allow_chain_root: bool = False) -> None:
        """Insert blocks (with their transactions and channel ops) and assign heights from their parents.

        Blocks are stored non-canonical; `set_canonical_tip` (driven by the node's
        reported tip) decides which chain is canonical. Blocks already stored (by
        hash) are skipped. Ids and heights are written back onto the given objects.

        Args:
            allow_chain_root: If True, allow the first block (by slot) to be a chain root
                even if its parent doesn't exist. Used during chain-walk backfills.
        """
        if not blocks:
            return

        with self.conn:
            # The live stream can deliver a block that a chain-walk backfill has
            # just inserted; skip anything we already have.
            already_stored = self._stored_hashes([block.hash for block in blocks])
            blocks = [block for block in blocks if block.hash not in already_stored]
            if not blocks:
                return

            parent_heights = self._heights({block.parent_block for block in blocks})
            blocks_by_hash = {block.hash: block for block in blocks}

            # The chain root candidate: lowest-slot block whose parent is unknown.
            chain_root_hash = None
            if allow_chain_root:
                for block in sorted(blocks, key=lambda b: b.slot):
                    if block.parent_block not in blocks_by_hash and block.parent_block not in parent_heights:
                        chain_root_hash = block.hash
                        break

            # Resolve heights iteratively: a block's parent may be in the database,
            # earlier in this batch, or missing altogether (an orphan, dropped).
            resolved: List[Block] = []
            done: set[bytes] = set()
            orphans: set[bytes] = set()
            for _ in range(len(blocks) * 2):
                made_progress = False
                for block in blocks:
                    if block.hash in done or block.hash in orphans:
                        continue
                    if block.parent_block in parent_heights:
                        block.height = parent_heights[block.parent_block] + 1
                    elif block.parent_block in blocks_by_hash:
                        if block.parent_block in orphans:
                            orphans.add(block.hash)
                            made_progress = True
                        continue  # parent later in the batch; resolved on a later pass
                    elif block.slot == 0 or block.hash == chain_root_hash:
                        block.height = 1  # genesis, or the root of a chain-walk backfill
                    else:
                        orphans.add(block.hash)
                        made_progress = True
                        continue
                    parent_heights[block.hash] = block.height
                    done.add(block.hash)
                    resolved.append(block)
                    made_progress = True
                if not made_progress:
                    break

            for block in blocks:
                if block.hash not in done:
                    logger.warning(
                        f"Dropping unresolvable block: hash={block.hash.hex()}, "
                        f"slot={block.slot}, parent={block.parent_block.hex()}"
                    )

            for block in resolved:
                self._insert_block(block)

    def _insert_block(self, block: Block) -> None:
        cursor = self.conn.execute(
            "INSERT INTO block (hash, parent_block, slot, height, canonical, canonical_seq, block_root,"
            " proof_of_leadership, uncles) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?)",
            (
                block.hash,
                block.parent_block,
                block.slot,
                block.height,
                block.block_root,
                _PROOF_JSON.dump_json(block.proof_of_leadership).decode(),
                _UNCLES_JSON.dump_json(block.uncles).decode(),
            ),
        )
        block.id, block.canonical, block.canonical_seq = cursor.lastrowid, False, 0
        for transaction in block.transactions:
            transaction.block_id = block.id
            cursor = self.conn.execute(
                "INSERT INTO tx (block_id, hash, operations) VALUES (?, ?, ?)",
                (block.id, transaction.hash, _OPERATIONS_JSON.dump_json(transaction.operations).decode()),
            )
            transaction.id = cursor.lastrowid
            self.conn.executemany(
                "INSERT INTO channel_operation (block_id, transaction_id, channel_id, op_type, op_index)"
                " VALUES (?, ?, ?, ?, ?)",
                [
                    (op.block_id, op.transaction_id, op.channel_id, op.op_type, op.op_index)
                    for op in channel_operations_of(transaction)
                ],
            )

    def _stored_hashes(self, hashes: Sequence[bytes]) -> set[bytes]:
        stored: set[bytes] = set()
        for chunk in _chunks(hashes):
            rows = self.conn.execute(f"SELECT hash FROM block WHERE hash IN ({_marks(chunk)})", tuple(chunk))
            stored.update(row[0] for row in rows)
        return stored

    def _heights(self, hashes: Iterable[bytes]) -> Dict[bytes, int]:
        heights: Dict[bytes, int] = {}
        for chunk in _chunks(list(hashes)):
            rows = self.conn.execute(f"SELECT hash, height FROM block WHERE hash IN ({_marks(chunk)})", tuple(chunk))
            heights.update(rows)
        return heights

    def set_canonical_tip(self, tip_hash: bytes) -> int:
        """Make the chain ending at `tip_hash` the canonical one, as the node's fork choice says.

        Walks parent links from the tip until it reaches a block that is already
        canonical (the common ancestor) or the root. Blocks on the old chain above
        the ancestor are un-flagged, the walked path is flagged. A tip that is
        already canonical but below the current canonical height (the node rolled
        back) un-flags everything above it. The tip must already be stored. The
        node's rule is not plain longest-chain, so this accepts a tip on a shorter
        branch as readily as a longer one. Returns the number of blocks changed.
        """
        with self.conn:
            tip = self._chain_link(tip_hash)
            if tip is None:
                raise ValueError(f"Tip {tip_hash.hex()[:16]}... is not stored")

            path_ids: List[int] = []
            current = tip
            while current is not None and not current[3]:
                path_ids.append(current[0])
                current = self._chain_link(current[1])
            ancestor_height = current[2] if current is not None else 0

            if not path_ids:
                # Tip already canonical: drop anything the node no longer considers part of the chain.
                cursor = self.conn.execute(
                    "UPDATE block SET canonical = 0 WHERE canonical = 1 AND height > ?", (tip[2],)
                )
                return cursor.rowcount

            # One stamp per switch: every block flagged here is newer, stream-wise,
            # than anything flagged before, regardless of row id.
            next_seq = self.max_canonical_seq() + 1
            self.conn.execute("UPDATE block SET canonical = 0 WHERE canonical = 1 AND height > ?", (ancestor_height,))
            for chunk in _chunks(path_ids):
                self.conn.execute(
                    f"UPDATE block SET canonical = 1, canonical_seq = ? WHERE id IN ({_marks(chunk)})",
                    (next_seq, *chunk),
                )
            if len(path_ids) > 1:
                logger.info(
                    f"Canonical chain switched: {len(path_ids)} blocks above height {ancestor_height} now canonical"
                )
            return len(path_ids)

    def _chain_link(self, block_hash: bytes) -> Optional[Tuple[int, bytes, int, int]]:
        """(id, parent_block, height, canonical) of a block, or None."""
        return self.conn.execute(
            "SELECT id, parent_block, height, canonical FROM block WHERE hash = ?", (block_hash,)
        ).fetchone()

    def block_by_hash(self, block_hash: bytes) -> Optional[Block]:
        blocks = self._blocks(f"SELECT {BLOCK_COLUMNS} FROM block WHERE hash = ?", (block_hash,))
        return blocks[0] if blocks else None

    def latest_blocks(self, limit: int) -> List[Block]:
        """The newest `limit` canonical blocks, oldest-first."""
        if limit == 0:
            return []
        newest_first = self._blocks(
            f"SELECT {BLOCK_COLUMNS} FROM block WHERE canonical = 1 ORDER BY height DESC LIMIT ?", (limit,)
        )
        return newest_first[::-1]

    def blocks_since(self, canonical_seq: int, *, limit: int = 500) -> List[Block]:
        """Blocks that became canonical after stamp `canonical_seq`, in chain order. Drives the live stream."""
        return self._blocks(
            f"SELECT {BLOCK_COLUMNS} FROM block WHERE canonical = 1 AND canonical_seq > ?"
            " ORDER BY canonical_seq ASC, height ASC LIMIT ?",
            (canonical_seq, limit),
        )

    def max_canonical_seq(self) -> int:
        """The latest canonical stamp; a stream started from here sees only future changes."""
        return self.conn.execute("SELECT MAX(canonical_seq) FROM block").fetchone()[0] or 0

    def paginated_blocks(self, page: int, page_size: int) -> Tuple[List[Block], int]:
        """Canonical blocks, newest first, plus the canonical chain length."""
        total = self.conn.execute("SELECT COUNT(*) FROM block WHERE canonical = 1").fetchone()[0]
        blocks = self._blocks(
            f"SELECT {BLOCK_COLUMNS} FROM block WHERE canonical = 1 ORDER BY height DESC LIMIT ? OFFSET ?",
            (page_size, page * page_size),
        )
        return blocks, total

    def _blocks(self, sql: str, params: tuple = ()) -> List[Block]:
        """Blocks for a query over the block table, with their transactions attached."""
        rows = self.conn.execute(sql, params).fetchall()
        transactions: Dict[int, List[Transaction]] = {row[0]: [] for row in rows}
        for chunk in _chunks(list(transactions)):
            tx_rows = self.conn.execute(
                f"SELECT {TX_COLUMNS} FROM tx WHERE block_id IN ({_marks(chunk)}) ORDER BY id", tuple(chunk)
            )
            for tx_row in tx_rows:
                transactions[tx_row[1]].append(_transaction(tx_row))
        return [_block(row, transactions[row[0]]) for row in rows]

    # --- Transactions --- #
    # Reads return (transaction, block) pairs; the block carries no transactions.

    def transaction_by_hash(self, transaction_hash: bytes) -> Optional[TransactionWithBlock]:
        """The canonical copy if one exists, otherwise the copy from an orphaned block."""
        pairs = self._transactions(
            "WHERE t.hash = ? ORDER BY b.canonical DESC, b.height DESC LIMIT 1", (transaction_hash,)
        )
        return pairs[0] if pairs else None

    def latest_transactions(self, limit: int) -> List[TransactionWithBlock]:
        """The newest `limit` canonical transactions, oldest-first."""
        if limit == 0:
            return []
        newest_first = self._transactions("WHERE b.canonical = 1 ORDER BY b.height DESC, t.id DESC LIMIT ?", (limit,))
        return newest_first[::-1]

    def transactions_since(self, canonical_seq: int, *, limit: int = 500) -> List[TransactionWithBlock]:
        """Transactions whose block became canonical after stamp `canonical_seq`, in chain order."""
        return self._transactions(
            "WHERE b.canonical = 1 AND b.canonical_seq > ?"
            " ORDER BY b.canonical_seq ASC, b.height ASC, t.id ASC LIMIT ?",
            (canonical_seq, limit),
        )

    def search_transactions_by_note(self, note_id: bytes, *, limit: int) -> List[TransactionWithBlock]:
        """Canonical transactions whose operations JSON contains the note id's hex, newest first.

        This is a textual prefilter: the hex could in principle appear in a
        non-note field (signature, public key, metadata), so callers must
        verify which operations actually reference the note.
        """
        return self._transactions(
            "WHERE b.canonical = 1 AND t.operations LIKE ? ORDER BY b.height DESC, t.id DESC LIMIT ?",
            (f"%{note_id.hex()}%", limit),
        )

    def paginated_transactions(self, page: int, page_size: int) -> Tuple[List[TransactionWithBlock], int]:
        """Canonical transactions, newest first, plus the total count."""
        total = self.conn.execute(
            "SELECT COUNT(*) FROM tx t JOIN block b ON b.id = t.block_id WHERE b.canonical = 1"
        ).fetchone()[0]
        pairs = self._transactions(
            "WHERE b.canonical = 1 ORDER BY b.height DESC, t.id DESC LIMIT ? OFFSET ?", (page_size, page * page_size)
        )
        return pairs, total

    def _transactions(self, clause: str, params: tuple) -> List[TransactionWithBlock]:
        rows = self.conn.execute(
            f"SELECT {_TX_COLUMNS_T}, {_BLOCK_COLUMNS_B} FROM tx t JOIN block b ON b.id = t.block_id {clause}", params
        )
        return [(_transaction(row[:4]), _block(row[4:])) for row in rows]

    # --- Channels --- #

    def top_channels(self, *, limit: int) -> List[Tuple[bytes, int, int]]:
        """(channel_id, op_count, last_height) for the most active channels on the canonical chain."""
        rows = self.conn.execute(
            "SELECT c.channel_id, COUNT(*) AS op_count, MAX(b.height) AS last_height"
            " FROM channel_operation c JOIN block b ON b.id = c.block_id"
            " WHERE b.canonical = 1 GROUP BY c.channel_id ORDER BY op_count DESC, last_height DESC LIMIT ?",
            (limit,),
        )
        return [tuple(row) for row in rows]

    def channel_op_count(self, channel_id: bytes) -> int:
        return self.conn.execute(
            "SELECT COUNT(*) FROM channel_operation c JOIN block b ON b.id = c.block_id"
            " WHERE b.canonical = 1 AND c.channel_id = ?",
            (channel_id,),
        ).fetchone()[0]

    def channel_operations(
        self, channel_id: bytes, *, newest_first: bool, offset: int = 0, limit: int
    ) -> List[ChannelOperationRow]:
        """Channel operations with their transaction and block, in chain order."""
        direction = "DESC" if newest_first else "ASC"
        rows = self.conn.execute(
            "SELECT c.id, c.block_id, c.transaction_id, c.channel_id, c.op_type, c.op_index,"
            f" {_TX_COLUMNS_T}, {_BLOCK_COLUMNS_B}"
            " FROM channel_operation c JOIN tx t ON t.id = c.transaction_id JOIN block b ON b.id = c.block_id"
            " WHERE b.canonical = 1 AND c.channel_id = ?"
            f" ORDER BY b.height {direction}, t.id {direction}, c.op_index {direction} LIMIT ? OFFSET ?",
            (channel_id, limit, offset),
        )
        return [
            (
                ChannelOperation(
                    id=row[0],
                    block_id=row[1],
                    transaction_id=row[2],
                    channel_id=row[3],
                    op_type=row[4],
                    op_index=row[5],
                ),
                _transaction(row[6:10]),
                _block(row[10:]),
            )
            for row in rows
        ]
