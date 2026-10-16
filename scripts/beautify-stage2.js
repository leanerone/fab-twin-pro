// Stage2: 腔室金属化（不锈钢质感）
// - 4 个 PVD 腔 CH_1~4 + CH_A~F：chSteel 径向渐变填充 + 明暗罩 + 顶部高光弧 + 底部投影弧 + 腔盖法兰圈(+螺栓)
// - 机械臂 ARM_1/ARM_2：关节圆/Chuck/转台改 armSteel 渐变，叉臂 blade 改 armBlade 纵向渐变，加关节圆盘装饰
// 红线：动画引用的 id 全部不动（CH_* 仅作 snap 定位点，无填充动画；ARM_* 整组旋转，装饰挂组内跟随）
// 幂等：defs/CSS 按 id 查重，装饰按 data-for 查重。
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const files = [
  'models/user/amat_metsput.svg',
  'backend/uploads/models/amat_metsput.svg',
  'backend/uploads/models/AMAT-METSPUT_v21_282af57e.svg',
];

/* ---------- defs / CSS ---------- */
const DEFS = `  <!-- === 腔室金属化（阶段2） === -->
  <!-- 不锈钢主体：左上光源径向渐变 -->
  <radialGradient id="chSteel" cx="0.35" cy="0.3" r="0.85">
   <stop offset="0" stop-color="#fdfeff"/>
   <stop offset="0.4" stop-color="#d3dbe6"/>
   <stop offset="0.72" stop-color="#98a4b6"/>
   <stop offset="1" stop-color="#5b6679"/>
  </radialGradient>
  <!-- 腔体明暗罩：边缘压暗出球面感 -->
  <radialGradient id="chShade" cx="0.5" cy="0.5" r="0.5">
   <stop offset="0.62" stop-color="#10151d" stop-opacity="0"/>
   <stop offset="0.85" stop-color="#10151d" stop-opacity="0.12"/>
   <stop offset="1" stop-color="#10151d" stop-opacity="0.38"/>
  </radialGradient>
  <!-- 法兰圈金属 -->
  <linearGradient id="chFlange" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#f4f7fb"/>
   <stop offset="0.5" stop-color="#aeb9c8"/>
   <stop offset="1" stop-color="#646e7e"/>
  </linearGradient>
  <!-- 机械臂关节金属 -->
  <radialGradient id="armSteel" cx="0.38" cy="0.32" r="0.85">
   <stop offset="0" stop-color="#f8fafc"/>
   <stop offset="0.45" stop-color="#cfd8e4"/>
   <stop offset="0.78" stop-color="#8e9baf"/>
   <stop offset="1" stop-color="#4d5666"/>
  </radialGradient>
  <!-- 机械臂叉臂纵向金属 -->
  <linearGradient id="armBlade" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#eef2f8"/>
   <stop offset="0.55" stop-color="#b9c3d2"/>
   <stop offset="1" stop-color="#788294"/>
  </linearGradient>
`;

const CSS = `
            /* === 腔室金属化（阶段2） === */
            #CH_1, #CH_2, #CH_3, #CH_4, #CH_E, #CH_F, #CH_A, #CH_B, #CH_C, #CH_D { fill: url(#chSteel); }
            #CH_C, #CH_D { stroke: #3a4250; }
            #svg_36, #svg_38, #Wafer_Chuck1, #Wafer_Chuck2, #svg_48 { fill: url(#armSteel); }
            #svg_39, #svg_51 { fill: url(#armBlade); }
`;

/* ---------- 装饰生成 ---------- */
const f1 = (n) => Math.round(n * 10) / 10;

// 顶部高光弧（屏坐标扫掠 160°→20°，过顶部）
function arcTop(cx, cy, rx, ry, sw, color, op) {
  const y = f1(cy - 0.342 * ry);
  return `<path d="M${f1(cx - 0.9397 * rx)},${y} A${f1(rx)},${f1(ry)} 0 0 1 ${f1(cx + 0.9397 * rx)},${y}" fill="none" stroke="${color}" stroke-opacity="${op}" stroke-width="${sw}" stroke-linecap="round"/>`;
}
// 底部投影弧（过底部）
function arcBottom(cx, cy, rx, ry, sw, color, op) {
  const y = f1(cy + 0.342 * ry);
  return `<path d="M${f1(cx - 0.9397 * rx)},${y} A${f1(rx)},${f1(ry)} 0 0 0 ${f1(cx + 0.9397 * rx)},${y}" fill="none" stroke="${color}" stroke-opacity="${op}" stroke-width="${sw}" stroke-linecap="round"/>`;
}

function roundChamberDeco(cx, cy, r, bolts) {
  const rf = r + 3.4;
  const p = [];
  p.push(`<circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#chShade)"/>`);
  p.push(arcTop(cx, cy, r - 7, r - 7, 2.4, '#ffffff', 0.8));
  p.push(arcBottom(cx, cy, r - 5, r - 5, 3, '#141a24', 0.28));
  p.push(`<circle cx="${cx}" cy="${cy}" r="${f1(rf)}" fill="none" stroke="url(#chFlange)" stroke-width="4.6"/>`);
  p.push(`<circle cx="${cx}" cy="${cy}" r="${f1(r + 0.9)}" fill="none" stroke="#454545" stroke-width="1"/>`);
  for (let k = 0; k < bolts; k++) {
    const a = (Math.PI * 2 * k) / bolts + Math.PI / bolts;
    p.push(`<circle cx="${f1(cx + rf * Math.cos(a))}" cy="${f1(cy + rf * Math.sin(a))}" r="1.1" fill="#3a4250"/>`);
  }
  return p.join('\n   ');
}

function ellipseChamberDeco(cx, cy, rx, ry) {
  const p = [];
  p.push(`<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="url(#chShade)"/>`);
  p.push(arcTop(cx, cy, rx - 5, ry - 5, 2, '#ffffff', 0.8));
  p.push(arcBottom(cx, cy, rx - 4, ry - 4, 2.6, '#141a24', 0.28));
  p.push(`<ellipse cx="${cx}" cy="${cy}" rx="${rx + 3}" ry="${ry + 3}" fill="none" stroke="url(#chFlange)" stroke-width="3.6"/>`);
  p.push(`<ellipse cx="${cx}" cy="${cy}" rx="${f1(rx + 0.8)}" ry="${f1(ry + 0.8)}" fill="none" stroke="#454545" stroke-width="0.9"/>`);
  return p.join('\n   ');
}

function rectChamberDeco(x, y, w, h) {
  const p = [];
  p.push(`<rect x="${x}" y="${y}" width="${w}" height="${h}" fill="url(#chShade)"/>`);
  p.push(`<rect x="${x - 4}" y="${y - 4}" width="${w + 8}" height="${h + 8}" rx="7" fill="none" stroke="url(#chFlange)" stroke-width="4"/>`);
  p.push(`<path d="M${x + 9},${y + 7} H${x + w - 9}" fill="none" stroke="#ffffff" stroke-opacity="0.8" stroke-width="2" stroke-linecap="round"/>`);
  p.push(`<path d="M${x + 9},${y + h - 7} H${x + w - 9}" fill="none" stroke="#141a24" stroke-opacity="0.28" stroke-width="3" stroke-linecap="round"/>`);
  return p.join('\n   ');
}

// 机械臂关节圆盘：金属环 + 中心轴毂（ARM_2：肩关节 svg_36 / Chuck2 / svg_38）
const ARM2_DECO = [
  arcTop(360, 278, 22, 22, 2, '#ffffff', 0.7),
  `<circle cx="360" cy="278" r="10.5" fill="none" stroke="url(#chFlange)" stroke-width="2.6"/>`,
  `<circle cx="360" cy="278" r="3.2" fill="#39414e"/>`,
  `<circle cx="359" cy="213.5" r="13" fill="none" stroke="url(#chFlange)" stroke-width="2.6"/>`,
  `<circle cx="359" cy="213.5" r="3.2" fill="#39414e"/>`,
  `<circle cx="360.5" cy="341.5" r="13" fill="none" stroke="url(#chFlange)" stroke-width="2.6"/>`,
  `<circle cx="360.5" cy="341.5" r="3.2" fill="#39414e"/>`,
].join('\n   ');

// ARM_1：Chuck1 关节盘 + 转台 svg_48 椭圆环
const ARM1_DECO = [
  `<circle cx="364.36" cy="463.6" r="13" fill="none" stroke="url(#chFlange)" stroke-width="2.6"/>`,
  `<circle cx="364.36" cy="463.6" r="3.2" fill="#39414e"/>`,
  `<ellipse cx="363.58" cy="539.98" rx="20" ry="13" fill="none" stroke="url(#chFlange)" stroke-width="2.6"/>`,
  `<circle cx="363.58" cy="539.98" r="3.2" fill="#39414e"/>`,
].join('\n   ');

/* ---------- 插入工具 ---------- */
function insertAfterShape(s, id, decoInner) {
  if (s.includes(`data-for="${id}"`)) return { s, done: false };
  const re = new RegExp(`(<(?:circle|ellipse|rect)\\b[^>]*id="${id}"[^>]*/>)`);
  const m = s.match(re);
  if (!m) return { s, missing: true };
  const tag = m[1];
  const tm = tag.match(/transform="([^"]*)"/);
  // 形状自带变换（如 CH_E/F 的缩放平移）→ 装饰组复制同一变换，保证坐标一致
  const tattr = tm && tm[1] !== 'matrix(1 0 0 1 0 0)' ? ` transform="${tm[1]}"` : '';
  const deco = `\n   <g class="ch-deco" data-for="${id}" pointer-events="none"${tattr}>\n   ${decoInner}\n   </g>`;
  return { s: s.replace(re, tag + deco), done: true };
}

function insertArmDeco(s, armId, anchorId, decoInner) {
  if (s.includes(`data-for="${armId}"`)) return { s, done: false };
  const re = new RegExp(`(<path[^>]*id="${anchorId}"[^>]*/>)`);
  const m = s.match(re);
  if (!m) return { s, missing: true };
  const deco = `\n    <g class="arm-deco" data-for="${armId}" pointer-events="none">\n   ${decoInner}\n    </g>`;
  return { s: s.replace(re, m[1] + deco), done: true };
}

/* ---------- 执行 ---------- */
const roundChambers = [
  ['CH_2', 188, 190, 46, 8],
  ['CH_3', 530, 190, 46, 8],
  ['CH_1', 188, 350, 46, 8],
  ['CH_4', 530, 350, 46, 8],
  ['CH_E', 244.53, 634, 34, 6],
  ['CH_F', 498, 635, 34, 6],
];
const ellChambers = [
  ['CH_A', 298, 470, 42, 26],
  ['CH_B', 422, 470, 42, 26],
];
const rectChambers = [
  ['CH_C', 132.25, 472, 83, 102],
  ['CH_D', 511.75, 471.75, 83, 102],
];

for (const rel of files) {
  const f = path.join(root, rel);
  let s = fs.readFileSync(f, 'utf8');
  const log = [];

  if (!s.includes('id="chSteel"')) {
    if (!s.includes('</defs>')) { console.log(rel, 'ERROR: no </defs>'); process.exit(1); }
    s = s.replace('</defs>', DEFS + '</defs>');
    log.push('defs');
  }
  if (!s.includes('#CH_1, #CH_2')) {
    s = s.replace('</style>', CSS + '</style>');
    log.push('css');
  }

  let n = 0;
  for (const [id, cx, cy, r, b] of roundChambers) {
    const r0 = insertAfterShape(s, id, roundChamberDeco(cx, cy, r, b));
    if (r0.missing) { console.log(rel, 'ERROR: missing', id); process.exit(1); }
    s = r0.s; if (r0.done) n++;
  }
  for (const [id, cx, cy, rx, ry] of ellChambers) {
    const r0 = insertAfterShape(s, id, ellipseChamberDeco(cx, cy, rx, ry));
    if (r0.missing) { console.log(rel, 'ERROR: missing', id); process.exit(1); }
    s = r0.s; if (r0.done) n++;
  }
  for (const [id, x, y, w, h] of rectChambers) {
    const r0 = insertAfterShape(s, id, rectChamberDeco(x, y, w, h));
    if (r0.missing) { console.log(rel, 'ERROR: missing', id); process.exit(1); }
    s = r0.s; if (r0.done) n++;
  }
  const a2 = insertArmDeco(s, 'ARM_2', 'svg_41', ARM2_DECO);
  if (a2.missing) { console.log(rel, 'ERROR: missing ARM_2 anchor'); process.exit(1); }
  s = a2.s; if (a2.done) n++;
  const a1 = insertArmDeco(s, 'ARM_1', 'svg_53', ARM1_DECO);
  if (a1.missing) { console.log(rel, 'ERROR: missing ARM_1 anchor'); process.exit(1); }
  s = a1.s; if (a1.done) n++;

  fs.writeFileSync(f, s);
  console.log(rel, log.join('+') || 'defs/css ok', 'decoAdded=' + n);
}
