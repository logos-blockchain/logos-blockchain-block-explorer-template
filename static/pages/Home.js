import { h } from 'preact';
import { useState } from 'preact/hooks';
import BlocksTable from '../components/BlocksTable.js';
import TransactionsTable from '../components/TransactionsTable.js';

export default function HomeView() {
    const [live, setLive] = useState(true);

    const toggleLive = () => setLive((prev) => !prev);

    const liveButtonStyle = live
        ? `
            cursor: pointer;
            background: #ff4444;
            color: white;
            border: none;
            animation: live-pulse 1.5s ease-in-out infinite;
        `
        : `
            cursor: pointer;
            background: var(--bg-secondary, #333);
            color: var(--muted, #888);
            border: 1px solid var(--border, #444);
        `;

    return h(
        'main',
        { class: 'wrap' },
        h(
            'div',
            { style: 'display:flex; justify-content:flex-end; margin-bottom:12px;' },
            h(
                'button',
                {
                    class: 'pill',
                    style: liveButtonStyle,
                    onClick: toggleLive,
                    title: live ? 'Live updates enabled' : 'Click to enable live updates',
                },
                live ? 'LIVE \u2022' : 'LIVE',
            ),
        ),
        h('section', { class: 'two-columns twocol' },
            h(BlocksTable, { live, onDisableLive: () => setLive(false) }),
            h(TransactionsTable, { live, onDisableLive: () => setLive(false) }),
        ),
    );
}
