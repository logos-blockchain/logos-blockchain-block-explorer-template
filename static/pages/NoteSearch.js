// static/pages/NoteSearch.js
// Search results for a note id: every transaction with an op referencing it.
import { h, Fragment } from 'preact';
import { useEffect, useMemo, useState } from 'preact/hooks';
import { API, PAGE, BASE_PATH } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';
import NoteSearchBar from '../components/NoteSearchBar.js';

function MatchTag({ match }) {
    const detail = match.input_index != null ? ` #${match.input_index}` : '';
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

export default function NoteSearch({ parameters }) {
    const noteId = parameters?.[0];
    const isValidId = typeof noteId === 'string' && noteId.length > 0;

    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);

    const pageTitle = useMemo(() => `Note ${shortenHex(noteId)}`, [noteId]);
    useEffect(() => {
        document.title = pageTitle;
    }, [pageTitle]);

    useEffect(() => {
        setData(null);
        setErr(null);

        if (!isValidId) {
            setErr({ kind: 'invalid', msg: 'Invalid note id.' });
            return;
        }

        let alive = true;
        const controller = new AbortController();

        (async () => {
            try {
                const res = await fetch(API.NOTE_SEARCH(noteId), {
                    cache: 'no-cache',
                    signal: controller.signal,
                });
                if (res.status === 400) {
                    const payload = await res.json().catch(() => null);
                    if (alive) setErr({ kind: 'invalid', msg: payload?.detail ?? 'Invalid note id.' });
                    return;
                }
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const payload = await res.json();
                if (!alive) return;
                setData(payload);
            } catch (e) {
                if (!alive || e?.name === 'AbortError') return;
                setErr({ kind: 'network', msg: e?.message ?? 'Failed to search for note' });
            }
        })();

        return () => {
            alive = false;
            controller.abort();
        };
    }, [noteId, isValidId]);

    return h(
        'main',
        { class: 'wrap' },

        h(
            'header',
            { style: 'display:flex; gap:12px; align-items:center; margin:12px 0;' },
            h('a', { class: 'linkish', href: `${BASE_PATH}/` }, '← Back'),
            h('h1', { style: 'margin:0' }, pageTitle),
        ),

        h(NoteSearchBar, { initialValue: noteId ?? '' }),

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
                    h('span', { class: 'pill mono', style: 'overflow-wrap:anywhere;' }, data.note_id),
                    h('span', { class: 'channel-count' }, `${data.count} transaction${data.count === 1 ? '' : 's'}`),
                ),
                data.count === 0 && h('div', { class: 'channels-empty' }, 'No transactions reference this note id.'),
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
