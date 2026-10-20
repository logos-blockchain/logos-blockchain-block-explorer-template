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
from models.transactions.references import ReferenceKind, TransactionReference, references_of
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
    uncles              TEXT    NOT NULL,  -- JSON list of uncle headers
    tx_count            INTEGER NOT NULL,
    -- Transactions in this block and all its stored ancestors. Fixed once written,
    -- since a block's ancestry never changes: on the canonical chain it is the
    -- transaction total up to this block, which pages transactions without counting.
    chain_tx_count      INTEGER NOT NULL
);
-- (canonical, height) serves every "walk the chain newest-first" query;
-- parent_block serves ingestion's parent lookups.
CREATE INDEX IF NOT EXISTS ix_block_parent_block ON block (parent_block);
CREATE INDEX IF NOT EXISTS ix_block_height ON block (height);
CREATE INDEX IF NOT EXISTS ix_block_canonical_seq ON block (canonical_seq);
CREATE INDEX IF NOT EXISTS ix_block_canonical_height ON block (canonical, height);
-- Finds the canonical block holding the Nth transaction; height breaks ties with empty blocks.
CREATE INDEX IF NOT EXISTS ix_block_canonical_chain_tx_count ON block (canonical, chain_tx_count, height);

-- Rows below copy their block's `height`, which never changes, so canonical,
-- newest-first reads walk an index in display order, check each row's block,
-- and stop after a page instead of joining every candidate and sorting.
-- channel_operation also copies `canonical` (kept in step by _set_canonical), so
-- a deep channel page skips rows within the index alone. Its rows are few and
-- narrow, so flipping them is cheap; flipping tx (wide operations JSON) or
-- tx_reference (about three rows per transaction) took ~20 s for a testnet sync.

CREATE TABLE IF NOT EXISTS tx (
    id         INTEGER PRIMARY KEY,
    block_id   INTEGER NOT NULL REFERENCES block (id),
    height     INTEGER NOT NULL,
    -- Not unique: the same transaction can be included by competing blocks.
    hash       BLOB    NOT NULL,
    operations TEXT    NOT NULL  -- JSON list of operations
);
CREATE INDEX IF NOT EXISTS ix_tx_block_id ON tx (block_id);
CREATE INDEX IF NOT EXISTS ix_tx_hash ON tx (hash);
CREATE INDEX IF NOT EXISTS ix_tx_height ON tx (height, id);

-- One row per channel operation, written in the same transaction as its
-- block, so channel counts are exact and can be restricted to the canonical chain.
CREATE TABLE IF NOT EXISTS channel_operation (
    id             INTEGER PRIMARY KEY,
    block_id       INTEGER NOT NULL REFERENCES block (id),
    transaction_id INTEGER NOT NULL REFERENCES tx (id),
    height         INTEGER NOT NULL,
    canonical      INTEGER NOT NULL,
    channel_id     BLOB    NOT NULL,
    op_type        TEXT    NOT NULL,
    op_index       INTEGER NOT NULL  -- position inside the transaction's operations list
);
CREATE INDEX IF NOT EXISTS ix_channel_operation_block_id ON channel_operation (block_id);
CREATE INDEX IF NOT EXISTS ix_channel_operation_channel_order
    ON channel_operation (channel_id, canonical, height, transaction_id, op_index);

-- Per-channel totals over the canonical chain, adjusted whenever blocks change
-- canonical state, so ranking channels and counting a channel's ops are lookups.
CREATE TABLE IF NOT EXISTS channel (
    channel_id  BLOB    PRIMARY KEY,
    op_count    INTEGER NOT NULL,
    last_height INTEGER NOT NULL
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS ix_channel_activity ON channel (op_count, last_height);

-- One row per note id or public key an operation names (see models.transactions.references),
-- written with its transaction, so searching by either is an index lookup.
CREATE TABLE IF NOT EXISTS tx_reference (
    id             INTEGER PRIMARY KEY,
    block_id       INTEGER NOT NULL REFERENCES block (id),
    transaction_id INTEGER NOT NULL REFERENCES tx (id),
    height         INTEGER NOT NULL,
    kind           TEXT    NOT NULL,  -- 'note' or 'public_key'
    key            BLOB    NOT NULL,
    op_index       INTEGER NOT NULL,
    field          TEXT    NOT NULL,
    item_index     INTEGER            -- position in a list field
);
CREATE INDEX IF NOT EXISTS ix_tx_reference_key ON tx_reference (kind, key, height, transaction_id);
"""

_PROOF_JSON = TypeAdapter(ProofOfLeadership)
_UNCLES_JSON = TypeAdapter(List[UncleHeader])
_OPERATIONS_JSON = TypeAdapter(List[Operation])

BLOCK_COLUMNS = (
    "id, hash, parent_block, slot, height, canonical, canonical_seq, block_root, proof_of_leadership, uncles,"
    " tx_count"
)
TX_COLUMNS = "id, block_id, hash, operations"
_BLOCK_COLUMNS_B = ", ".join(f"b.{column}" for column in BLOCK_COLUMNS.split(", "))
_TX_COLUMNS_T = ", ".join(f"t.{column}" for column in TX_COLUMNS.split(", "))

# SQLite's default bound-parameter limit is 32766; stay well under it.
IN_CHUNK = 500

T = TypeVar("T")
TransactionWithBlock = Tuple[Transaction, Block]
ChannelOperationRow = Tuple[ChannelOperation, Transaction, Block]
ReferencingTransaction = Tuple[Transaction, Block, List[TransactionReference]]


def _chunks(items: Sequence[T], size: int = IN_CHUNK) -> Iterator[Sequence[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def _marks(items: Sequence) -> str:
    return ", ".join("?" * len(items))


def _block(values: Sequence, transactions: Iterable[Transaction] = ()) -> Block:
    id_, hash_, parent, slot, height, canonical, canonical_seq, block_root, proof, uncles, tx_count = values
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
        transaction_count=tx_count,
        transactions=list(transactions),
    )


def _transaction(values: Sequence) -> Transaction:
    id_, block_id, hash_, operations = values
    return Transaction(id=id_, block_id=block_id, hash=hash_, operations=_OPERATIONS_JSON.validate_json(operations))


class Database:
    def __init__(self, path: str) -> None:
        self.conn = sqlite3.connect(path)
        # WAL with synchronous=NORMAL syncs at checkpoints rather than every commit; a
        # power cut can lose only the latest commits, which ingestion fetches again.
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA synchronous = NORMAL")
        # The default page cache is 2 MB; the testnet database is over 600 MB.
        self.conn.execute("PRAGMA cache_size = -65536")  # KiB, so 64 MiB
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

            # hash -> (height, chain_tx_count) for parents already stored, then for each block as it resolves.
            positions = self._chain_positions({block.parent_block for block in blocks})
            blocks_by_hash = {block.hash: block for block in blocks}

            # The chain root candidate: lowest-slot block whose parent is unknown.
            chain_root_hash = None
            if allow_chain_root:
                for block in sorted(blocks, key=lambda b: b.slot):
                    if block.parent_block not in blocks_by_hash and block.parent_block not in positions:
                        chain_root_hash = block.hash
                        break

            # Resolve heights iteratively: a block's parent may be in the database,
            # earlier in this batch, or missing altogether (an orphan, dropped).
            resolved: List[Tuple[Block, int]] = []  # with its chain_tx_count
            done: set[bytes] = set()
            orphans: set[bytes] = set()
            for _ in range(len(blocks) * 2):
                made_progress = False
                for block in blocks:
                    if block.hash in done or block.hash in orphans:
                        continue
                    if block.parent_block in positions:
                        parent_height, parent_chain_tx_count = positions[block.parent_block]
                        block.height = parent_height + 1
                    elif block.parent_block in blocks_by_hash:
                        if block.parent_block in orphans:
                            orphans.add(block.hash)
                            made_progress = True
                        continue  # parent later in the batch; resolved on a later pass
                    elif block.slot == 0 or block.hash == chain_root_hash:
                        block.height = 1  # genesis, or the root of a chain-walk backfill
                        parent_chain_tx_count = 0
                    else:
                        orphans.add(block.hash)
                        made_progress = True
                        continue
                    chain_tx_count = parent_chain_tx_count + len(block.transactions)
                    positions[block.hash] = (block.height, chain_tx_count)
                    done.add(block.hash)
                    resolved.append((block, chain_tx_count))
                    made_progress = True
                if not made_progress:
                    break

            for block in blocks:
                if block.hash not in done:
                    logger.warning(
                        f"Dropping unresolvable block: hash={block.hash.hex()}, "
                        f"slot={block.slot}, parent={block.parent_block.hex()}"
                    )

            for block, chain_tx_count in resolved:
                self._insert_block(block, chain_tx_count)

    def _insert_block(self, block: Block, chain_tx_count: int) -> None:
        cursor = self.conn.execute(
            "INSERT INTO block (hash, parent_block, slot, height, canonical, canonical_seq, block_root,"
            " proof_of_leadership, uncles, tx_count, chain_tx_count) VALUES (?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)",
            (
                block.hash,
                block.parent_block,
                block.slot,
                block.height,
                block.block_root,
                _PROOF_JSON.dump_json(block.proof_of_leadership).decode(),
                _UNCLES_JSON.dump_json(block.uncles).decode(),
                len(block.transactions),
                chain_tx_count,
            ),
        )
        block.id, block.canonical, block.canonical_seq = cursor.lastrowid, False, 0
        block.transaction_count = len(block.transactions)
        for transaction in block.transactions:
            transaction.block_id = block.id
            cursor = self.conn.execute(
                "INSERT INTO tx (block_id, height, hash, operations) VALUES (?, ?, ?, ?)",
                (block.id, block.height, transaction.hash, _OPERATIONS_JSON.dump_json(transaction.operations).decode()),
            )
            transaction.id = cursor.lastrowid
            self.conn.executemany(
                "INSERT INTO channel_operation (block_id, transaction_id, height, canonical, channel_id, op_type,"
                " op_index) VALUES (?, ?, ?, 0, ?, ?, ?)",
                [
                    (op.block_id, op.transaction_id, block.height, op.channel_id, op.op_type, op.op_index)
                    for op in channel_operations_of(transaction)
                ],
            )
            self.conn.executemany(
                "INSERT INTO tx_reference (block_id, transaction_id, height, kind, key, op_index, field, item_index)"
                " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (r.block_id, r.transaction_id, block.height, r.kind, r.key, r.op_index, r.field, r.item_index)
                    for r in references_of(transaction)
                ],
            )

    def _stored_hashes(self, hashes: Sequence[bytes]) -> set[bytes]:
        stored: set[bytes] = set()
        for chunk in _chunks(hashes):
            rows = self.conn.execute(f"SELECT hash FROM block WHERE hash IN ({_marks(chunk)})", tuple(chunk))
            stored.update(row[0] for row in rows)
        return stored

    def _chain_positions(self, hashes: Iterable[bytes]) -> Dict[bytes, Tuple[int, int]]:
        """hash -> (height, chain_tx_count) for the stored blocks among `hashes`."""
        positions: Dict[bytes, Tuple[int, int]] = {}
        for chunk in _chunks(list(hashes)):
            rows = self.conn.execute(
                f"SELECT hash, height, chain_tx_count FROM block WHERE hash IN ({_marks(chunk)})", tuple(chunk)
            )
            positions.update((hash_, (height, count)) for hash_, height, count in rows)
        return positions

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
                return self._set_canonical(self._canonical_ids_above(tip[2]), False)

            # One stamp per switch: every block flagged here is newer, stream-wise,
            # than anything flagged before, regardless of row id.
            next_seq = self.max_canonical_seq() + 1
            self._set_canonical(self._canonical_ids_above(ancestor_height), False)
            self._set_canonical(path_ids, True, canonical_seq=next_seq)
            if len(path_ids) > 1:
                logger.info(
                    f"Canonical chain switched: {len(path_ids)} blocks above height {ancestor_height} now canonical"
                )
            return len(path_ids)

    def _canonical_ids_above(self, height: int) -> List[int]:
        return self._ids("SELECT id FROM block WHERE canonical = 1 AND height > ?", (height,))

    def _set_canonical(self, block_ids: List[int], canonical: bool, *, canonical_seq: Optional[int] = None) -> int:
        """Flip blocks (all currently the other way) and the state derived from them; returns the count.

        Channel ops carry their block's flag, and the channel table's totals move
        by the ops gained or lost, so both stay exact through reorgs.
        """
        flag = int(canonical)
        channel_deltas: Dict[bytes, int] = {}
        for chunk in _chunks(block_ids):
            marks, ids = _marks(chunk), tuple(chunk)
            if canonical_seq is None:
                self.conn.execute(f"UPDATE block SET canonical = ? WHERE id IN ({marks})", (flag, *ids))
            else:
                self.conn.execute(
                    f"UPDATE block SET canonical = ?, canonical_seq = ? WHERE id IN ({marks})",
                    (flag, canonical_seq, *ids),
                )
            self.conn.execute(f"UPDATE channel_operation SET canonical = ? WHERE block_id IN ({marks})", (flag, *ids))
            rows = self.conn.execute(
                f"SELECT channel_id, COUNT(*) FROM channel_operation WHERE block_id IN ({marks}) GROUP BY channel_id",
                ids,
            )
            for channel_id, count in rows:
                channel_deltas[channel_id] = channel_deltas.get(channel_id, 0) + (count if canonical else -count)

        for channel_id, delta in channel_deltas.items():
            self.conn.execute(
                "INSERT INTO channel (channel_id, op_count, last_height) VALUES (?, ?, 0)"
                " ON CONFLICT (channel_id) DO UPDATE SET op_count = op_count + excluded.op_count",
                (channel_id, delta),
            )
            self.conn.execute("DELETE FROM channel WHERE channel_id = ? AND op_count = 0", (channel_id,))
            self.conn.execute(
                "UPDATE channel SET last_height = (SELECT MAX(height) FROM channel_operation"
                " WHERE channel_id = ?1 AND canonical = 1) WHERE channel_id = ?1",
                (channel_id,),
            )
        return len(block_ids)

    def _chain_link(self, block_hash: bytes) -> Optional[Tuple[int, bytes, int, int]]:
        """(id, parent_block, height, canonical) of a block, or None."""
        return self.conn.execute(
            "SELECT id, parent_block, height, canonical FROM block WHERE hash = ?", (block_hash,)
        ).fetchone()

    def block_by_hash(self, block_hash: bytes) -> Optional[Block]:
        blocks = self._blocks(f"SELECT {BLOCK_COLUMNS} FROM block WHERE hash = ?", (block_hash,))
        return blocks[0] if blocks else None

    # Block lists and the live stream show summaries, so they load blocks without
    # their transactions (`transaction_count` is stored on the block).

    def latest_blocks(self, limit: int) -> List[Block]:
        """The newest `limit` canonical blocks, oldest-first, without their transactions."""
        if limit == 0:
            return []
        newest_first = self._blocks(
            f"SELECT {BLOCK_COLUMNS} FROM block WHERE canonical = 1 ORDER BY height DESC LIMIT ?",
            (limit,),
            with_transactions=False,
        )
        return newest_first[::-1]

    def blocks_since(self, canonical_seq: int, *, limit: int = 500) -> List[Block]:
        """Blocks that became canonical after stamp `canonical_seq`, in chain order, without their transactions.

        Drives the live stream.
        """
        return self._blocks(
            f"SELECT {BLOCK_COLUMNS} FROM block WHERE canonical = 1 AND canonical_seq > ?"
            " ORDER BY canonical_seq ASC, height ASC LIMIT ?",
            (canonical_seq, limit),
            with_transactions=False,
        )

    def max_canonical_seq(self) -> int:
        """The latest canonical stamp; a stream started from here sees only future changes."""
        return self.conn.execute("SELECT MAX(canonical_seq) FROM block").fetchone()[0] or 0

    def paginated_blocks(self, page: int, page_size: int) -> Tuple[List[Block], int]:
        """Canonical blocks, newest first and without their transactions, plus the canonical chain length.

        The canonical chain is one unbroken run of heights, so its length and a
        page's first height follow from its two ends.
        """
        lowest = self.conn.execute("SELECT MIN(height) FROM block WHERE canonical = 1").fetchone()[0]
        highest = self.conn.execute("SELECT MAX(height) FROM block WHERE canonical = 1").fetchone()[0]
        if highest is None:
            return [], 0
        blocks = self._blocks(
            f"SELECT {BLOCK_COLUMNS} FROM block WHERE canonical = 1 AND height <= ? ORDER BY height DESC LIMIT ?",
            (highest - page * page_size, page_size),
            with_transactions=False,
        )
        return blocks, highest - lowest + 1

    def _blocks(self, sql: str, params: tuple = (), *, with_transactions: bool = True) -> List[Block]:
        """Blocks for a query over the block table, with their transactions attached unless told otherwise."""
        rows = self.conn.execute(sql, params).fetchall()
        transactions: Dict[int, List[Transaction]] = {row[0]: [] for row in rows}
        for chunk in _chunks(list(transactions) if with_transactions else []):
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
        ids = self._ids(
            "SELECT t.id FROM tx t CROSS JOIN block b ON b.id = t.block_id WHERE b.canonical = 1"
            " ORDER BY t.height DESC, t.id DESC LIMIT ?",
            (limit,),
        )
        return self._transactions_by_id(ids)[::-1]

    def transactions_since(self, canonical_seq: int, *, limit: int = 500) -> List[TransactionWithBlock]:
        """Transactions whose block became canonical after stamp `canonical_seq`, in chain order."""
        return self._transactions(
            "WHERE b.canonical = 1 AND b.canonical_seq > ?"
            " ORDER BY b.canonical_seq ASC, b.height ASC, t.id ASC LIMIT ?",
            (canonical_seq, limit),
        )

    def transactions_referencing(self, kind: ReferenceKind, key: bytes, *, limit: int) -> List[ReferencingTransaction]:
        """Canonical transactions naming a note id or public key, newest first, with the fields that name it.

        Walks the reference index newest-first and stops after `limit` transactions.
        """
        rows = self.conn.execute(
            "SELECT r.transaction_id, r.block_id, r.op_index, r.field, r.item_index"
            " FROM tx_reference r CROSS JOIN block b ON b.id = r.block_id"
            " WHERE r.kind = ? AND r.key = ? AND b.canonical = 1 ORDER BY r.height DESC, r.transaction_id DESC",
            (kind, key),
        )
        references: Dict[int, List[TransactionReference]] = {}
        for transaction_id, block_id, op_index, field, item_index in rows:
            if transaction_id not in references:
                if len(references) == limit:
                    break
                references[transaction_id] = []
            references[transaction_id].append(
                TransactionReference(
                    block_id=block_id,
                    transaction_id=transaction_id,
                    kind=kind,
                    key=key,
                    op_index=op_index,
                    field=field,
                    item_index=item_index,
                )
            )
        for found in references.values():
            found.sort(key=lambda reference: (reference.op_index, reference.item_index or 0))
        pairs = self._transactions_by_id(list(references))
        return [(transaction, block, references[transaction.id]) for transaction, block in pairs]

    def paginated_transactions(self, page: int, page_size: int) -> Tuple[List[TransactionWithBlock], int]:
        """Canonical transactions, newest first, plus the total count.

        The tip's chain_tx_count is the total, and the block holding a page's
        first transaction is found by its chain_tx_count, so a deep page costs the
        same as the first.
        """
        tip = self.conn.execute(
            "SELECT chain_tx_count FROM block WHERE canonical = 1 ORDER BY height DESC LIMIT 1"
        ).fetchone()
        total = tip[0] if tip else 0
        # 1-based position, counting from the oldest, of the page's newest transaction.
        position = total - page * page_size
        if position < 1:
            return [], total
        height, chain_tx_count = self.conn.execute(
            "SELECT height, chain_tx_count FROM block WHERE canonical = 1 AND chain_tx_count >= ?"
            " ORDER BY chain_tx_count, height LIMIT 1",
            (position,),
        ).fetchone()
        ids = self._ids(
            "SELECT t.id FROM tx t CROSS JOIN block b ON b.id = t.block_id WHERE t.height <= ? AND b.canonical = 1"
            " ORDER BY t.height DESC, t.id DESC LIMIT ? OFFSET ?",
            (height, page_size, chain_tx_count - position),  # skip that block's transactions newer than it
        )
        return self._transactions_by_id(ids), total

    def _transactions(self, clause: str, params: tuple) -> List[TransactionWithBlock]:
        ids = self._ids(f"SELECT t.id FROM tx t JOIN block b ON b.id = t.block_id {clause}", params)
        return self._transactions_by_id(ids)

    def _transactions_by_id(self, ids: List[int]) -> List[TransactionWithBlock]:
        rows = self._rows_by_id(
            f"SELECT {_TX_COLUMNS_T}, {_BLOCK_COLUMNS_B} FROM tx t JOIN block b ON b.id = t.block_id WHERE t.id IN",
            ids,
        )
        return [(_transaction(row[:4]), _block(row[4:])) for row in rows]

    # Paged and sorted reads pick their ids first, then load the rows. Sorting the
    # full rows would drag every candidate's operations and proof JSON through
    # SQLite's sorter only to keep a page of them.
    #
    # Newest-first reads of transactions and references walk the child table's
    # (height, ...) index and check each row's block is canonical, stopping after
    # a page. They use CROSS JOIN, which fixes that join order: left to choose,
    # SQLite drives from block's canonical index and sorts every canonical row.

    def _ids(self, sql: str, params: tuple) -> List[int]:
        return [row[0] for row in self.conn.execute(sql, params)]

    def _rows_by_id(self, sql: str, ids: List[int]) -> List[tuple]:
        """Rows for `sql` (ending in "WHERE <id column> IN", the id selected first), in the order of `ids`."""
        by_id: Dict[int, tuple] = {}
        for chunk in _chunks(ids):
            by_id.update((row[0], row) for row in self.conn.execute(f"{sql} ({_marks(chunk)})", tuple(chunk)))
        return [by_id[id_] for id_ in ids if id_ in by_id]

    # --- Channels --- #

    def top_channels(self, *, limit: int) -> List[Tuple[bytes, int, int]]:
        """(channel_id, op_count, last_height) for the most active channels on the canonical chain."""
        rows = self.conn.execute(
            "SELECT channel_id, op_count, last_height FROM channel ORDER BY op_count DESC, last_height DESC LIMIT ?",
            (limit,),
        )
        return [tuple(row) for row in rows]

    def channel_op_count(self, channel_id: bytes) -> int:
        row = self.conn.execute("SELECT op_count FROM channel WHERE channel_id = ?", (channel_id,)).fetchone()
        return row[0] if row else 0

    def channel_operations(
        self, channel_id: bytes, *, newest_first: bool, offset: int = 0, limit: int
    ) -> List[ChannelOperationRow]:
        """Channel operations with their transaction and block, in chain order."""
        direction = "DESC" if newest_first else "ASC"
        ids = self._ids(
            "SELECT id FROM channel_operation WHERE channel_id = ? AND canonical = 1"
            f" ORDER BY height {direction}, transaction_id {direction}, op_index {direction} LIMIT ? OFFSET ?",
            (channel_id, limit, offset),
        )
        rows = self._rows_by_id(
            "SELECT c.id, c.block_id, c.transaction_id, c.channel_id, c.op_type, c.op_index,"
            f" {_TX_COLUMNS_T}, {_BLOCK_COLUMNS_B}"
            " FROM channel_operation c JOIN tx t ON t.id = c.transaction_id JOIN block b ON b.id = c.block_id"
            " WHERE c.id IN",
            ids,
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
