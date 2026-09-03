// static/pages/ChannelDetail.js
import { h, Fragment } from 'preact';
import { useEffect, useMemo, useRef, useState } from 'preact/hooks';
import { API, PAGE, BASE_PATH } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';
import { subscribeFork } from '../lib/fork.js';
import { summarize, OP_LABELS } from '../lib/channels.js';
import { fieldLabel, tryDecodeUtf8Hex } from '../lib/format.js';
import { FieldValue } from '../components/Common.js';

const PAGE_SIZE = 25;

function ContentFields({ content }) {
    const entries = Object.entries(content ?? {}).filter(([k]) => k !== 'type');
    if (!entries.length) return null;
    return h(
        'div',
        { class: 'channel-detail-fields' },
        ...entries.flatMap(([key, value]) => {
            const decoded = key === 'inscription' ? tryDecodeUtf8Hex(value) : null;
            return [
                h('span', { class: 'channel-detail-field-key' }, fieldLabel(key)),
                decoded != null
                    ? h('span', { style: 'overflow-wrap:anywhere; word-break:break-word;' }, decoded)
                    : h(FieldValue, { value }),
            ];
        }),
    );
}

function OperationRow({ op, highlighted }) {
    const [expanded, setExpanded] = useState(false);
    const label = OP_LABELS[op.content?.type] ?? op.content?.type ?? '?';
    const txUrl = PAGE.TRANSACTION_DETAIL(op.transaction_hash);
    const blockUrl = PAGE.BLOCK_DETAIL(op.block_hash);
    const ref = useRef(null);

    useEffect(() => {
        if (highlighted && ref.current) {
            ref.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }, [highlighted]);

    return h(
        'div',
        { class: `channel-detail-op${highlighted ? ' is-highlighted' : ''}`, ref, id: `op-${op.index}` },
        h(
            'div',
            { class: 'channel-op-head' },
            h('span', { class: 'pill mono channel-detail-op-index' }, `#${op.index}`),
            h('span', { class: 'op-tag' }, label),
            h(
                'a',
                {
                    class: 'linkish mono channel-op-tx',
                    href: txUrl,
                    title: op.transaction_hash,
                },
                shortenHex(op.transaction_hash, 8, 6),
            ),
            h(
                'a',
                {
                    class: 'linkish channel-op-height',
                    href: blockUrl,
                    title: op.block_hash,
                },
                `height ${op.height} · slot ${op.slot}`,
            ),
        ),
        h('div', { class: 'channel-op-summary' }, summarize(op.content)),
        h(
            'a',
            {
                class: 'linkish channel-detail-toggle',
                href: '#',
                onClick: (e) => {
                    e.preventDefault();
                    setExpanded(!expanded);
                },
            },
            expanded ? 'Hide fields' : 'Show fields',
        ),
        expanded && h(ContentFields, { content: op.content }),
    );
}

function JumpToOp({ opCount, onJump }) {
    const [value, setValue] = useState('');

    const submit = (e) => {
        e.preventDefault();
        const n = Number.parseInt(value, 10);
        if (!Number.isInteger(n)) return;
        onJump(Math.max(0, Math.min(n, opCount - 1)));
    };

    return h(
        'form',
        { class: 'channel-jump', onSubmit: submit },
        h('label', { for: 'jump-op' }, 'Go to operation'),
        h('input', {
            id: 'jump-op',
            class: 'mono',
            type: 'number',
            min: 0,
            max: Math.max(0, opCount - 1),
            placeholder: 'n',
            value,
            onInput: (e) => setValue(e.currentTarget.value),
        }),
        h('button', { class: 'pill', type: 'submit', disabled: opCount === 0 }, 'Go'),
        h('span', { class: 'channel-jump-note' }, opCount > 0 ? `0 – ${opCount - 1}` : 'no operations'),
    );
}

export default function ChannelDetail({ parameters }) {
    const channelId = parameters?.[0];
    const isValidId = typeof channelId === 'string' && channelId.length > 0;

    const [data, setData] = useState(null);
    const [err, setErr] = useState(null);
    const [fork, setFork] = useState(null);
    const [page, setPage] = useState(0);
    const [highlightIndex, setHighlightIndex] = useState(null);

    useEffect(() => {
        return subscribeFork((newFork) => setFork(newFork));
    }, []);

    const pageTitle = useMemo(() => `Channel ${shortenHex(channelId)}`, [channelId]);
    useEffect(() => {
        document.title = pageTitle;
    }, [pageTitle]);

    useEffect(() => {
        setErr(null);

        if (!isValidId) {
            setErr({ kind: 'invalid', msg: 'Invalid channel id.' });
            return;
        }
        if (fork == null) return;

        let alive = true;
        const controller = new AbortController();

        (async () => {
            try {
                const res = await fetch(API.CHANNEL_DETAIL_BY_ID(channelId, fork, page, PAGE_SIZE), {
                    cache: 'no-cache',
                    signal: controller.signal,
                });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const payload = await res.json();
                if (!alive) return;
                setData(payload);
            } catch (e) {
                if (!alive || e?.name === 'AbortError') return;
                setErr({ kind: 'network', msg: e?.message ?? 'Failed to load channel' });
            }
        })();

        return () => {
            alive = false;
            controller.abort();
        };
    }, [channelId, isValidId, fork, page]);

    const opCount = data?.op_count ?? 0;
    const pageCount = Math.max(1, Math.ceil(opCount / PAGE_SIZE));

    const jumpTo = (index) => {
        setHighlightIndex(index);
        setPage(Math.floor(index / PAGE_SIZE));
    };

    return h(
        'main',
        { class: 'wrap' },

        h(
            'header',
            { style: 'display:flex; gap:12px; align-items:center; margin:12px 0;' },
            h('a', { class: 'linkish', href: `${BASE_PATH}/` }, '← Back'),
            h('h1', { style: 'margin:0' }, pageTitle),
        ),

        err?.kind === 'invalid' && h('p', { style: 'color:var(--danger)' }, err.msg),
        err?.kind === 'network' && h('p', { style: 'color:var(--danger)' }, `Error: ${err.msg}`),

        !data && !err && h('p', null, 'Loading…'),

        data &&
            h(
                Fragment,
                null,
                h(
                    'div',
                    { class: 'channel-detail-head' },
                    h('span', { class: 'pill mono', style: 'overflow-wrap:anywhere;' }, channelId),
                    h('span', { class: 'channel-count' }, `${opCount} ops`),
                ),
                h(
                    'div',
                    { class: 'channel-detail-scan-note' },
                    'Operations are indexed oldest-first across the channel’s full history on this fork.',
                ),
                h(JumpToOp, { opCount, onJump: jumpTo }),

                opCount === 0 &&
                    h('div', { class: 'channels-empty' }, 'No operations found for this channel on this fork.'),

                opCount > 0 &&
                    h(
                        'div',
                        { class: 'channel-detail-ops' },
                        ...(data.operations ?? []).map((op) =>
                            h(OperationRow, { op, key: op.index, highlighted: op.index === highlightIndex }),
                        ),
                    ),

                opCount > PAGE_SIZE &&
                    h(
                        'div',
                        { class: 'channel-detail-pager' },
                        h(
                            'button',
                            { class: 'pill', disabled: page === 0, onClick: () => setPage(page - 1) },
                            '← Prev',
                        ),
                        h('span', null, `Page ${page + 1} of ${pageCount}`),
                        h(
                            'button',
                            { class: 'pill', disabled: page >= pageCount - 1, onClick: () => setPage(page + 1) },
                            'Next →',
                        ),
                    ),
            ),
    );
}
