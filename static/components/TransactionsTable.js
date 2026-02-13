// static/pages/TransactionsTable.js
import { h } from 'preact';
import { useEffect, useRef } from 'preact/hooks';
import { API, PAGE } from '../lib/api.js';
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

function tryDecodeUtf8Hex(hex) {
    if (typeof hex !== 'string' || hex.length === 0 || hex.length % 2 !== 0) return null;
    try {
        const bytes = new Uint8Array(hex.length / 2);
        for (let i = 0; i < hex.length; i += 2) {
            const b = parseInt(hex.substring(i, i + 2), 16);
            if (Number.isNaN(b)) return null;
            bytes[i / 2] = b;
        }
        const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
        if (/[\x20-\x7e]/.test(text)) return text;
        return null;
    } catch {
        return null;
    }
}

function opPreview(op) {
    const content = op?.content ?? op;
    const type = content?.type ?? (typeof op === 'string' ? op : 'op');

    if (type === 'ChannelInscribe' && content) {
        const chanShort = typeof content.channel_id === 'string' ? content.channel_id.slice(0, 8) : '?';
        let inscPreview = '';
        if (typeof content.inscription === 'string') {
            const decoded = tryDecodeUtf8Hex(content.inscription);
            if (decoded != null) {
                inscPreview = decoded.length > 20 ? decoded.slice(0, 20) + '\u2026' : decoded;
            } else {
                inscPreview = content.inscription.slice(0, 12) + '\u2026';
            }
        }
        return `${type}(${chanShort}\u2026, ${inscPreview})`;
    }

    if (type === 'ChannelBlob' && content) {
        const chanShort = typeof content.channel === 'string' ? content.channel.slice(0, 8) : '?';
        const size = content.blob_size != null ? `${content.blob_size}B` : '?';
        return `${type}(${chanShort}\u2026, ${size})`;
    }

    if (type === 'ChannelSetKeys' && content) {
        const chanShort = typeof content.channel === 'string' ? content.channel.slice(0, 8) : '?';
        const nKeys = Array.isArray(content.keys) ? content.keys.length : '?';
        return `${type}(${chanShort}\u2026, ${nKeys} keys)`;
    }

    return type;
}

function formatOperationsPreview(ops) {
    if (!ops?.length) return '—';
    const previews = ops.map(opPreview);
    if (previews.length <= OPERATIONS_PREVIEW_LIMIT) return previews.join(', ');
    const head = previews.slice(0, OPERATIONS_PREVIEW_LIMIT).join(', ');
    const remainder = previews.length - OPERATIONS_PREVIEW_LIMIT;
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
    tdId.appendChild(createLink(PAGE.TRANSACTION_DETAIL(tx.hash), shortenHex(tx.hash), tx.hash));

    // Operations (preview)
    const tdOps = document.createElement('td');
    tdOps.style.whiteSpace = 'normal';
    tdOps.style.lineHeight = '1.4';
    const preview = formatOperationsPreview(tx.operations);
    const fullPreview = Array.isArray(tx.operations) ? tx.operations.map(opPreview).join(', ') : '';
    tdOps.appendChild(createSpan('', preview, fullPreview));

    // Outputs (count / total)
    const tdOut = document.createElement('td');
    tdOut.className = 'amount';
    tdOut.textContent = `${tx.numberOfOutputs} / ${tx.totalOutputValue.toLocaleString(undefined, { maximumFractionDigits: 8 })}`;

    tr.append(tdId, tdOps, tdOut);
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

        // 3 columns: Hash | Operations | Outputs
        ensureFixedRowCount(body, 3, TABLE_SIZE);

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
                    ),
                ),
                h('tbody', { ref: bodyRef }),
            ),
        ),
    );
}
