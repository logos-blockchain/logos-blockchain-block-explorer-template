// static/components/NoteSearchBar.js
// Search box for note ids: validates 32-byte hex and navigates to the note page.
import { h } from 'preact';
import { useState } from 'preact/hooks';
import { PAGE } from '../lib/api.js';
import { navigateTo } from '../lib/utils.js';

const NOTE_ID_HEX_LENGTH = 64;

export default function NoteSearchBar({ initialValue = '' }) {
    const [value, setValue] = useState(initialValue);
    const [error, setError] = useState(null);

    const submit = (e) => {
        e.preventDefault();
        const cleaned = value.trim().toLowerCase().replace(/^0x/, '');
        if (!new RegExp(`^[0-9a-f]{${NOTE_ID_HEX_LENGTH}}$`).test(cleaned)) {
            setError(`Note id must be ${NOTE_ID_HEX_LENGTH} hex characters.`);
            return;
        }
        setError(null);
        navigateTo(PAGE.NOTE_DETAIL(cleaned));
    };

    return h(
        'form',
        { class: 'note-search', onSubmit: submit },
        h('input', {
            class: 'mono',
            type: 'text',
            placeholder: 'Search by note id (64 hex chars)…',
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
