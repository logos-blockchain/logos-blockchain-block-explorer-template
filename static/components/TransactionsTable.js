// static/components/TransactionsTable.js
import { h } from 'preact';
import { useEffect, useState, useCallback, useRef } from 'preact/hooks';
import { API, PAGE } from '../lib/api.js';
import { TABLE_SIZE } from '../lib/constants.js';
import { shortenHex, streamNdjson } from '../lib/utils.js';
import { opLabel, transferOutputs, tryDecodeUtf8Hex } from '../lib/format.js';

const OPERATIONS_PREVIEW_LIMIT = 2;

function opPreview(op) {
    const content = op?.content;
    const type = opLabel(op);
    if (type === 'ChannelInscribe' && content) {
        const chanShort = typeof content.channel_id === 'string' ? content.channel_id.slice(0, 8) : '?';
        let inscPreview = '';
        if (typeof content.inscription === 'string') {
            const decoded = tryDecodeUtf8Hex(content.inscription);
            inscPreview =
                decoded != null
                    ? decoded.length > 20
                        ? decoded.slice(0, 20) + '\u2026'
                        : decoded
                    : content.inscription.slice(0, 12) + '\u2026';
        }
        return `${type}(${chanShort}\u2026, ${inscPreview})`;
    }
    return type;
}

function formatOperationsPreview(ops) {
    if (!ops?.length) return '\u2014';
    const previews = ops.map(opPreview);
    if (previews.length <= OPERATIONS_PREVIEW_LIMIT) return previews.join(', ');
    const head = previews.slice(0, OPERATIONS_PREVIEW_LIMIT).join(', ');
    return `${head} +${previews.length - OPERATIONS_PREVIEW_LIMIT}`;
}

function normalize(raw) {
    const ops = Array.isArray(raw?.operations) ? raw.operations : [];
    const { count, total } = transferOutputs(ops);
    return {
        id: raw?.id ?? '',
        hash: raw?.hash ?? '',
        operations: ops,
        numberOfOutputs: count,
        totalOutputValue: total,
    };
}

// ---------- component ----------
export default function TransactionsTable({ live, onDisableLive }) {
    const [transactions, setTransactions] = useState([]);
    const [page, setPage] = useState(0);
    const [totalPages, setTotalPages] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const abortRef = useRef(null);
    const seenKeysRef = useRef(new Set());

    // Fetch paginated transactions
    const fetchTransactions = useCallback(async (pageNum) => {
        abortRef.current?.abort();
        seenKeysRef.current.clear();

        setLoading(true);
        setError(null);
        try {
            const res = await fetch(API.TRANSACTIONS_LIST(pageNum, TABLE_SIZE));
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setTransactions(data.transactions.map(normalize));
            setTotalPages(data.total_pages);
            setTotalCount(data.total_count);
            setPage(data.page);
        } catch (e) {
            setError(e.message);
        } finally {
            setLoading(false);
        }
    }, []);

    // Start live streaming
    const startLiveStream = useCallback(() => {
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        seenKeysRef.current.clear();
        setTransactions([]);
        setLoading(true);
        setError(null);

        let liveTxs = [];

        streamNdjson(
            API.TRANSACTIONS_STREAM(TABLE_SIZE),
            (raw) => {
                const tx = normalize(raw);
                if (seenKeysRef.current.has(tx.hash)) return;
                seenKeysRef.current.add(tx.hash);

                liveTxs = [tx, ...liveTxs].slice(0, TABLE_SIZE);
                setTransactions([...liveTxs]);
                setLoading(false);
            },
            {
                signal: abortRef.current.signal,
                onError: (e) => {
                    if (e?.name !== 'AbortError') {
                        console.error('Transactions stream error:', e);
                        setError(e?.message || 'Stream error');
                    }
                },
            },
        );
    }, []);

    useEffect(() => {
        if (live) {
            startLiveStream();
        } else {
            setPage(0);
            fetchTransactions(0);
        }
        return () => abortRef.current?.abort();
    }, [live, startLiveStream, fetchTransactions]);

    // Go to a page (or exit live mode into page 0)
    const goToPage = (newPage) => {
        if (live) {
            onDisableLive?.();
            return; // useEffect will handle fetching page 0 when live changes
        }
        if (newPage >= 0) {
            fetchTransactions(newPage);
        }
    };

    const renderRow = (tx, idx) => {
        const opsPreview = formatOperationsPreview(tx.operations);
        const fullPreview = Array.isArray(tx.operations) ? tx.operations.map(opPreview).join(', ') : '';
        const outputsText = `${tx.numberOfOutputs} / ${tx.totalOutputValue.toLocaleString(undefined, { maximumFractionDigits: 8 })}`;

        return h(
            'tr',
            { key: tx.id || idx },
            // Hash
            h(
                'td',
                null,
                h(
                    'a',
                    {
                        class: 'linkish mono',
                        href: PAGE.TRANSACTION_DETAIL(tx.hash),
                        title: tx.hash,
                    },
                    shortenHex(tx.hash),
                ),
            ),
            // Operations
            h('td', { style: 'white-space:normal; line-height:1.4;' }, h('span', { title: fullPreview }, opsPreview)),
            // Outputs
            h('td', { class: 'amount' }, outputsText),
        );
    };

    const renderPlaceholderRow = (idx) => {
        return h(
            'tr',
            { key: `ph-${idx}`, class: 'ph' },
            h('td', null, '\u00A0'),
            h('td', null, '\u00A0'),
            h('td', null, '\u00A0'),
        );
    };

    const rows = [];
    for (let i = 0; i < TABLE_SIZE; i++) {
        if (i < transactions.length) {
            rows.push(renderRow(transactions[i], i));
        } else {
            rows.push(renderPlaceholderRow(i));
        }
    }

    return h(
        'div',
        { class: 'card' },
        h(
            'div',
            { class: 'card-header', style: 'display:flex; justify-content:space-between; align-items:center;' },
            h(
                'div',
                null,
                h('strong', null, 'Transactions '),
                !live && totalCount > 0 && h('span', { class: 'pill' }, String(totalCount)),
            ),
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
                h('tbody', null, ...rows),
            ),
        ),
        // Pagination controls
        h(
            'div',
            {
                class: 'card-footer',
                style: 'display:flex; justify-content:space-between; align-items:center; padding:8px 14px; border-top:1px solid var(--border);',
            },
            h(
                'button',
                {
                    class: 'pill',
                    disabled: !live && (page === 0 || loading),
                    onClick: () => goToPage(page - 1),
                },
                'Previous',
            ),
            h(
                'span',
                { style: 'color:var(--muted); font-size:13px;' },
                live
                    ? 'Streaming live transactions...'
                    : totalPages > 0
                      ? `Page ${page + 1} of ${totalPages}`
                      : 'No transactions',
            ),
            h(
                'button',
                {
                    class: 'pill',
                    disabled: !live && (page >= totalPages - 1 || loading),
                    onClick: () => goToPage(page + 1),
                },
                'Next',
            ),
        ),
        // Error display
        error && h('div', { style: 'padding:8px 14px; color:var(--danger);' }, `Error: ${error}`),
    );
}
