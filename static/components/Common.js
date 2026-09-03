// static/components/Common.js
// Small presentational pieces shared by the detail pages.
import { h } from 'preact';
import { opLabel, renderBytes, toLocaleNum } from '../lib/format.js';

export function CopyPill({ text, label = 'Copy' }) {
    const onCopy = async (e) => {
        e.preventDefault();
        try {
            await navigator.clipboard.writeText(String(text ?? ''));
        } catch {}
    };
    return h(
        'a',
        {
            class: 'pill linkish mono',
            style: 'cursor:pointer; user-select:none;',
            href: '#',
            onClick: onCopy,
            onKeyDown: (e) => {
                if (e.key === 'Enter' || e.key === ' ') onCopy(e);
            },
            tabIndex: 0,
            role: 'button',
        },
        label,
    );
}

/** Operation type labels as pills, showing at most `limit` and a "+n" for the rest. */
export function OpPills({ ops, limit = 2, wrap = false }) {
    const arr = Array.isArray(ops) ? ops : [];
    if (!arr.length) return h('span', { style: 'color:var(--muted); white-space:nowrap;' }, '—');
    const labels = arr.map(opLabel);
    const shown = labels.slice(0, limit);
    const extra = labels.length - shown.length;
    return h(
        'div',
        {
            style: `display:flex; gap:6px; align-items:center; flex-wrap:${wrap ? 'wrap' : 'nowrap'}; white-space:nowrap;`,
        },
        ...shown.map((label, i) =>
            h('span', { key: `${label}-${i}`, class: 'pill', title: label, style: 'flex:0 0 auto;' }, label),
        ),
        extra > 0 && h('span', { class: 'pill', title: `${extra} more`, style: 'flex:0 0 auto;' }, `+${extra}`),
    );
}

/** Render one field of an operation's content or proof. */
export function FieldValue({ value }) {
    if (value == null) return h('span', { class: 'mono', style: 'color:var(--muted)' }, 'null');
    if (typeof value === 'number') return h('span', { class: 'mono' }, toLocaleNum(value));
    if (typeof value === 'string') {
        if (value.length > 24) {
            return h(
                'span',
                { style: 'display:flex; align-items:center; gap:6px;' },
                h('span', { class: 'mono', style: 'overflow-wrap:anywhere; word-break:break-all;' }, value),
                h(CopyPill, { text: value }),
            );
        }
        return h('span', { class: 'mono' }, value);
    }
    if (Array.isArray(value)) {
        if (!value.length) return h('span', { class: 'mono', style: 'color:var(--muted)' }, '[]');
        return h(
            'div',
            { style: 'display:flex; flex-direction:column; gap:4px;' },
            ...value.map((item, i) => h('div', { key: i }, h(FieldValue, { value: renderBytes(item) }))),
        );
    }
    return h('span', { class: 'mono', style: 'overflow-wrap:anywhere;' }, renderBytes(value));
}
