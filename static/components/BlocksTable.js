// static/pages/BlocksTable.js
import { h } from 'preact';
import { useEffect, useRef } from 'preact/hooks';
import { PAGE, API } from '../lib/api.js';
import { TABLE_SIZE } from '../lib/constants.js';
import { streamNdjson, ensureFixedRowCount, shortenHex } from '../lib/utils.js';

export default function BlocksTable() {
    const bodyRef = useRef(null);
    const countRef = useRef(null);
    const abortRef = useRef(null);
    const seenKeysRef = useRef(new Set());

    useEffect(() => {
        const body = bodyRef.current;
        const counter = countRef.current;

        // 5 columns: Hash | Slot | Parent | Block Root | Transactions
        ensureFixedRowCount(body, 5, TABLE_SIZE);

        abortRef.current?.abort();
        abortRef.current = new AbortController();

        const pruneAndPad = () => {
            // remove any placeholder rows that snuck in
            for (let i = body.rows.length - 1; i >= 0; i--) {
                if (body.rows[i].classList.contains('ph')) body.deleteRow(i);
            }
            // keep at most TABLE_SIZE non-placeholder rows
            while ([...body.rows].filter((r) => !r.classList.contains('ph')).length > TABLE_SIZE) {
                const last = body.rows[body.rows.length - 1];
                const key = last?.dataset?.key;
                if (key) seenKeysRef.current.delete(key);
                body.deleteRow(-1);
            }
            // pad with placeholders to TABLE_SIZE (5 cols)
            ensureFixedRowCount(body, 5, TABLE_SIZE);
            const real = [...body.rows].filter((r) => !r.classList.contains('ph')).length;
            counter.textContent = String(real);
        };

        const navigateToBlockDetail = (blockHash) => {
            history.pushState({}, '', PAGE.BLOCK_DETAIL(blockHash));
            window.dispatchEvent(new PopStateEvent('popstate'));
        };

        const appendRow = (b, key) => {
            const tr = document.createElement('tr');
            tr.dataset.key = key;

            // Hash (clickable, replaces ID)
            const tdId = document.createElement('td');
            const linkId = document.createElement('a');
            linkId.className = 'linkish mono';
            linkId.href = PAGE.BLOCK_DETAIL(b.hash);
            linkId.textContent = shortenHex(b.hash);
            linkId.title = b.hash;
            linkId.addEventListener('click', (e) => {
                e.preventDefault();
                navigateToBlockDetail(b.hash);
            });
            tdId.appendChild(linkId);

            // Slot
            const tdSlot = document.createElement('td');
            const spSlot = document.createElement('span');
            spSlot.className = 'mono';
            spSlot.textContent = String(b.slot);
            tdSlot.appendChild(spSlot);

            // Parent (block.parent_block_hash)
            const tdParent = document.createElement('td');
            const linkParent = document.createElement('a');
            linkParent.className = 'linkish mono';
            linkParent.href = PAGE.BLOCK_DETAIL(b.parent);
            linkParent.textContent = shortenHex(b.parent);
            linkParent.title = b.parent;
            linkParent.addEventListener('click', (e) => {
                e.preventDefault();
                navigateToBlockDetail(b.parent, e);
            });
            tdParent.appendChild(linkParent);

            // Block Root
            const tdRoot = document.createElement('td');
            const spRoot = document.createElement('span');
            spRoot.className = 'mono';
            spRoot.title = b.root;
            spRoot.textContent = shortenHex(b.root);
            tdRoot.appendChild(spRoot);

            // Transactions (array length)
            const tdCount = document.createElement('td');
            const spCount = document.createElement('span');
            spCount.className = 'mono';
            spCount.textContent = String(b.transactionCount);
            tdCount.appendChild(spCount);

            tr.append(tdId, tdSlot, tdParent, tdRoot, tdCount);
            body.insertBefore(tr, body.firstChild);
            pruneAndPad();
        };

        const normalize = (raw) => {
            // New backend:
            // { id, hash, slot, block_root, parent_block_hash, transactions: [...] }
            // Back-compat (header.* / raw.parent_block) just in case.
            const header = raw.header ?? null;
            const txLen = Array.isArray(raw.transactions)
                ? raw.transactions.length
                : Array.isArray(raw.txs)
                  ? raw.txs.length
                  : 0;

            return {
                id: Number(raw.id ?? 0),
                slot: Number(raw.slot ?? header?.slot ?? 0),
                hash: raw.hash ?? header?.hash ?? '',
                parent: raw.parent_block_hash ?? header?.parent_block ?? raw.parent_block ?? '',
                root: raw.block_root ?? header?.block_root ?? '',
                transactionCount: txLen,
            };
        };

        streamNdjson(
            `${API.BLOCKS_STREAM}?prefetch-limit=${encodeURIComponent(TABLE_SIZE)}`,
            (raw) => {
                const b = normalize(raw);
                const key = `${b.id}:${b.slot}`;
                if (seenKeysRef.current.has(key)) {
                    pruneAndPad();
                    return;
                }
                seenKeysRef.current.add(key);
                appendRow(b, key);
            },
            {
                signal: abortRef.current.signal,
                onError: (e) => {
                    console.error('Blocks stream error:', e);
                },
            },
        );

        return () => abortRef.current?.abort();
    }, []);

    return h(
        'div',
        { class: 'card' },
        h(
            'div',
            { class: 'card-header' },
            h('div', null, h('strong', null, 'Blocks '), h('span', { class: 'pill', ref: countRef }, '0')),
            h('div', { style: 'color:var(--muted); fontSize:12px;' }),
        ),
        h(
            'div',
            { class: 'table-wrapper' },
            h(
                'table',
                { class: 'table--blocks' },
                h(
                    'colgroup',
                    null,
                    h('col', { style: 'width:240px' }), // Hash
                    h('col', { style: 'width:90px' }), // Slot
                    h('col', { style: 'width:240px' }), // Parent
                    h('col', { style: 'width:240px' }), // Block Root
                    h('col', { style: 'width:120px' }), // Transactions
                ),
                h(
                    'thead',
                    null,
                    h(
                        'tr',
                        null,
                        h('th', null, 'Hash'),
                        h('th', null, 'Slot'),
                        h('th', null, 'Parent'),
                        h('th', null, 'Block Root'),
                        h('th', null, 'Transactions'),
                    ),
                ),
                h('tbody', { ref: bodyRef }),
            ),
        ),
    );
}
