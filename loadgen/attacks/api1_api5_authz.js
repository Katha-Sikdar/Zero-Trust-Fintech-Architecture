// OWASP API1 (BOLA) and API5 (BFLA). A validly-authenticated customer tries to
// reach another user's object and an admin-only function. A correct system
// authenticates them fine but DENIES the action.
import http from 'k6/http';
import { score, tag } from '../lib/scoring.js';
import { bearer, validToken } from '../lib/corpus.js';

export function bolaAttack(base, alg) {
  // u001 (valid token) reads u002's account -> object-level violation
  const res = http.get(`${base}/accounts/a002`,
    { headers: bearer(validToken('u001', alg)), tags: tag('API1', 'attack', 'bola_cross_owner') });
  score(res, 'API1', 'attack', 'bola_cross_owner');
}

export function bflaAttack(base, alg) {
  // customer u001 invokes an admin-only function -> function-level violation
  const res = http.del(`${base}/admin/users/u005`, null,
    { headers: bearer(validToken('u001', alg)), tags: tag('API5', 'attack', 'bfla_admin_route') });
  score(res, 'API5', 'attack', 'bfla_admin_route');
}

export function authzBenign(base, alg) {
  // admin legitimately reading any account, and owner reading own transactions
  const r1 = http.get(`${base}/accounts/a050`,
    { headers: bearer(validToken('u000', alg)), tags: tag('API1', 'benign', 'admin_ok') });
  score(r1, 'API1', 'benign', 'admin_ok');
  const r2 = http.get(`${base}/accounts/a003/transactions`,
    { headers: bearer(validToken('u003', alg)), tags: tag('API1', 'benign', 'owner_ok') });
  score(r2, 'API1', 'benign', 'owner_ok');
}
