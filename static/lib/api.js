const _baseHref = new URL(document.baseURI).pathname;
export const BASE_PATH = _baseHref.endsWith('/') ? _baseHref.slice(0, -1) : _baseHref;

const API_PREFIX = `${BASE_PATH}/api/v1`;

const joinUrl = (...parts) => parts.join('/').replace(/\/{2,}/g, '/');
const encodeHash = (hash) => encodeURIComponent(String(hash));

const HEALTH_ENDPOINT = joinUrl(API_PREFIX, 'health/stream');

const TRANSACTION_DETAIL_BY_HASH = (hash, fork) =>
    `${joinUrl(API_PREFIX, 'transactions', encodeHash(hash))}?fork=${encodeURIComponent(fork)}`;
const TRANSACTIONS_STREAM = joinUrl(API_PREFIX, 'transactions/stream');

const FORK_CHOICE = joinUrl(API_PREFIX, 'fork-choice');

const BLOCK_DETAIL_BY_HASH = (hash) => joinUrl(API_PREFIX, 'blocks', encodeHash(hash));
const BLOCKS_STREAM = (fork) => `${joinUrl(API_PREFIX, 'blocks/stream')}?fork=${encodeURIComponent(fork)}`;
const BLOCKS_LIST = (page, pageSize, fork) =>
    `${joinUrl(API_PREFIX, 'blocks/list')}?page=${encodeURIComponent(page)}&page-size=${encodeURIComponent(pageSize)}&fork=${encodeURIComponent(fork)}`;

const CHANNELS_LIST = (fork, limit, opsLimit) =>
    `${joinUrl(API_PREFIX, 'channels/list')}?fork=${encodeURIComponent(fork)}&limit=${encodeURIComponent(limit)}&ops-limit=${encodeURIComponent(opsLimit)}`;
const CHANNEL_DETAIL_BY_ID = (channelId, fork, page, pageSize) =>
    `${joinUrl(API_PREFIX, 'channels', encodeHash(channelId))}?fork=${encodeURIComponent(fork)}&page=${encodeURIComponent(page)}&page-size=${encodeURIComponent(pageSize)}`;

const NOTE_SEARCH = (noteId, fork) =>
    `${joinUrl(API_PREFIX, 'notes', encodeHash(noteId))}?fork=${encodeURIComponent(fork)}`;

const TRANSACTIONS_STREAM_WITH_FORK = (fork) =>
    `${joinUrl(API_PREFIX, 'transactions/stream')}?fork=${encodeURIComponent(fork)}`;
const TRANSACTIONS_LIST = (page, pageSize, fork) =>
    `${joinUrl(API_PREFIX, 'transactions/list')}?page=${encodeURIComponent(page)}&page-size=${encodeURIComponent(pageSize)}&fork=${encodeURIComponent(fork)}`;

export const API = {
    HEALTH_ENDPOINT,
    FORK_CHOICE,
    CHANNELS_LIST,
    CHANNEL_DETAIL_BY_ID,
    NOTE_SEARCH,
    TRANSACTION_DETAIL_BY_HASH,
    TRANSACTIONS_STREAM,
    TRANSACTIONS_STREAM_WITH_FORK,
    TRANSACTIONS_LIST,
    BLOCK_DETAIL_BY_HASH,
    BLOCKS_STREAM,
    BLOCKS_LIST,
};

const BLOCK_DETAIL = (hash) => joinUrl(`${BASE_PATH}/blocks`, encodeHash(hash));
const TRANSACTION_DETAIL = (hash) => joinUrl(`${BASE_PATH}/transactions`, encodeHash(hash));
const CHANNEL_DETAIL = (channelId) => joinUrl(`${BASE_PATH}/channel`, encodeHash(channelId));
const NOTE_DETAIL = (noteId) => joinUrl(`${BASE_PATH}/notes`, encodeHash(noteId));

export const PAGE = {
    BLOCK_DETAIL,
    TRANSACTION_DETAIL,
    CHANNEL_DETAIL,
    NOTE_DETAIL,
};
