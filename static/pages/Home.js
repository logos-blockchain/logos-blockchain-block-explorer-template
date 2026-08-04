import { h } from 'preact';
import { useState } from 'preact/hooks';
import BlocksTable from '../components/BlocksTable.js';
import TransactionsTable from '../components/TransactionsTable.js';
import ChannelsPanel from '../components/ChannelsPanel.js';

export default function HomeView() {
    const [live, setLive] = useState(true);

    const toggleLive = () => setLive((prev) => !prev);

    return h(
        'main',
        { class: 'wrap' },
        h(
            'div',
            { style: 'display:flex; justify-content:flex-end; margin-bottom:12px;' },
            h(
                'button',
                {
                    class: `pill live-toggle ${live ? 'is-live' : ''}`,
                    onClick: toggleLive,
                    title: live ? 'Live updates enabled' : 'Click to enable live updates',
                },
                live ? 'LIVE \u25cf' : 'LIVE',
            ),
        ),
        h(
            'section',
            { class: 'two-columns twocol' },
            h(BlocksTable, { live, onDisableLive: () => setLive(false) }),
            h(TransactionsTable, { live, onDisableLive: () => setLive(false) }),
        ),
        h(ChannelsPanel, null),
    );
}
