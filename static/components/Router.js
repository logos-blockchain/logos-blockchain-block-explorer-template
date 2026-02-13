import { h } from 'preact';
import { useEffect, useState } from 'preact/hooks';
import { BASE_PATH } from '../lib/api.js';

/** Strip the BASE_PATH prefix from a pathname so route regexes match the relative path. */
function stripBase(pathname) {
    if (BASE_PATH && pathname.startsWith(BASE_PATH)) {
        const relative = pathname.slice(BASE_PATH.length);
        return relative.startsWith('/') ? relative : '/' + relative;
    }
    return pathname;
}

export default function AppRouter({ routes }) {
    const [match, setMatch] = useState(() => resolveRoute(location.pathname, routes));

    useEffect(() => {
        const handlePopState = () => setMatch(resolveRoute(location.pathname, routes));

        const handleLinkClick = (event) => {
            if (event.defaultPrevented || event.button !== 0) return; // only left-click
            if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

            const anchor = event.target.closest?.('a[href]');
            if (!anchor) return;

            // Respect hints/targets
            if (anchor.target && anchor.target !== '_self') return;
            if (anchor.hasAttribute('download')) return;
            if (anchor.getAttribute('rel')?.includes('external')) return;
            if (anchor.dataset.external === 'true' || anchor.dataset.noRouter === 'true') return;

            const href = anchor.getAttribute('href');
            if (!href) return;

            // Allow in-page, mailto, tel, etc.
            if (href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return;

            // Cross-origin goes to browser
            if (anchor.origin !== location.origin) return;

            // Likely a static asset
            if (/\.[a-z0-9]+($|\?)/i.test(href)) return;

            event.preventDefault();
            history.pushState({}, '', href);
            setMatch(resolveRoute(location.pathname, routes));
        };

        window.addEventListener('popstate', handlePopState);
        document.addEventListener('click', handleLinkClick);
        return () => {
            window.removeEventListener('popstate', handlePopState);
            document.removeEventListener('click', handleLinkClick);
        };
    }, [routes]);

    const View = match?.view ?? NotFound;
    return h(View, { parameters: match?.parameters ?? [] });
}

function resolveRoute(pathname, routes) {
    const relative = stripBase(pathname);
    for (const route of routes) {
        const rx = route.pattern || route.re;
        if (!rx) continue;
        const m = relative.match(rx);
        if (m) return { view: route.view, parameters: m.slice(1) };
    }
    return null;
}

function NotFound() {
    return h('main', { class: 'wrap' }, h('h1', null, 'Not found'));
}
