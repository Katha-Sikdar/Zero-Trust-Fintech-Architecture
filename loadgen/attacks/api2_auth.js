// OWASP API2:2023 Broken Authentication. Fires the forged/expired/confused
// tokens against a protected resource. A correct system blocks all of them.
import http from 'k6/http';
import { score, tag } from '../lib/scoring.js';
import { TOKENS, bearer, validToken } from '../lib/corpus.js';

const A = TOKENS.attacks;
const cases = [
  ['alg_none', A.alg_none],
  ['key_confusion', A.key_confusion],
  ['expired', A.expired],
  ['wrong_signature', A.wrong_signature],
  ['tampered', A.tampered],
];

export function api2Attack(base, alg, i) {
  const [name, token] = cases[i % cases.length];
  // target an admin-only or another-owner resource so a bypass is meaningful
  const res = http.get(`${base}/accounts/a000`,
    { headers: bearer(token), tags: tag('API2', 'attack', name) });
  score(res, 'API2', 'attack', name);
}

// benign counterpart: a valid user reading their own account
export function api2Benign(base, alg) {
  const res = http.get(`${base}/accounts/a001`,
    { headers: bearer(validToken('u001', alg)), tags: tag('API2', 'benign', 'valid_owner') });
  score(res, 'API2', 'benign', 'valid_owner');
}
