// static/components/TransactionsTable.js
import { h } from 'preact';
import { useEffect, useState, useCallback, useRef } from 'preact/hooks';
import { API, PAGE } from '../lib/api.js';
import { TABLE_SIZE } from '../lib/constants.js';
import { shortenHex, streamNdjson } from '../lib/utils.js';
import { subscribeFork } from '../lib/fork.js';

const OPERATIONS_PREVIEW_LIMIT = 2;

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
    if (!ops?.length) return '\u2014';
    const previews = ops.map(opPreview);
    if (previews.length <= OPERATIONS_PREVIEW_LIMIT) return previews.join(', ');
    const head = previews.slice(0, OPERATIONS_PREVIEW_LIMIT).join(', ');
    const remainder = previews.length - OPERATIONS_PREVIEW_LIMIT;
    return `${head} +${remainder}`;
}

// ---------- normalize API → view model ----------
function normalize(raw) {
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

// ---------- component ----------
export default function TransactionsTable({ live }) {
    const [transactions, setTransactions] = useState([]);
    const [page, setPage] = useState(0);
    const [totalPages, setTotalPages] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [fork, setFork] = useState(null);

    const abortRef = useRef(null);
    const seenKeysRef = useRef(new Set());

    // Subscribe to fork-choice changes
    useEffect(() => {
        return subscribeFork((newFork) => setFork(newFork));
    }, []);

    // Fetch paginated transactions
    const fetchTransactions = useCallback(async (pageNum, currentFork) => {
        abortRef.current?.abort();
        seenKeysRef.current.clear();

        setLoading(true);
        setError(null);
        try {
            const res = await fetch(API.TRANSACTIONS_LIST(pageNum, TABLE_SIZE, currentFork));
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
    const startLiveStream = useCallback((currentFork) => {
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        seenKeysRef.current.clear();
        setTransactions([]);
        setLoading(true);
        setError(null);

        let liveTxs = [];

        const url = `${API.TRANSACTIONS_STREAM_WITH_FORK(currentFork)}&prefetch-limit=${encodeURIComponent(TABLE_SIZE)}`;
        streamNdjson(
            url,
            (raw) => {
                const tx = normalize(raw);
                const key = `${tx.id}:${tx.hash}`;
                if (seenKeysRef.current.has(key)) return;
                seenKeysRef.current.add(key);

                liveTxs = [tx, ...liveTxs].slice(0, TABLE_SIZE);
                setTransactions([...liveTxs]);
                setTotalCount(liveTxs.length);
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

    // Handle live mode and fork changes
    useEffect(() => {
        if (fork == null) return;
        if (live) {
            startLiveStream(fork);
        } else {
            setPage(0);
            fetchTransactions(0, fork);
        }
        return () => abortRef.current?.abort();
    }, [live, fork, startLiveStream]);

    // Go to a page
    const goToPage = (newPage) => {
        if (newPage >= 0 && fork != null) {
            fetchTransactions(newPage, fork);
        }
    };

    const navigateToTxDetail = (txHash) => {
        history.pushState({}, '', PAGE.TRANSACTION_DETAIL(txHash));
        window.dispatchEvent(new PopStateEvent('popstate'));
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
                        onClick: (e) => {
                            e.preventDefault();
                            navigateToTxDetail(tx.hash);
                        },
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
            h('div', null, h('strong', null, 'Transactions '), h('span', { class: 'pill' }, String(totalCount))),
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
                    disabled: live || page === 0 || loading,
                    onClick: () => goToPage(page - 1),
                    style: 'cursor:pointer;',
                },
                'Previous',
            ),
            h(
                'span',
                { style: 'color:var(--muted); font-size:13px;' },
                live ? 'Streaming live transactions...' : totalPages > 0 ? `Page ${page + 1} of ${totalPages}` : 'No transactions',
            ),
            h(
                'button',
                {
                    class: 'pill',
                    disabled: live || page >= totalPages - 1 || loading,
                    onClick: () => goToPage(page + 1),
                    style: 'cursor:pointer;',
                },
                'Next',
            ),
        ),
        // Error display
        error && h('div', { style: 'padding:8px 14px; color:#ff8a8a;' }, `Error: ${error}`),
    );
}
