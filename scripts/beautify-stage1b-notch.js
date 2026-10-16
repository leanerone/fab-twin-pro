/* notch 从底部移到顶部（底部被 pod 门框遮挡），高光弧避开顶部中心 */
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..');
const files = [
  path.join(root, 'models/user/amat_metsput.svg'),
  path.join(root, 'backend/uploads/models/amat_metsput.svg'),
  path.join(root, 'backend/uploads/models/AMAT-METSPUT_v21_282af57e.svg'),
];
const glareOld = 'd="M140.5,755.5 A20.8,20.8 0 0 1 162,751.5"';
const glareNew = 'd="M138.5,757.5 A20.8,20.8 0 0 1 148.5,750.6"';
const notchOld = 'd="M151.6,747.8 L155,751.1 L158.4,747.8 Z"';
const notchNew = 'd="M150.8,747.5 L155,752.2 L159.2,747.5 Z"';
for (const f of files) {
  let s = fs.readFileSync(f, 'utf8');
  let n = 0;
  while (s.includes(glareOld)) { s = s.replace(glareOld, glareNew); n++; }
  while (s.includes(notchOld)) { s = s.replace(notchOld, notchNew); n++; }
  fs.writeFileSync(f, s);
  console.log(`${path.relative(root, f)}: ${n} paths moved`);
}
