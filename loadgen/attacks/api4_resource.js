// OWASP API4:2023 Unrestricted Resource Consumption. A single client bursts
// requests far above its fair share. A correct system (gateway rate limit)
// sheds the excess with 429. "Blocked" here = 429/503. This is also the control
// whose actuator the RQ3 model tunes, so its block rate is expected to rise as
// S6 tightens the limit.
import http from 'k6/http';
import { score, tag } from '../lib/scoring.js';
import { bearer, validToken } from '../lib/corpus.js';

export function api4Attack(base, alg) {
  // authenticated but abusive: hammer an expensive endpoint
  const res = http.get(`${base}/accounts/a001/transactions`,
    { headers: bearer(validToken('u001', alg)), tags: tag('API4', 'attack', 'flood') });
  // for API4, a 2xx means the flood was served (not blocked); 429/503 = blocked
  score(res, 'API4', 'attack', 'flood');
}

export function api4Benign(base, alg) {
  const res = http.get(`${base}/accounts/a004`,
    { headers: bearer(validToken('u004', alg)), tags: tag('API4', 'benign', 'normal_rate') });
  score(res, 'API4', 'benign', 'normal_rate');
}
