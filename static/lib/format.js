// static/lib/format.js
// Pure formatting helpers shared by the tables and detail pages.

export const toNumber = (v) => {
    if (v == null) return 0;
    if (typeof v === 'number') return v;
    if (typeof v === 'bigint') return Number(v);
    if (typeof v === 'string') {
        const s = v.trim();
        if (/^0x[0-9a-f]+$/i.test(s)) return Number(BigInt(s));
        const n = Number(s);
        return Number.isFinite(n) ? n : 0;
    }
    if (typeof v === 'object' && 'value' in v) return toNumber(v.value);
    return 0;
};

export const toLocaleNum = (n, opts = {}) =>
    Number(n ?? 0).toLocaleString(undefined, { maximumFractionDigits: 8, ...opts });

/** Best-effort text for a bytes-ish value: hex string, int array, or anything else. */
export function renderBytes(value) {
    if (value == null) return '';
    if (typeof value === 'string') return value;
    if (Array.isArray(value) && value.every((x) => Number.isInteger(x) && x >= 0 && x <= 255)) {
        return '0x' + value.map((b) => b.toString(16).padStart(2, '0')).join('');
    }
    try {
        return JSON.stringify(value);
    } catch {
        return String(value);
    }
}

/** Decode a hex string as UTF-8 if it is valid and contains printable text; otherwise null. */
export function tryDecodeUtf8Hex(hex) {
    if (typeof hex !== 'string' || hex.length === 0 || hex.length % 2 !== 0) return null;
    try {
        const bytes = new Uint8Array(hex.length / 2);
        for (let i = 0; i < hex.length; i += 2) {
            const b = parseInt(hex.substring(i, i + 2), 16);
            if (Number.isNaN(b)) return null;
            bytes[i / 2] = b;
        }
        const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
        return /[\x20-\x7e]/.test(text) ? text : null;
    } catch {
        return null;
    }
}

/** Operation type label: operations are `{ content: { type } , proof }`. */
export const opLabel = (op) => op?.content?.type ?? op?.type ?? 'op';

/** "posting_timeframe" -> "Posting Timeframe" */
export const fieldLabel = (key) => key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());

/** Outputs of every LedgerTransfer op in a transaction, with their count and total value. */
export function transferOutputs(ops) {
    const outputs = [];
    for (const op of Array.isArray(ops) ? ops : []) {
        const content = op?.content ?? op;
        if (content?.type === 'LedgerTransfer' && Array.isArray(content.outputs)) outputs.push(...content.outputs);
    }
    const total = outputs.reduce((sum, note) => sum + toNumber(note?.value), 0);
    return { outputs, count: outputs.length, total };
}
