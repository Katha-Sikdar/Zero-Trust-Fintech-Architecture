// Scoring: map each response to a confusion-matrix cell and record latency.
//   benign -> 2xx  = tn (correctly allowed);  non-2xx = fp (false positive)
//   attack -> 2xx  = fn (BYPASS!);            non-2xx = tp (correctly blocked)
import { check } from 'k6';
import { CM, LAT } from './metrics.js';

export function tag(risk, truth, name) { return { risk, truth, name }; }

export function score(res, risk, truth, name) {
  const is2xx = res.status >= 200 && res.status < 300;
  const cell = truth === 'benign' ? (is2xx ? 'tn' : 'fp') : (is2xx ? 'fn' : 'tp');
  CM[risk][cell].add(1);
  LAT[risk].add(res.timings.duration);
  check(res, { [`${risk}:${name} correct`]: () => (truth === 'benign' ? is2xx : !is2xx) },
        { risk, truth });
  return cell;
}
