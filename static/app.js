import { h, render, Fragment } from 'preact';

import Router from './components/Router.js';
import HealthPill from './components/HealthPill.js';

import HomePage from './pages/Home.js';
import BlockDetailPage from './pages/BlockDetail.js';
import TransactionDetailPage from './pages/TransactionDetail.js';

const ROOT = document.getElementById('app');

//  Detect the Base Path from the HTML <base> tag.
//  If the tag is missing or equals "__BASE_PATH__", default to root "/".
const BASE_PATH = (() => {
    const baseHref = document.querySelector('base')?.getAttribute('href');
    if (!baseHref || baseHref === '__BASE_PATH__') return '/';

    return baseHref.endsWith('/') ? baseHref : `${baseHref}/`;
})();

function LoadingScreen() {
    return h('main', { class: 'wrap' }, h('p', null, 'Loading...'));
}

function AppShell(props) {
    return h(
        Fragment,
        null,
        h('header', null, h('h1', null, 'λ Blockchain Block Explorer'), h(HealthPill, null)),
        props.children,
    );
}

const ROUTES = [
    {
        name: 'home',
        re: /^\/$/,
        view: () => h(AppShell, null, h(HomePage, null)),
    },
    {
        name: 'blockDetail',
        re: /^\/blocks\/([^/]+)$/,
        view: ({ parameters }) => {
            return h(AppShell, null, h(BlockDetailPage, { parameters }));
        },
    },
    {
        name: 'transactionDetail',
        re: /^\/transactions\/([^/]+)$/,
        view: ({ parameters }) => h(AppShell, null, h(TransactionDetailPage, { parameters })),
    },
];

function AppRouter() {
    const wired = ROUTES.map((route) => ({
        re: route.re,
        view: route.view,
    }));

    // Pass the base prop to the Router so it knows where internal links start
    return h(Router, { routes: wired, base: BASE_PATH });
}

try {
    if (ROOT) {
        render(h(LoadingScreen, null), ROOT);
        render(h(AppRouter, null), ROOT);
    } else {
        console.error('Mount element #app not found.');
    }
} catch (err) {
    console.error('UI Error', err);
}
