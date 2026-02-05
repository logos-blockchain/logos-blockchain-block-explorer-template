// static/pages/TransactionDetail.js
import { h, Fragment } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import { API, PAGE } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';

// ————— helpers —————
const isNumber = (v) => typeof v === 'number' && !Number.isNaN(v);
const toLocaleNum = (n, opts = {}) => Number(n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 8, ...opts });

// Best-effort pretty bytes/hex/string
function renderBytes(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value; // hex/base64/plain
    if (Array.isArray(value) && value.every((x) => Number.isInteger(x) && x >= 0 && x <= 255)) {
        return '0x' + value.map((b) => b.toString(16).padStart(2, '0')).join('');
    }
    try {
        return JSON.stringify(value);
    } catch {
        return String(value);
    }
}

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

function opsToPills(ops, limit = 6) {
    const arr = Array.isArray(ops) ? ops : [];
    if (!arr.length) return h('span', { style: 'color:var(--muted); whiteSpace: "nowrap";' }, '—');
    const labels = arr.map(opLabel);
    const shown = labels.slice(0, limit);
    const extra = labels.length - shown.length;
    return h(
        'div',
        { style: 'display:flex; gap:6px; flexWrap:"wrap"; alignItems:"center"' },
        ...shown.map((label, i) =>
            h('span', { key: `${label}-${i}`, class: 'pill', title: label, style: 'flex:0 0 auto;' }, label),
        ),
        extra > 0 && h('span', { class: 'pill', title: `${extra} more`, style: 'flex:0 0 auto;' }, `+${extra}`),
    );
}

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

function CopyPill({ text, label = 'Copy' }) {
    const onCopy = async (e) => {
        e.preventDefault();
        try {
            await navigator.clipboard.writeText(String(text ?? ''));
        } catch {}
    };
    return h(
        'a',
        {
            class: 'pill linkish mono',
            style: 'cursor:pointer; user-select:none;',
            href: '#',
            onClick: onCopy,
            onKeyDown: (e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    onCopy(e);
                }
            },
            tabIndex: 0,
            role: 'button',
        },
        label,
    );
}

// ————— normalizer for new TransactionRead —————
// { id, block_id, hash, operations:[Operation], inputs:[HexBytes], outputs:[Note{public_key:HexBytes,value:int}],
//   proof, execution_gas_price, storage_gas_price }
function normalizeTransaction(raw) {
    const ops = Array.isArray(raw?.operations) ? raw.operations : Array.isArray(raw?.ops) ? raw.ops : [];

    const inputs = Array.isArray(raw?.inputs) ? raw.inputs : [];
    const outputs = Array.isArray(raw?.outputs) ? raw.outputs : [];

    const totalOutputValue = outputs.reduce((sum, note) => sum + toNumber(note?.value), 0);

    return {
        id: raw?.id ?? '',
        blockHash: raw?.block_hash ?? null,
        hash: renderBytes(raw?.hash),
        proof: renderBytes(raw?.proof),
        operations: ops, // keep objects, we’ll label in UI
        executionGasPrice: isNumber(raw?.execution_gas_price)
            ? raw.execution_gas_price
            : toNumber(raw?.execution_gas_price),
        storageGasPrice: isNumber(raw?.storage_gas_price) ? raw.storage_gas_price : toNumber(raw?.storage_gas_price),
        ledger: {
            inputs: inputs.map((v) => renderBytes(v)),
            outputs: outputs.map((n) => ({
                public_key: renderBytes(n?.public_key),
                value: toNumber(n?.value),
            })),
            totalOutputValue,
        },
    };
}

// ————— UI bits —————
function SectionCard({ title, children, style }) {
    return h(
        'div',
        { class: 'card', style: `margin-top:12px; ${style ?? ''}` },
        h('div', { class: 'card-header' }, h('strong', null, title)),
        h('div', { style: 'padding:12px 14px' }, children),
    );
}

function Summary({ tx }) {
    return h(
        SectionCard,
        { title: 'Summary' },
        h(
            'div',
            { style: 'display:grid; gap:8px;' },

            // Block link
            tx.blockHash != null &&
                h(
                    'div',
                    null,
                    h('b', null, 'Block: '),
                    h(
                        'a',
                        { class: 'linkish mono', href: PAGE.BLOCK_DETAIL(tx.blockHash), title: String(tx.blockHash) },
                        shortenHex(tx.blockHash),
                    ),
                ),

            // Hash + copy
            h(
                'div',
                null,
                h('b', null, 'Hash: '),
                h(
                    'span',
                    { class: 'pill mono', title: tx.hash, style: 'max-width:100%; overflow-wrap:anywhere;' },
                    String(tx.hash || ''),
                ),
                h(CopyPill, { text: tx.hash }),
            ),

            // Proof + copy (if present)
            tx.proof &&
                h(
                    'div',
                    null,
                    h('b', null, 'Proof: '),
                    h(
                        'span',
                        { class: 'pill mono', title: tx.proof, style: 'max-width:100%; overflow-wrap:anywhere;' },
                        String(tx.proof),
                    ),
                    h(CopyPill, { text: tx.proof }),
                ),

            // Gas
            h(
                'div',
                null,
                h('b', null, 'Execution Gas: '),
                h('span', { class: 'mono' }, toLocaleNum(tx.executionGasPrice)),
            ),
            h(
                'div',
                null,
                h('b', null, 'Storage Gas: '),
                h('span', { class: 'mono' }, toLocaleNum(tx.storageGasPrice)),
            ),

            // Operations (labels as pills)
            h('div', null, h('b', null, 'Operations: '), opsToPills(tx.operations)),
        ),
    );
}

function InputsTable({ inputs }) {
    if (!inputs?.length) return h('div', { style: 'color:var(--muted)' }, '—');

    return h(
        'div',
        { class: 'table-wrapper', style: 'margin-top:6px;' },
        h(
            'table',
            { class: 'table--transactions' },
            h(
                'colgroup',
                null,
                h('col', { style: 'width:80px' }), // #
                h('col', null), // Value
            ),
            h('thead', null, h('tr', null, h('th', { style: 'text-align:center;' }, '#'), h('th', null, 'Note ID'))),
            h(
                'tbody',
                null,
                ...inputs.map((fr, i) =>
                    h(
                        'tr',
                        { key: i },
                        h('td', { style: 'text-align:center;' }, String(i)),
                        h(
                            'td',
                            null,
                            h(
                                'span',
                                { class: 'mono', style: 'overflow-wrap:anywhere; word-break:break-word;' },
                                String(fr),
                            ),
                        ),
                    ),
                ),
            ),
        ),
    );
}

function OutputsTable({ outputs }) {
    if (!outputs?.length) return h('div', { style: 'color:var(--muted)' }, '—');

    return h(
        'div',
        { class: 'table-wrapper', style: 'margin-top:6px;' },
        h(
            'table',
            { class: 'table--transactions' },
            h(
                'colgroup',
                null,
                h('col', { style: 'width:80px' }), // #
                h('col', null), // Public Key
                h('col', { style: 'width:180px' }), // Value
            ),
            h(
                'thead',
                null,
                h(
                    'tr',
                    null,
                    h('th', { style: 'text-align:center;' }, '#'),
                    h('th', null, 'Public Key'),
                    h('th', { style: 'text-align:right;' }, 'Value'),
                ),
            ),
            h(
                'tbody',
                null,
                ...outputs.map((note, idx) =>
                    h(
                        'tr',
                        { key: idx },
                        h('td', { style: 'text-align:center;' }, String(idx)),
                        h(
                            'td',
                            null,
                            h(
                                'span',
                                { class: 'mono', style: 'display:inline-block; overflow-wrap:anywhere;' },
                                String(note.public_key ?? ''),
                            ),
                            h('span', { class: 'sr-only' }, ' '),
                        ),
                        h('td', { class: 'amount', style: 'text-align:right;' }, toLocaleNum(note.value)),
                    ),
                ),
            ),
        ),
    );
}

function Ledger({ ledger }) {
    const inputs = Array.isArray(ledger?.inputs) ? ledger.inputs : [];
    const outputs = Array.isArray(ledger?.outputs) ? ledger.outputs : [];
    const totalOutputValue = toNumber(ledger?.totalOutputValue);

    return h(
        SectionCard,
        { title: 'Ledger' },
        h(
            'div',
            { style: 'display:grid; gap:16px;' },

            // Inputs
            h(
                'div',
                null,
                h(
                    'div',
                    { style: 'display:flex; alignItems:center; gap:8px;' },
                    h('b', null, 'Inputs'),
                    h('span', { class: 'pill' }, String(inputs.length)),
                ),
                h(InputsTable, { inputs }),
            ),

            // Outputs
            h(
                'div',
                null,
                h(
                    'div',
                    { style: 'display:flex; alignItems:center; gap:8px;' },
                    h('b', null, 'Outputs'),
                    h('span', { class: 'pill' }, String(outputs.length)),
                    h(
                        'span',
                        { class: 'amount', style: 'margin-left:auto;' },
                        `Total: ${toLocaleNum(totalOutputValue)}`,
                    ),
                ),
                h(OutputsTable, { outputs }),
            ),
        ),
    );
}

// ————— page —————
export default function TransactionDetail({ parameters }) {
    const transactionHash = parameters?.[0];
    const isValidHash = typeof transactionHash === 'string' && transactionHash.length > 0;

    const [tx, setTx] = useState(null);
    const [err, setErr] = useState(null); // { kind: 'invalid'|'not-found'|'network', msg: string }

    const pageTitle = useMemo(() => `Transaction ${shortenHex(transactionHash)}`, [transactionHash]);
    useEffect(() => {
        document.title = pageTitle;
    }, [pageTitle]);

    useEffect(() => {
        setTx(null);
        setErr(null);

        if (!isValidHash) {
            setErr({ kind: 'invalid', msg: 'Invalid transaction hash.' });
            return;
        }

        let alive = true;
        const controller = new AbortController();

        (async () => {
            try {
                const res = await fetch(API.TRANSACTION_DETAIL_BY_HASH(transactionHash), {
                    cache: 'no-cache',
                    signal: controller.signal,
                });
                if (res.status === 404 || res.status === 410) {
                    if (alive) setErr({ kind: 'not-found', msg: 'Transaction not found.' });
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const payload = await res.json();
                if (!alive) return;
                setTx(normalizeTransaction(payload));
            } catch (e) {
                if (!alive || e?.name === 'AbortError') return;
                setErr({ kind: 'network', msg: e?.message ?? 'Failed to load transaction' });
            }
        })();

        return () => {
            alive = false;
            controller.abort();
        };
    }, [transactionHash, isValidHash]);

    return h(
        'main',
        { class: 'wrap' },

        h(
            'header',
            { style: 'display:flex; gap:12px; alignItems:center; margin:12px 0;' },
            h('a', { class: 'linkish', href: '/' }, '← Back'),
            h('h1', { style: 'margin:0' }, pageTitle),
        ),

        // Errors
        err?.kind === 'invalid' && h('p', { style: 'color:#ff8a8a' }, err.msg),
        err?.kind === 'not-found' &&
            h(
                SectionCard,
                { title: 'Transaction not found' },
                h('p', null, 'We could not find a transaction with that identifier.'),
            ),
        err?.kind === 'network' && h('p', { style: 'color:#ff8a8a' }, `Error: ${err.msg}`),

        // Loading
        !tx && !err && h('p', null, 'Loading…'),

        // Success
        tx && h(Fragment, null, h(Summary, { tx }), h(Ledger, { ledger: tx.ledger })),
    );
}
