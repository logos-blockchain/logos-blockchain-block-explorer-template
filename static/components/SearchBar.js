// static/components/SearchBar.js
// Search box for note ids and public keys: validates 32-byte hex and navigates to the results page.
import { h } from 'preact';
import { useState } from 'preact/hooks';
import { PAGE } from '../lib/api.js';
import { navigateTo } from '../lib/utils.js';

const KEY_HEX_LENGTH = 64;

export const SEARCH_KINDS = {
    note: { label: 'Note id', page: PAGE.NOTE_DETAIL },
    public_key: { label: 'Public key', page: PAGE.KEY_DETAIL },
};

export default function SearchBar({ initialKind = 'note', initialValue = '' }) {
    const [kind, setKind] = useState(initialKind);
    const [value, setValue] = useState(initialValue);
    const [error, setError] = useState(null);
    const { label, page } = SEARCH_KINDS[kind];

    const submit = (e) => {
        e.preventDefault();
        const cleaned = value.trim().toLowerCase().replace(/^0x/, '');
        if (!new RegExp(`^[0-9a-f]{${KEY_HEX_LENGTH}}$`).test(cleaned)) {
            setError(`${label} must be ${KEY_HEX_LENGTH} hex characters.`);
            return;
        }
        setError(null);
        navigateTo(page(cleaned));
    };

    return h(
        'form',
        { class: 'note-search', onSubmit: submit },
        h(
            'select',
            {
                value: kind,
                'aria-label': 'Search by',
                onChange: (e) => {
                    setKind(e.currentTarget.value);
                    setError(null);
                },
            },
            ...Object.entries(SEARCH_KINDS).map(([k, v]) => h('option', { key: k, value: k }, v.label)),
        ),
        h('input', {
            class: 'mono',
            type: 'text',
            placeholder: `Search by ${label.toLowerCase()} (64 hex chars)…`,
            value,
            spellcheck: false,
            onInput: (e) => {
                setValue(e.currentTarget.value);
                if (error) setError(null);
            },
        }),
        h('button', { class: 'pill', type: 'submit' }, 'Search'),
        error && h('span', { class: 'note-search-error' }, error),
    );
}
