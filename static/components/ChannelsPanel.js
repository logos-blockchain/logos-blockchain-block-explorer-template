// static/components/ChannelsPanel.js
import { h } from 'preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { API, PAGE } from '../lib/api.js';
import { shortenHex } from '../lib/utils.js';
import { summarize, OP_LABELS } from '../lib/channels.js';

const CHANNEL_LIMIT = 8;
const OPS_LIMIT = 25;
const REFRESH_INTERVAL_MS = 15000;

function ChannelOp({ op }) {
    const label = OP_LABELS[op.content?.type] ?? op.content?.type ?? '?';
    const txUrl = PAGE.TRANSACTION_DETAIL(op.transaction_hash);
    return h(
        'div',
        { class: 'channel-op' },
        h(
            'div',
            { class: 'channel-op-head' },
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
            h('span', { class: 'channel-op-height' }, `#${op.height}`),
        ),
        h('div', { class: 'channel-op-summary' }, summarize(op.content)),
    );
}

function ChannelColumn({ channel }) {
    const channelUrl = PAGE.CHANNEL_DETAIL(channel.channel_id);
    return h(
        'div',
        { class: 'channel-column' },
        h(
            'div',
            { class: 'channel-column-head' },
            h(
                'a',
                {
                    class: 'linkish mono channel-id',
                    href: channelUrl,
                    title: channel.channel_id,
                },
                shortenHex(channel.channel_id, 8, 6),
            ),
            h('span', { class: 'channel-count' }, `${channel.op_count} ops`),
        ),
        h(
            'div',
            { class: 'channel-column-meta' },
            `last activity · height ${channel.last_height} · slot ${channel.last_slot}`,
        ),
        h(
            'div',
            { class: 'channel-ops' },
            ...channel.operations.map((op, idx) => h(ChannelOp, { op, key: `${op.transaction_hash}-${idx}` })),
        ),
    );
}

export default function ChannelsPanel() {
    const [channels, setChannels] = useState(null); // null = loading
    const [error, setError] = useState(null);
    const timerRef = useRef(null);

    useEffect(() => {
        let cancelled = false;

        const load = async () => {
            try {
                const res = await fetch(API.CHANNELS_LIST(CHANNEL_LIMIT, OPS_LIMIT), { cache: 'no-cache' });
                if (!res.ok) throw new Error(`HTTP ${res.status}`);
                const data = await res.json();
                if (!cancelled) {
                    setChannels(data.channels ?? []);
                    setError(null);
                }
            } catch (e) {
                if (!cancelled) setError(e.message);
            }
        };

        load();
        timerRef.current = setInterval(load, REFRESH_INTERVAL_MS);
        return () => {
            cancelled = true;
            clearInterval(timerRef.current);
        };
    }, []);

    return h(
        'section',
        { class: 'channels-section' },
        h(
            'div',
            { class: 'section-label' },
            h('span', null, 'Channels'),
            h('span', { class: 'section-label-note' }, 'top by activity'),
        ),
        error && h('div', { class: 'error-note' }, `Error: ${error}`),
        channels == null && !error && h('div', { class: 'channels-empty' }, 'Loading channels…'),
        channels != null &&
            channels.length === 0 &&
            h('div', { class: 'channels-empty' }, 'No channel activity on this chain yet.'),
        channels != null &&
            channels.length > 0 &&
            h(
                'div',
                { class: 'channels-row' },
                ...channels.map((channel) => h(ChannelColumn, { channel, key: channel.channel_id })),
            ),
    );
}
