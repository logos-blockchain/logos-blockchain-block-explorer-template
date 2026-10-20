// static/pages/ReferenceSearch.js
// Search results for a note id or public key: every transaction with an op naming it.
import { h, Fragment } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import { API, PAGE, BASE_PATH } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';
import SearchBar, { SEARCH_KINDS } from '../components/SearchBar.js';

const KINDS = {
    note: { search: API.NOTE_SEARCH, empty: 'No transactions spend this note.' },
    public_key: {
        search: API.KEY_SEARCH,
        empty: 'No transactions name this public key.',
        // Spends carry only note ids, which the explorer cannot tie back to their owner's key.
        caveat: "Lists notes sent to this key and ops it signed or claimed, not spends of the key's notes.",
    },
};

function MatchTag({ match }) {
    const detail = match.item_index != null ? ` #${match.item_index}` : '';
    return h(
        'span',
        { class: 'pill note-match-tag', title: `operation #${match.op_index} · field ${match.field}` },
        `${match.op_type} · ${match.role}${detail}`,
    );
}

function ResultRow({ tx }) {
    const txUrl = PAGE.TRANSACTION_DETAIL(tx.hash);
    const blockUrl = PAGE.BLOCK_DETAIL(tx.block_hash);

    return h(
        'div',
        { class: 'note-result' },
        h(
            'div',
            { class: 'note-result-head' },
            h(
                'a',
                {
                    class: 'linkish mono',
                    href: txUrl,
                    title: tx.hash,
                },
                shortenHex(tx.hash, 12, 8),
            ),
            h(
                'a',
                {
                    class: 'linkish note-result-height',
                    href: blockUrl,
                    title: tx.block_hash,
                },
                `height ${tx.height} · slot ${tx.slot}`,
            ),
        ),
        h(
            'div',
            { class: 'note-result-matches' },
            ...(tx.matches ?? []).map((m, i) => h(MatchTag, { key: i, match: m })),
        ),
    );
}

export default function ReferenceSearch({ kind, parameters }) {
    const key = parameters?.[0];
    const isValidKey = typeof key === 'string' && key.length > 0;
    const { label } = SEARCH_KINDS[kind];
    const { search, empty, caveat } = KINDS[kind];

    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);

    const pageTitle = useMemo(() => `${label} ${shortenHex(key)}`, [label, key]);
    useEffect(() => {
        document.title = pageTitle;
    }, [pageTitle]);

    useEffect(() => {
        setData(null);
        setErr(null);

        if (!isValidKey) {
            setErr({ kind: 'invalid', msg: `Invalid ${label.toLowerCase()}.` });
            return;
        }

        let alive = true;
        const controller = new AbortController();

        (async () => {
            try {
                const res = await fetch(search(key), {
                    cache: 'no-cache',
                    signal: controller.signal,
                });
                if (res.status === 400) {
                    const payload = await res.json().catch(() => null);
                    if (alive) setErr({ kind: 'invalid', msg: payload?.detail ?? `Invalid ${label.toLowerCase()}.` });
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const payload = await res.json();
                if (!alive) return;
                setData(payload);
            } catch (e) {
                if (!alive || e?.name === 'AbortError') return;
                setErr({ kind: 'network', msg: e?.message ?? 'Search failed' });
            }
        })();

        return () => {
            alive = false;
            controller.abort();
        };
    }, [key, isValidKey, label, search]);

    return h(
        'main',
        { class: 'wrap' },

        h(
            'header',
            { style: 'display:flex; gap:12px; align-items:center; margin:12px 0;' },
            h('a', { class: 'linkish', href: `${BASE_PATH}/` }, '← Back'),
            h('h1', { style: 'margin:0' }, pageTitle),
        ),

        h(SearchBar, { key: `${kind}:${key}`, initialKind: kind, initialValue: key ?? '' }),

        err?.kind === 'invalid' && h('p', { style: 'color:var(--danger)' }, err.msg),
        err?.kind === 'network' && h('p', { style: 'color:var(--danger)' }, `Error: ${err.msg}`),

        !data && !err && h('p', null, 'Searching…'),

        data &&
            h(
                Fragment,
                null,
                h(
                    'div',
                    { class: 'note-search-head' },
                    h('span', { class: 'pill mono', style: 'overflow-wrap:anywhere;' }, data.key),
                    h('span', { class: 'channel-count' }, `${data.count} transaction${data.count === 1 ? '' : 's'}`),
                ),
                caveat && h('div', { class: 'channel-detail-scan-note' }, caveat),
                data.count === 0 && h('div', { class: 'channels-empty' }, empty),
                data.count > 0 &&
                    h(
                        'div',
                        { class: 'note-results' },
                        ...(data.transactions ?? []).map((tx) => h(ResultRow, { tx, key: tx.hash })),
                    ),
                data.count >= data.limit &&
                    h('div', { class: 'channel-detail-scan-note' }, `Showing the ${data.limit} most recent matches.`),
            ),
    );
}
