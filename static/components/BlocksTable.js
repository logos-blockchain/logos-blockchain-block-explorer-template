// static/components/BlocksTable.js
import { h } from 'preact';
import { useEffect, useState, useCallback, useRef } from 'preact/hooks';
import { PAGE, API } from '../lib/api.js';
import { TABLE_SIZE } from '../lib/constants.js';
import { shortenHex, streamNdjson } from '../lib/utils.js';

const normalize = (raw) => ({
    id: Number(raw.id ?? 0),
    height: Number(raw.height ?? 0),
    slot: Number(raw.slot ?? 0),
    hash: raw.hash ?? '',
    parent: raw.parent_block_hash ?? '',
    root: raw.block_root ?? '',
    transactionCount: Number(raw.transaction_count ?? 0),
    uncleCount: Number(raw.uncle_count ?? 0),
});

export default function BlocksTable({ live, onDisableLive }) {
    const [blocks, setBlocks] = useState([]);
    const [page, setPage] = useState(0);
    const [totalPages, setTotalPages] = useState(0);
    const [totalCount, setTotalCount] = useState(0);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    const abortRef = useRef(null);
    const seenKeysRef = useRef(new Set());

    // Fetch paginated blocks
    const fetchBlocks = useCallback(async (pageNum) => {
        // Stop any live stream
        abortRef.current?.abort();
        seenKeysRef.current.clear();

        setLoading(true);
        setError(null);
        try {
            const res = await fetch(API.BLOCKS_LIST(pageNum, TABLE_SIZE));
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
    const startLiveStream = useCallback(() => {
        abortRef.current?.abort();
        abortRef.current = new AbortController();
        seenKeysRef.current.clear();
        setBlocks([]);
        setLoading(true);
        setError(null);

        let liveBlocks = [];

        streamNdjson(
            API.BLOCKS_STREAM(TABLE_SIZE),
            (raw) => {
                const b = normalize(raw);
                if (seenKeysRef.current.has(b.hash)) return;
                seenKeysRef.current.add(b.hash);

                // One row per height: a reorg replaces the orphaned block at that height.
                // Newest first, keep max TABLE_SIZE.
                const byHeight = new Map(liveBlocks.map((x) => [x.height, x]));
                byHeight.set(b.height, b);
                liveBlocks = [...byHeight.values()].sort((x, y) => y.height - x.height).slice(0, TABLE_SIZE);
                setBlocks([...liveBlocks]);
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

    useEffect(() => {
        if (live) {
            startLiveStream();
        } else {
            setPage(0);
            fetchBlocks(0);
        }
        return () => abortRef.current?.abort();
    }, [live, startLiveStream, fetchBlocks]);

    // Go to a page (or exit live mode into page 0)
    const goToPage = (newPage) => {
        if (live) {
            onDisableLive?.();
            return; // useEffect will handle fetching page 0 when live changes
        }
        if (newPage >= 0) {
            fetchBlocks(newPage);
        }
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
                    },
                    shortenHex(b.parent),
                ),
            ),
            // Block Root
            h('td', null, h('span', { class: 'mono', title: b.root }, shortenHex(b.root))),
            // Transactions
            h('td', null, h('span', { class: 'mono' }, String(b.transactionCount))),
            // Uncles
            h('td', null, h('span', { class: 'mono' }, String(b.uncleCount))),
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
            h(
                'div',
                null,
                h('strong', null, 'Blocks '),
                !live && totalCount > 0 && h('span', { class: 'pill' }, String(totalCount)),
            ),
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
                    h('col', { style: 'width:70px' }), // Uncles
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
                        h('th', null, 'Uncles'),
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
                live ? 'Streaming live blocks...' : totalPages > 0 ? `Page ${page + 1} of ${totalPages}` : 'No blocks',
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
