// Stage1c: move .wafer-deco group from after LLA1/LLB1 to after LLA25/LLB25 (z-order fix).
// Deco was painted over by LLA2..25 (24 waferPattern circles), washing out the notch.
// Safe: animation only references the parent groups, never individual LLA/LLB circles.
// Idempotent: skips when deco is not adjacent to the first circle.
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const files = [
  'models/user/amat_metsput.svg',
  'backend/uploads/models/amat_metsput.svg',
  'backend/uploads/models/AMAT-METSPUT_v21_282af57e.svg',
];

for (const rel of files) {
  const f = path.join(root, rel);
  let s = fs.readFileSync(f, 'utf8');
  let moved = 0;
  for (const pfx of ['LLA', 'LLB']) {
    const re1 = new RegExp(`(<circle[^>]*id="${pfx}1"[^>]*/>)(\\s*<g class="wafer-deco"[\\s\\S]*?</g>)`);
    let deco = null;
    s = s.replace(re1, (m, c1, d) => { deco = d; return c1; });
    if (!deco) continue; // already moved or absent
    const re25 = new RegExp(`(<circle[^>]*id="${pfx}25"[^>]*/>)`);
    if (!re25.test(s)) { console.log(f, pfx, 'ERROR: last circle not found, deco lost!'); process.exit(1); }
    s = s.replace(re25, (m, c25) => c25 + deco);
    moved++;
  }
  fs.writeFileSync(f, s);
  console.log(rel, 'moved=' + moved);
}
