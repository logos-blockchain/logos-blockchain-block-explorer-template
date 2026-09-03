// static/pages/TransactionDetail.js
import { h, Fragment } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import { API, PAGE, BASE_PATH } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';
import { fieldLabel, opLabel, renderBytes, toLocaleNum, toNumber, tryDecodeUtf8Hex } from '../lib/format.js';
import { CopyPill, FieldValue, OpPills } from '../components/Common.js';

// ————— normalizer for TransactionRead —————
// { id, block_hash, hash, operations:[Operation], execution_gas_price, storage_gas_price }
// Ledger transfers are now an Operation with content.type === 'LedgerTransfer'.
function normalizeTransaction(raw) {
    const ops = Array.isArray(raw?.operations) ? raw.operations : Array.isArray(raw?.ops) ? raw.ops : [];

    return {
        id: raw?.id ?? '',
        blockHash: raw?.block_hash ?? null,
        hash: renderBytes(raw?.hash),
        operations: ops,
        executionGasPrice: toNumber(raw?.execution_gas_price),
        storageGasPrice: toNumber(raw?.storage_gas_price),
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
            h('div', null, h('b', null, 'Operations: '), h(OpPills, { ops: tx.operations, limit: 6, wrap: true })),
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
                            /^[0-9a-f]{64}$/i.test(String(fr))
                                ? h(
                                      'a',
                                      {
                                          class: 'linkish mono',
                                          style: 'overflow-wrap:anywhere; word-break:break-word;',
                                          href: PAGE.NOTE_DETAIL(String(fr)),
                                          title: 'Find transactions referencing this note',
                                      },
                                      String(fr),
                                  )
                                : h(
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

// ————— operations detail —————

function InscriptionValue({ value }) {
    const decoded = tryDecodeUtf8Hex(value);
    if (decoded != null) {
        return h(
            'span',
            { style: 'display:flex; align-items:center; gap:6px;' },
            h('span', { style: 'overflow-wrap:anywhere; word-break:break-word;' }, decoded),
            h(CopyPill, { text: decoded }),
        );
    }
    return h(FieldValue, { value });
}

function LedgerTransferContent({ content }) {
    const inputs = Array.isArray(content?.inputs) ? content.inputs.map((v) => renderBytes(v)) : [];
    const rawOutputs = Array.isArray(content?.outputs) ? content.outputs : [];
    const outputs = rawOutputs.map((n) => ({
        public_key: renderBytes(n?.public_key),
        value: toNumber(n?.value),
    }));
    const totalOutputValue = outputs.reduce((sum, o) => sum + o.value, 0);

    return h(
        'div',
        { style: 'display:grid; gap:16px;' },

        // Inputs
        h(
            'div',
            null,
            h(
                'div',
                { style: 'display:flex; align-items:center; gap:8px;' },
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
                { style: 'display:flex; align-items:center; gap:8px;' },
                h('b', null, 'Outputs'),
                h('span', { class: 'pill' }, String(outputs.length)),
                h('span', { class: 'amount', style: 'margin-left:auto;' }, `Total: ${toLocaleNum(totalOutputValue)}`),
            ),
            h(OutputsTable, { outputs }),
        ),
    );
}

function OperationContent({ content }) {
    if (content?.type === 'LedgerTransfer') return h(LedgerTransferContent, { content });

    // Get all fields except "type"
    const entries = Object.entries(content).filter(([k]) => k !== 'type');
    if (!entries.length) return h('div', { style: 'color:var(--muted)' }, 'No fields');

    return h(
        'div',
        { style: 'display:grid; grid-template-columns:auto 1fr; gap:6px 12px; align-items:baseline;' },
        ...entries.flatMap(([key, value]) => [
            h('span', { style: 'color:var(--muted); font-size:13px; white-space:nowrap;' }, fieldLabel(key)),
            key === 'inscription' ? h(InscriptionValue, { value }) : h(FieldValue, { value }),
        ]),
    );
}

function OperationProof({ proof }) {
    if (!proof) return null;
    const proofType = proof.type ?? 'Unknown';
    const entries = Object.entries(proof).filter(([k]) => k !== 'type');

    return h(
        'div',
        { style: 'margin-top:8px; padding-top:8px; border-top:1px solid var(--border);' },
        h('span', { style: 'color:var(--muted); font-size:12px;' }, `Proof: ${proofType}`),
        entries.length > 0 &&
            h(
                'div',
                {
                    style: 'margin-top:4px; display:grid; grid-template-columns:auto 1fr; gap:4px 12px; align-items:baseline;',
                },
                ...entries.flatMap(([key, value]) => [
                    h('span', { style: 'color:var(--muted); font-size:12px; white-space:nowrap;' }, fieldLabel(key)),
                    h(
                        'span',
                        { class: 'mono', style: 'font-size:12px; overflow-wrap:anywhere; word-break:break-all;' },
                        renderBytes(value),
                    ),
                ]),
            ),
    );
}

function OperationCard({ op, index }) {
    const content = op?.content ?? op;
    const proof = op?.proof ?? null;
    const type = opLabel(op);

    return h(
        'div',
        { style: 'background:var(--panel); border:1px solid var(--border); padding:12px 14px;' },
        h(
            'div',
            { style: 'display:flex; align-items:center; gap:8px; margin-bottom:10px;' },
            h('span', { class: 'pill', style: 'font-size:11px;' }, `#${index}`),
            h(
                'span',
                {
                    class: 'pill',
                    style: 'background:var(--accent-bg); color:var(--accent); border-color:var(--accent);',
                },
                type,
            ),
        ),
        h(OperationContent, { content }),
        h(OperationProof, { proof }),
    );
}

function Operations({ operations }) {
    const ops = Array.isArray(operations) ? operations : [];
    if (!ops.length) return null;

    return h(
        SectionCard,
        { title: `Operations (${ops.length})` },
        h(
            'div',
            { style: 'display:flex; flex-direction:column; gap:12px;' },
            ...ops.map((op, i) => h(OperationCard, { key: i, op, index: i })),
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
            h('a', { class: 'linkish', href: `${BASE_PATH}/` }, '← Back'),
            h('h1', { style: 'margin:0' }, pageTitle),
        ),

        // Errors
        err?.kind === 'invalid' && h('p', { style: 'color:var(--danger)' }, err.msg),
        err?.kind === 'not-found' &&
            h(
                SectionCard,
                { title: 'Transaction not found' },
                h('p', null, 'We could not find a transaction with that identifier.'),
            ),
        err?.kind === 'network' && h('p', { style: 'color:var(--danger)' }, `Error: ${err.msg}`),

        // Loading
        !tx && !err && h('p', null, 'Loading…'),

        // Success
        tx && h(Fragment, null, h(Summary, { tx }), h(Operations, { operations: tx.operations })),
    );
}
