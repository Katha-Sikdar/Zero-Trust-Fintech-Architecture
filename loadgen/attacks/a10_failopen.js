// OWASP Top 10:2025 A10 Mishandling of Exceptional Conditions. The core RQ5
// probe. Under load past lambda*, the ext_authz path may time out; if Envoy is
// failure_mode_allow=true it admits the request WITHOUT authorization. This
// sends a request that MUST be denied (a BOLA attempt); any 2xx here past the
// elbow is direct evidence of a load-induced enforcement bypass.
import http from 'k6/http';
import { score, tag } from '../lib/scoring.js';
import { bearer, validToken } from '../lib/corpus.js';

export function a10Probe(base, alg) {
  // valid customer token, but reaching for a foreign object: correct outcome is
  // 403 at ALL load levels. A 2xx is a fail-open event.
  const res = http.get(`${base}/accounts/a077`,
    { headers: bearer(validToken('u001', alg)), tags: tag('A10', 'attack', 'failopen_probe') });
  score(res, 'A10', 'attack', 'failopen_probe');
}
