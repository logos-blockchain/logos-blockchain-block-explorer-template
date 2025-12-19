const API_PREFIX = '/api/v1';

const joinUrl = (...parts) => parts.join('/').replace(/\/{2,}/g, '/');
const encodeHash = (hash) => encodeURIComponent(String(hash));

const HEALTH_ENDPOINT = joinUrl(API_PREFIX, 'health/stream');

const TRANSACTION_DETAIL_BY_HASH = (hash) => joinUrl(API_PREFIX, 'transactions', encodeHash(hash));
const TRANSACTIONS_STREAM = joinUrl(API_PREFIX, 'transactions/stream');

const BLOCK_DETAIL_BY_HASH = (hash) => joinUrl(API_PREFIX, 'blocks', encodeHash(hash));
const BLOCKS_STREAM = joinUrl(API_PREFIX, 'blocks/stream');

export const API = {
    HEALTH_ENDPOINT,
    TRANSACTION_DETAIL_BY_HASH,
    TRANSACTIONS_STREAM,
    BLOCK_DETAIL_BY_HASH,
    BLOCKS_STREAM,
};

const BLOCK_DETAIL = (hash) => joinUrl('/blocks', encodeHash(hash));
const TRANSACTION_DETAIL = (hash) => joinUrl('/transactions', encodeHash(hash));

export const PAGE = {
    BLOCK_DETAIL,
    TRANSACTION_DETAIL,
};
