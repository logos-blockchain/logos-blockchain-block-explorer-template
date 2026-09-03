// static/lib/channels.js
// Shared helpers for rendering channel operations (home panel + channel detail page).

// Extract a human-readable preview from inscription bytes (hex string).
// Inscriptions are binary payloads with embedded ASCII runs (e.g. LEZ program
// account paths); show the longest printable run.
export function inscriptionPreview(hex) {
    if (!hex || typeof hex !== 'string') return '';
    let text = '';
    for (let i = 0; i + 1 < hex.length; i += 2) {
        const code = parseInt(hex.slice(i, i + 2), 16);
        text += code >= 0x20 && code < 0x7f ? String.fromCharCode(code) : ' ';
    }
    const runs = text.split(' ').filter((run) => run.length >= 4);
    if (!runs.length) return '';
    runs.sort((a, b) => b.length - a.length);
    return runs[0];
}

// One-line summary of a channel operation's content.
export function summarize(content) {
    switch (content?.type) {
        case 'ChannelInscribe': {
            const preview = inscriptionPreview(content.inscription);
            const size = content.inscription ? content.inscription.length / 2 : 0;
            return preview ? `“${preview}”` : `${size} B payload`;
        }
        case 'ChannelConfig':
            return `${content.keys?.length ?? 0} keys · thresholds ${content.configuration_threshold}/${content.transfer_threshold}`;
        case 'ChannelDeposit':
            return `${content.inputs?.length ?? 0} inputs · ${content.metadata ? content.metadata.length / 2 : 0} B metadata`;
        case 'ChannelWithdraw':
            return `${content.inputs?.length ?? 0} inputs`;
        case 'ChannelTransfer':
            return `${content.inputs?.length ?? 0} in → ${content.outputs?.length ?? 0} out`;
        default:
            return '';
    }
}

export const OP_LABELS = {
    ChannelInscribe: 'INSCRIBE',
    ChannelConfig: 'CONFIG',
    ChannelDeposit: 'DEPOSIT',
    ChannelWithdraw: 'WITHDRAW',
    ChannelTransfer: 'TRANSFER',
};
