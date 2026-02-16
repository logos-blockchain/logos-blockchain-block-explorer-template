const _baseHref = new URL(document.baseURI).pathname;
export const BASE_PATH = _baseHref.endsWith('/') ? _baseHref.slice(0, -1) : _baseHref;

const API_PREFIX = `${BASE_PATH}/api/v1`;

const joinUrl = (...parts) => parts.join('/').replace(/\/{2,}/g, '/');
const encodeHash = (hash) => encodeURIComponent(String(hash));

const HEALTH_ENDPOINT = joinUrl(API_PREFIX, 'health/stream');

const TRANSACTION_DETAIL_BY_HASH = (hash) => joinUrl(API_PREFIX, 'transactions', encodeHash(hash));
const TRANSACTIONS_STREAM = joinUrl(API_PREFIX, 'transactions/stream');

const FORK_CHOICE = joinUrl(API_PREFIX, 'fork-choice');

const BLOCK_DETAIL_BY_HASH = (hash) => joinUrl(API_PREFIX, 'blocks', encodeHash(hash));
const BLOCKS_STREAM = (fork) =>
    `${joinUrl(API_PREFIX, 'blocks/stream')}?fork=${encodeURIComponent(fork)}`;
const BLOCKS_LIST = (page, pageSize, fork) =>
    `${joinUrl(API_PREFIX, 'blocks/list')}?page=${encodeURIComponent(page)}&page-size=${encodeURIComponent(pageSize)}&fork=${encodeURIComponent(fork)}`;

const TRANSACTIONS_STREAM_WITH_FORK = (fork) =>
    `${joinUrl(API_PREFIX, 'transactions/stream')}?fork=${encodeURIComponent(fork)}`;

export const API = {
    HEALTH_ENDPOINT,
    FORK_CHOICE,
    TRANSACTION_DETAIL_BY_HASH,
    TRANSACTIONS_STREAM,
    TRANSACTIONS_STREAM_WITH_FORK,
    BLOCK_DETAIL_BY_HASH,
    BLOCKS_STREAM,
    BLOCKS_LIST,
};

const BLOCK_DETAIL = (hash) => joinUrl(`${BASE_PATH}/blocks`, encodeHash(hash));
const TRANSACTION_DETAIL = (hash) => joinUrl(`${BASE_PATH}/transactions`, encodeHash(hash));

export const PAGE = {
    BLOCK_DETAIL,
    TRANSACTION_DETAIL,
};
