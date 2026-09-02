// OWASP API8:2023 Security Misconfiguration. Probes for weakened transport /
// policy posture. In PERMISSIVE mesh mode a plaintext or unauthenticated call
// that should be refused may be served. "Blocked" = the request is refused.
import http from 'k6/http';
import { score, tag } from '../lib/scoring.js';
import { bearer, validToken } from '../lib/corpus.js';

export function api8Attack(base, alg) {
  // No Authorization header at all against a protected resource: only a
  // correctly-configured STRICT posture rejects it.
  const res = http.get(`${base}/accounts/a000`,
    { tags: tag('API8', 'attack', 'no_auth_header') });
  score(res, 'API8', 'attack', 'no_auth_header');
}

export function api8Benign(base, alg) {
  const res = http.get(`${base}/accounts/a006`,
    { headers: bearer(validToken('u006', alg)), tags: tag('API8', 'benign', 'proper_tls_auth') });
  score(res, 'API8', 'benign', 'proper_tls_auth');
}
