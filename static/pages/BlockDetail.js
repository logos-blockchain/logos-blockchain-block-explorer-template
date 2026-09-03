// static/pages/BlockDetailPage.js
import { h, Fragment } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import { API, PAGE, BASE_PATH } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';
import { transferOutputs } from '../lib/format.js';
import { CopyPill, OpPills } from '../components/Common.js';

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

    const transactions = Array.isArray(block?.transactions) ? block.transactions : [];
    const height = block?.height ?? null;
    const slot = block?.slot ?? null;
    const blockRoot = block?.block_root ?? '';
    const currentBlockHash = block?.hash ?? '';
    const parentHash = block?.parent_block_hash ?? '';

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
        errorKind === 'invalid-hash' && h('p', { style: 'color:var(--danger)' }, errorMessage),
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
        errorKind === 'network' && h('p', { style: 'color:var(--danger)' }, `Error: ${errorMessage}`),

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
                    ),
                ),

                // Transactions card
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
                                        { style: 'text-align:left; padding:8px 10px; white-space:nowrap;' },
                                        'Operations',
                                    ),
                                ),
                            ),
                            h(
                                'tbody',
                                null,
                                ...transactions.map((t) => {
                                    const { count, total } = transferOutputs(t?.operations);
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
                                        // Operations (left; no wrap)
                                        h(
                                            'td',
                                            { style: 'text-align:left; padding:8px 10px; white-space:nowrap;' },
                                            h(OpPills, { ops }),
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
