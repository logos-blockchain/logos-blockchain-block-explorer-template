// static/pages/TransactionsTable.js
import { h } from 'preact';
import { useEffect, useRef } from 'preact/hooks';
import { API } from '../lib/api.js';
import { TABLE_SIZE } from '../lib/constants.js';
import {
    streamNdjson,
    ensureFixedRowCount,
    shortenHex, // (kept in case you want to use later)
    withBenignFilter,
} from '../lib/utils.js';

const OPERATIONS_PREVIEW_LIMIT = 2;

// ---------- small DOM helpers ----------
function createSpan(className, text, title) {
    const el = document.createElement('span');
    if (className) el.className = className;
    if (title) el.title = title;
    el.textContent = text;
    return el;
}

function createLink(href, text, title) {
    const el = document.createElement('a');
    el.className = 'linkish mono';
    el.href = href;
    if (title) el.title = title;
    el.textContent = text;
    return el;
}

// ---------- coercion / formatting helpers ----------
const toNumber = (v) => {
    if (v == null) return 0;
    if (typeof v === 'number') return v;
    if (typeof v === 'bigint') return Number(v);
    if (typeof v === 'string') {
        const s = v.trim();
        if (/^0x[0-9a-f]+$/i.test(s)) return Number(BigInt(s));
        const n = Number(s);
        return Number.isFinite(n) ? n : 0;
    }
    if (typeof v === 'object' && v !== null && 'value' in v) return toNumber(v.value);
    return 0;
};

const opLabel = (op) => {
    if (op == null) return 'op';
    if (typeof op === 'string' || typeof op === 'number') return String(op);
    if (typeof op !== 'object') return String(op);
    if (typeof op.type === 'string') return op.type;
    if (typeof op.kind === 'string') return op.kind;
    if (op.content) {
        if (typeof op.content.type === 'string') return op.content.type;
        if (typeof op.content.kind === 'string') return op.content.kind;
    }
    const keys = Object.keys(op);
    return keys.length ? keys[0] : 'op';
};

function formatOperationsPreview(ops) {
    if (!ops?.length) return '—';
    const labels = ops.map(opLabel);
    if (labels.length <= OPERATIONS_PREVIEW_LIMIT) return labels.join(', ');
    const head = labels.slice(0, OPERATIONS_PREVIEW_LIMIT).join(', ');
    const remainder = labels.length - OPERATIONS_PREVIEW_LIMIT;
    return `${head} +${remainder}`;
}

// ---------- normalize API → view model ----------
function normalizeTransaction(raw) {
    // { id, block_id, hash, operations:[Operation], inputs:[HexBytes], outputs:[Note], proof, execution_gas_price, storage_gas_price, created_at? }
    const ops = Array.isArray(raw?.operations) ? raw.operations : Array.isArray(raw?.ops) ? raw.ops : [];

    const outputs = Array.isArray(raw?.outputs) ? raw.outputs : [];
    const totalOutputValue = outputs.reduce((sum, note) => sum + toNumber(note?.value), 0);

    return {
        id: raw?.id ?? '',
        hash: raw?.hash ?? '',
        operations: ops,
        executionGasPrice: toNumber(raw?.execution_gas_price),
        storageGasPrice: toNumber(raw?.storage_gas_price),
        numberOfOutputs: outputs.length,
        totalOutputValue,
    };
}

// ---------- row builder ----------
function buildTransactionRow(tx) {
    const tr = document.createElement('tr');

    // Hash (replaces ID)
    const tdId = document.createElement('td');
    tdId.className = 'mono';
    tdId.appendChild(createLink(`/transactions/${tx.hash}`, shortenHex(tx.hash), tx.hash));

    // Operations (preview)
    const tdOps = document.createElement('td');
    const preview = formatOperationsPreview(tx.operations);
    tdOps.appendChild(
        createSpan('', preview, Array.isArray(tx.operations) ? tx.operations.map(opLabel).join(', ') : ''),
    );

    // Outputs (count / total)
    const tdOut = document.createElement('td');
    tdOut.className = 'amount';
    tdOut.textContent = `${tx.numberOfOutputs} / ${tx.totalOutputValue.toLocaleString(undefined, { maximumFractionDigits: 8 })}`;

    // Gas (execution / storage)
    const tdGas = document.createElement('td');
    tdGas.className = 'mono';
    tdGas.textContent = `${tx.executionGasPrice.toLocaleString()} / ${tx.storageGasPrice.toLocaleString()}`;

    tr.append(tdId, tdOps, tdOut, tdGas);
    return tr;
}

// ---------- component ----------
export default function TransactionsTable() {
    const bodyRef = useRef(null);
    const countRef = useRef(null);
    const abortRef = useRef(null);
    const totalCountRef = useRef(0);

    useEffect(() => {
        const body = bodyRef.current;
        const counter = countRef.current;

        // 4 columns: Hash | Operations | Outputs | Gas
        ensureFixedRowCount(body, 4, TABLE_SIZE);

        abortRef.current?.abort();
        abortRef.current = new AbortController();

        const url = `${API.TRANSACTIONS_STREAM}?prefetch-limit=${encodeURIComponent(TABLE_SIZE)}`;

        streamNdjson(
            url,
            (raw) => {
                try {
                    const tx = normalizeTransaction(raw);
                    const row = buildTransactionRow(tx);
                    body.insertBefore(row, body.firstChild);

                    while (body.rows.length > TABLE_SIZE) body.deleteRow(-1);
                    counter.textContent = String(++totalCountRef.current);
                } catch (err) {
                    console.error('Failed to render transaction row:', err, raw);
                }
            },
            {
                signal: abortRef.current.signal,
                onError: withBenignFilter(
                    (err) => console.error('Transactions stream error:', err),
                    abortRef.current.signal,
                ),
            },
        ).catch((err) => {
            if (!abortRef.current.signal.aborted) {
                console.error('Transactions stream connection error:', err);
            }
        });

        return () => abortRef.current?.abort();
    }, []);

    return h(
        'div',
        { class: 'card' },
        h(
            'div',
            { class: 'card-header' },
            h('div', null, h('strong', null, 'Transactions '), h('span', { class: 'pill', ref: countRef }, '0')),
            h('div', { style: 'color:var(--muted); font-size:12px;' }),
        ),
        h(
            'div',
            { class: 'table-wrapper' },
            h(
                'table',
                { class: 'table--transactions' },
                h(
                    'colgroup',
                    null,
                    h('col', { style: 'width:240px' }), // Hash
                    h('col', null), // Operations
                    h('col', { style: 'width:200px' }), // Outputs (count / total)
                    h('col', { style: 'width:200px' }), // Gas (execution / storage)
                ),
                h(
                    'thead',
                    null,
                    h(
                        'tr',
                        null,
                        h('th', null, 'Hash'),
                        h('th', null, 'Operations'),
                        h('th', null, 'Outputs (count / total)'),
                        h('th', null, 'Gas (execution / storage)'),
                    ),
                ),
                h('tbody', { ref: bodyRef }),
            ),
        ),
    );
}
