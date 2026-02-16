// static/components/BlocksTable.js
import { h } from 'preact';
import { useEffect, useState, useCallback, useRef } from 'preact/hooks';
import { PAGE, API } from '../lib/api.js';
import { TABLE_SIZE } from '../lib/constants.js';
import { shortenHex, streamNdjson } from '../lib/utils.js';
import { subscribeFork } from '../lib/fork.js';

const normalize = (raw) => {
    const header = raw.header ?? null;
    const txLen = Array.isArray(raw.transactions)
        ? raw.transactions.length
        : Array.isArray(raw.txs)
          ? raw.txs.length
          : 0;

    return {
        id: Number(raw.id ?? 0),
        height: Number(raw.height ?? 0),
        slot: Number(raw.slot ?? header?.slot ?? 0),
        hash: raw.hash ?? header?.hash ?? '',
        parent: raw.parent_block_hash ?? header?.parent_block ?? raw.parent_block ?? '',
        root: raw.block_root ?? header?.block_root ?? '',
        transactionCount: txLen,
    };
};

export default function BlocksTable({ live, onDisableLive }) {
    const [blocks, setBlocks] = useState([]);
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

    // Fetch paginated blocks
    const fetchBlocks = useCallback(async (pageNum, currentFork) => {
        // Stop any live stream
        abortRef.current?.abort();
        seenKeysRef.current.clear();

        setLoading(true);
        setError(null);
        try {
            const res = await fetch(API.BLOCKS_LIST(pageNum, TABLE_SIZE, currentFork));
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            setBlocks(data.blocks.map(normalize));
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
        setBlocks([]);
        setLoading(true);
        setError(null);

        let liveBlocks = [];

        const url = `${API.BLOCKS_STREAM(currentFork)}&prefetch-limit=${encodeURIComponent(TABLE_SIZE)}`;
        streamNdjson(
            url,
            (raw) => {
                const b = normalize(raw);
                const key = `${b.id}:${b.slot}`;
                if (seenKeysRef.current.has(key)) return;
                seenKeysRef.current.add(key);

                // Add to front, keep max TABLE_SIZE
                liveBlocks = [b, ...liveBlocks].slice(0, TABLE_SIZE);
                setBlocks([...liveBlocks]);
                setTotalCount(liveBlocks.length);
                setLoading(false);
            },
            {
                signal: abortRef.current.signal,
                onError: (e) => {
                    if (e?.name !== 'AbortError') {
                        console.error('Blocks stream error:', e);
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
            fetchBlocks(0, fork);
        }
        return () => abortRef.current?.abort();
    }, [live, fork, startLiveStream]);

    // Go to a page
    const goToPage = (newPage) => {
        if (newPage >= 0 && fork != null) {
            if (live) onDisableLive?.();
            fetchBlocks(newPage, fork);
        }
    };

    const navigateToBlockDetail = (blockHash) => {
        history.pushState({}, '', PAGE.BLOCK_DETAIL(blockHash));
        window.dispatchEvent(new PopStateEvent('popstate'));
    };

    const renderRow = (b, idx) => {
        return h(
            'tr',
            { key: b.id || idx },
            // Hash
            h(
                'td',
                null,
                h(
                    'a',
                    {
                        class: 'linkish mono',
                        href: PAGE.BLOCK_DETAIL(b.hash),
                        title: b.hash,
                        onClick: (e) => {
                            e.preventDefault();
                            navigateToBlockDetail(b.hash);
                        },
                    },
                    shortenHex(b.hash),
                ),
            ),
            // Height
            h('td', null, h('span', { class: 'mono' }, String(b.height))),
            // Slot
            h('td', null, h('span', { class: 'mono' }, String(b.slot))),
            // Parent
            h(
                'td',
                null,
                h(
                    'a',
                    {
                        class: 'linkish mono',
                        href: PAGE.BLOCK_DETAIL(b.parent),
                        title: b.parent,
                        onClick: (e) => {
                            e.preventDefault();
                            navigateToBlockDetail(b.parent);
                        },
                    },
                    shortenHex(b.parent),
                ),
            ),
            // Block Root
            h('td', null, h('span', { class: 'mono', title: b.root }, shortenHex(b.root))),
            // Transactions
            h('td', null, h('span', { class: 'mono' }, String(b.transactionCount))),
        );
    };

    const renderPlaceholderRow = (idx) => {
        return h(
            'tr',
            { key: `ph-${idx}`, class: 'ph' },
            h('td', null, '\u00A0'),
            h('td', null, '\u00A0'),
            h('td', null, '\u00A0'),
            h('td', null, '\u00A0'),
            h('td', null, '\u00A0'),
            h('td', null, '\u00A0'),
        );
    };

    const rows = [];
    for (let i = 0; i < TABLE_SIZE; i++) {
        if (i < blocks.length) {
            rows.push(renderRow(blocks[i], i));
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
            h('div', null, h('strong', null, 'Blocks '), h('span', { class: 'pill' }, String(totalCount))),
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
                    h('col', { style: 'width:200px' }), // Hash
                    h('col', { style: 'width:70px' }), // Height
                    h('col', { style: 'width:80px' }), // Slot
                    h('col', { style: 'width:200px' }), // Parent
                    h('col', { style: 'width:200px' }), // Block Root
                    h('col', { style: 'width:100px' }), // Transactions
                ),
                h(
                    'thead',
                    null,
                    h(
                        'tr',
                        null,
                        h('th', null, 'Hash'),
                        h('th', null, 'Height'),
                        h('th', null, 'Slot'),
                        h('th', null, 'Parent'),
                        h('th', null, 'Block Root'),
                        h('th', null, 'Transactions'),
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
                    disabled: page === 0 || loading,
                    onClick: () => goToPage(page - 1),
                },
                'Previous',
            ),
            h(
                'span',
                { style: 'color:var(--muted); font-size:13px;' },
                live ? 'Streaming live blocks...' : totalPages > 0 ? `Page ${page + 1} of ${totalPages}` : 'No blocks',
            ),
            h(
                'button',
                {
                    class: 'pill',
                    disabled: page >= totalPages - 1 || loading,
                    onClick: () => goToPage(page + 1),
                },
                'Next',
            ),
        ),
        // Error display
        error && h('div', { style: 'padding:8px 14px; color:#ff8a8a;' }, `Error: ${error}`),
    );
}
