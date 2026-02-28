// static/pages/BlockDetailPage.js
import { h, Fragment } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import { API, PAGE, BASE_PATH } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';

const OPERATIONS_PREVIEW_LIMIT = 2;

// ---- Helpers ----
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

function opsToPills(ops, limit = OPERATIONS_PREVIEW_LIMIT) {
    const arr = Array.isArray(ops) ? ops : [];
    if (!arr.length) return h('span', { style: 'color:var(--muted); white-space:nowrap;' }, '—');

    const labels = arr.map(opLabel);
    const shown = labels.slice(0, limit);
    const extra = labels.length - shown.length;

    return h(
        'div',
        { style: 'display:flex; gap:6px; flex-wrap:nowrap; align-items:center; white-space:nowrap;' },
        ...shown.map((label, i) =>
            h('span', { key: `${label}-${i}`, class: 'pill', title: label, style: 'flex:0 0 auto;' }, label),
        ),
        extra > 0 && h('span', { class: 'pill', title: `${extra} more`, style: 'flex:0 0 auto;' }, `+${extra}`),
    );
}

function computeOutputsSummaryFromTx(tx) {
    const outputs = Array.isArray(tx?.outputs) ? tx.outputs : [];
    const count = outputs.length;
    const total = outputs.reduce((sum, o) => sum + Number(o?.value ?? 0), 0);
    return { count, total };
}

function CopyPill({ text }) {
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
        'Copy',
    );
}

export default function BlockDetailPage({ parameters }) {
    const blockHash = parameters[0];
    const isValidHash = typeof blockHash === 'string' && blockHash.length > 0;

    const [block, setBlock] = useState(null);
    const [errorMessage, setErrorMessage] = useState('');
    const [errorKind, setErrorKind] = useState(null); // 'invalid-hash' | 'not-found' | 'network' | null

    const pageTitle = useMemo(() => `Block ${shortenHex(blockHash)}`, [blockHash]);
    useEffect(() => {
        document.title = pageTitle;
    }, [pageTitle]);

    useEffect(() => {
        setBlock(null);
        setErrorMessage('');
        setErrorKind(null);

        if (!isValidHash) {
            setErrorKind('invalid-hash');
            setErrorMessage('Invalid block hash.');
            return;
        }

        let alive = true;
        const controller = new AbortController();

        (async () => {
            try {
                const res = await fetch(API.BLOCK_DETAIL_BY_HASH(blockHash), {
                    cache: 'no-cache',
                    signal: controller.signal,
                });
                if (res.status === 404 || res.status === 410) {
                    if (alive) {
                        setErrorKind('not-found');
                        setErrorMessage('Block not found.');
                    }
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const payload = await res.json();
                if (alive) setBlock(payload);
            } catch (e) {
                if (!alive || e?.name === 'AbortError') return;
                setErrorKind('network');
                setErrorMessage(e?.message ?? 'Failed to load block');
            }
        })();

        return () => {
            alive = false;
            controller.abort();
        };
    }, [blockHash, isValidHash]);

    const header = block?.header ?? {}; // back-compat only
    const transactions = Array.isArray(block?.transactions) ? block.transactions : [];

    // Prefer new top-level fields; fallback to legacy header.*
    const height = block?.height ?? null;
    const slot = block?.slot ?? header?.slot ?? null;
    const blockRoot = block?.block_root ?? header?.block_root ?? '';
    const currentBlockHash = block?.hash ?? header?.hash ?? '';
    const parentHash = block?.parent_block_hash ?? header?.parent_block ?? '';
    const lib = block?.lib ?? '';
    const tip = block?.tip ?? '';

    return h(
        'main',
        { class: 'wrap' },

        // Top bar
        h(
            'header',
            { style: 'display:flex; gap:12px; align-items:center; margin:12px 0;' },
            h('a', { class: 'linkish', href: `${BASE_PATH}/` }, '← Back'),
            h('h1', { style: 'margin:0' }, pageTitle),
        ),

        // Error states
        errorKind === 'invalid-hash' && h('p', { style: 'color:#ff8a8a' }, errorMessage),
        errorKind === 'not-found' &&
            h(
                'div',
                { class: 'card', style: 'margin-top:12px;' },
                h('div', { class: 'card-header' }, h('strong', null, 'Block not found')),
                h(
                    'div',
                    { style: 'padding:12px 14px' },
                    h('p', null, 'We could not find a block with that identifier.'),
                ),
            ),
        errorKind === 'network' && h('p', { style: 'color:#ff8a8a' }, `Error: ${errorMessage}`),

        // Loading
        !block && !errorKind && h('p', null, 'Loading…'),

        // Success
        block &&
            h(
                Fragment,
                null,

                // Header card
                h(
                    'div',
                    { class: 'card', style: 'margin-top:12px;' },
                    h(
                        'div',
                        { class: 'card-header', style: 'display:flex; align-items:center; gap:8px;' },
                        h('strong', null, 'Header'),
                        h(
                            'div',
                            { style: 'margin-left:auto; display:flex; gap:8px; flex-wrap:wrap;' },
                            height != null && h('span', { class: 'pill', title: 'Height' }, `Height ${String(height)}`),
                            slot != null && h('span', { class: 'pill', title: 'Slot' }, `Slot ${String(slot)}`),
                        ),
                    ),
                    h(
                        'div',
                        { style: 'padding:12px 14px; display:grid; grid-template-columns: 120px 1fr; gap:8px 12px;' },

                        // Hash (pill + copy)
                        h('div', null, h('b', null, 'Hash:')),
                        h(
                            'div',
                            { style: 'display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;' },
                            h(
                                'span',
                                {
                                    class: 'pill mono',
                                    title: currentBlockHash,
                                    style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                },
                                String(currentBlockHash),
                            ),
                            h(CopyPill, { text: currentBlockHash }),
                        ),

                        // Root (pill + copy)
                        h('div', null, h('b', null, 'Root:')),
                        h(
                            'div',
                            { style: 'display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;' },
                            h(
                                'span',
                                {
                                    class: 'pill mono',
                                    title: blockRoot,
                                    style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                },
                                String(blockRoot),
                            ),
                            h(CopyPill, { text: blockRoot }),
                        ),

                        // Parent (parent hash link) + copy
                        h('div', null, h('b', null, 'Parent:')),
                        h(
                            'div',
                            { style: 'display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;' },
                            parentHash
                                ? h(
                                      'a',
                                      {
                                          class: 'pill mono linkish',
                                          href: PAGE.BLOCK_DETAIL(parentHash),
                                          title: String(parentHash),
                                          style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                      },
                                      shortenHex(parentHash),
                                  )
                                : h(
                                      'span',
                                      {
                                          class: 'pill mono',
                                          title: '—',
                                          style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                      },
                                      '—',
                                  ),
                            h(CopyPill, { text: parentHash }),
                        ),

                        // LIB
                        h('div', null, h('b', null, 'LIB:')),
                        h(
                            'div',
                            { style: 'display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;' },
                            lib
                                ? h(
                                      'a',
                                      {
                                          class: 'pill mono linkish',
                                          href: PAGE.BLOCK_DETAIL(lib),
                                          title: String(lib),
                                          style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                      },
                                      shortenHex(lib),
                                  )
                                : h(
                                      'span',
                                      {
                                          class: 'pill mono',
                                          style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                      },
                                      '—',
                                  ),
                            lib && h(CopyPill, { text: lib }),
                        ),

                        // Tip
                        h('div', null, h('b', null, 'Tip:')),
                        h(
                            'div',
                            { style: 'display:flex; gap:8px; flex-wrap:wrap; align-items:flex-start;' },
                            tip
                                ? h(
                                      'a',
                                      {
                                          class: 'pill mono linkish',
                                          href: PAGE.BLOCK_DETAIL(tip),
                                          title: String(tip),
                                          style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                      },
                                      shortenHex(tip),
                                  )
                                : h(
                                      'span',
                                      {
                                          class: 'pill mono',
                                          style: 'max-width:100%; overflow-wrap:anywhere; word-break:break-word;',
                                      },
                                      '—',
                                  ),
                            tip && h(CopyPill, { text: tip }),
                        ),
                    ),
                ),

                // Transactions card — rows fill width; Outputs & Gas centered
                h(
                    'div',
                    { class: 'card', style: 'margin-top:16px;' },
                    h(
                        'div',
                        { class: 'card-header' },
                        h('strong', null, 'Transactions '),
                        h('span', { class: 'pill' }, String(transactions.length)),
                    ),
                    h(
                        'div',
                        { class: 'table-wrapper', style: 'max-width:100%; overflow:auto;' },
                        h(
                            'table',
                            {
                                class: 'table--transactions',
                                style: 'min-width:100%; width:max-content; table-layout:auto; border-collapse:collapse;',
                            },
                            h(
                                'thead',
                                null,
                                h(
                                    'tr',
                                    null,
                                    h(
                                        'th',
                                        { style: 'text-align:left; padding:8px 10px; white-space:nowrap;' },
                                        'Hash',
                                    ),
                                    h(
                                        'th',
                                        { style: 'text-align:center; padding:8px 10px; white-space:nowrap;' },
                                        'Outputs (count / total)',
                                    ),
                                    h(
                                        'th',
                                        { style: 'text-align:center; padding:8px 10px; white-space:nowrap;' },
                                        'Gas (execution / storage)',
                                    ),
                                    h(
                                        'th',
                                        { style: 'text-align:left; padding:8px 10px; white-space:nowrap;' },
                                        'Operations',
                                    ),
                                ),
                            ),
                            h(
                                'tbody',
                                null,
                                ...transactions.map((t) => {
                                    const { count, total } = computeOutputsSummaryFromTx(t);
                                    const executionGas = Number(t?.execution_gas_price ?? 0);
                                    const storageGas = Number(t?.storage_gas_price ?? 0);
                                    const ops = Array.isArray(t?.operations) ? t.operations : [];

                                    return h(
                                        'tr',
                                        { key: t?.hash ?? `${count}/${total}` },
                                        // Hash (left)
                                        h(
                                            'td',
                                            { style: 'text-align:left; padding:8px 10px; white-space:nowrap;' },
                                            h(
                                                'a',
                                                {
                                                    class: 'linkish mono',
                                                    href: PAGE.TRANSACTION_DETAIL(t?.hash ?? ''),
                                                    title: String(t?.hash ?? ''),
                                                },
                                                shortenHex(t?.hash ?? ''),
                                            ),
                                        ),
                                        // Outputs (center)
                                        h(
                                            'td',
                                            {
                                                class: 'amount',
                                                style: 'text-align:center; padding:8px 10px; white-space:nowrap;',
                                            },
                                            `${count} / ${Number(total).toLocaleString(undefined, { maximumFractionDigits: 8 })}`,
                                        ),
                                        // Gas (center)
                                        h(
                                            'td',
                                            {
                                                class: 'mono',
                                                style: 'text-align:center; padding:8px 10px; white-space:nowrap;',
                                            },
                                            `${executionGas.toLocaleString()} / ${storageGas.toLocaleString()}`,
                                        ),
                                        // Operations (left; no wrap)
                                        h(
                                            'td',
                                            { style: 'text-align:left; padding:8px 10px; white-space:nowrap;' },
                                            opsToPills(ops),
                                        ),
                                    );
                                }),
                            ),
                        ),
                    ),
                ),
            ),
    );
}
