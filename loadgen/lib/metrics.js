// Pre-declared per-risk confusion-matrix counters and latency trends. Declaring
// them at init time lets k6's handleSummary emit an exact matrix per risk with
// no raw-sample post-processing.
import { Counter, Trend } from 'k6/metrics';

export const RISKS = ['API1', 'API2', 'API4', 'API5', 'API8', 'A10'];
export const CELLS = ['tp', 'fp', 'tn', 'fn'];

const cm = {};
const lat = {};
for (const r of RISKS) {
  cm[r] = {};
  for (const c of CELLS) cm[r][c] = new Counter(`cm_${r}_${c}`);
  lat[r] = new Trend(`lat_${r}`, true);
}
export const CM = cm;
export const LAT = lat;
