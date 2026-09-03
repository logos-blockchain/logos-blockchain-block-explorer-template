import { h } from 'preact';
import { useState } from 'preact/hooks';
import BlocksTable from '../components/BlocksTable.js';
import TransactionsTable from '../components/TransactionsTable.js';
import ChannelsPanel from '../components/ChannelsPanel.js';
import NoteSearchBar from '../components/NoteSearchBar.js';

export default function HomeView() {
    const [live, setLive] = useState(true);

    const toggleLive = () => setLive((prev) => !prev);

    return h(
        'main',
        { class: 'wrap' },
        h(
            'div',
            { style: 'display:flex; gap:12px; align-items:flex-start; justify-content:space-between; margin-bottom:12px;' },
            h(NoteSearchBar, null),
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
