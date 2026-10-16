// Stage3: 整体光影收尾
// - SMIF 外壳金属质感（外框/内框渐变，SMIF_1 + svg_123 即 SMIF_2 躯体）
// - 部件落地阴影：PVD 腔组(含基座)/CH_A~F/BUFFER/LLA/LLB/SMIF 豆荚，groundShadow 径向渐隐
// - 腔室标签徽章化：PVD1~4 + A~F 标签加深色金属徽章底，文字改浅色
// - 附带整机光影：大转盘 svg_35 / BUFFER 八边形 / 外框 svg_1 微渐变
// 红线：动画 id 不动；阴影/徽章为独立装饰元素，data-for 统一 "s3:" 前缀避免与阶段2查重冲突
// 幂等：defs/CSS/装饰均查重跳过。
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const files = [
  'models/user/amat_metsput.svg',
  'backend/uploads/models/amat_metsput.svg',
  'backend/uploads/models/AMAT-METSPUT_v21_282af57e.svg',
];

const DEFS = `  <!-- === 整体光影收尾（阶段3） === -->
  <!-- 落地阴影：径向渐隐 -->
  <radialGradient id="groundShadow" cx="0.5" cy="0.5" r="0.5">
   <stop offset="0" stop-color="#0b0f16" stop-opacity="0.26"/>
   <stop offset="0.65" stop-color="#0b0f16" stop-opacity="0.1"/>
   <stop offset="1" stop-color="#0b0f16" stop-opacity="0"/>
  </radialGradient>
  <!-- SMIF 外壳金属 -->
  <linearGradient id="smifShell" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#f2f5f9"/>
   <stop offset="0.5" stop-color="#c7cfdb"/>
   <stop offset="1" stop-color="#97a2b1"/>
  </linearGradient>
  <linearGradient id="smifInner" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#ffffff"/>
   <stop offset="0.6" stop-color="#dde3ea"/>
   <stop offset="1" stop-color="#b4bdc9"/>
  </linearGradient>
  <!-- 标签徽章深色金属 -->
  <linearGradient id="badgeMetal" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#465062"/>
   <stop offset="0.5" stop-color="#2c3542"/>
   <stop offset="1" stop-color="#1a212c"/>
  </linearGradient>
  <!-- 转盘/缓冲台面板微渐变 -->
  <radialGradient id="deckPlate" cx="0.5" cy="0.42" r="0.75">
   <stop offset="0" stop-color="#ffffff"/>
   <stop offset="0.75" stop-color="#f2f5f9"/>
   <stop offset="1" stop-color="#dde3ec"/>
  </radialGradient>
  <linearGradient id="framePlate" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#ffffff"/>
   <stop offset="1" stop-color="#edf0f5"/>
  </linearGradient>
`;

const CSS = `
            /* === 整体光影收尾（阶段3） === */
            #smif1OuterFrame, #svg_124 { fill: url(#smifShell); }
            #smif1InnerFrame, #svg_125 { fill: url(#smifInner); }
            #svg_35, #BUFFER { fill: url(#deckPlate); }
            #svg_1 { fill: url(#framePlate); }
            #svg_13, #svg_19, #svg_25, #svg_31, #svg_59, #svg_60, #svg_68, #svg_65, #svg_69, #svg_70 { fill: #eef3fa; }
`;

const SH = (key, cx, cy, rx, ry, extra = '') =>
  `<ellipse class="part-shadow" data-for="s3:${key}" cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="url(#groundShadow)"${extra}/>`;

// 落在组内第一个子元素位置（组变换由父级继承）
const groupShadows = [
  ['svg_10', SH('svg_10', 188, 196, 97, 63)],
  ['svg_16', SH('svg_16', 530, 196, 97, 63)],
  ['svg_22', SH('svg_22', 188, 356, 97, 63)],
  ['svg_28', SH('svg_28', 530, 356, 97, 63)],
  ['SMIF_1', SH('SMIF_1', 335, 862, 42, 9)],
  ['svg_123', SH('svg_123', 335, 862, 42, 9)],
];

// 落在指定形状元素之前（CH_E/F 复制源形状的变换）
const TF_E = ' transform="matrix(1 0 0 1 0 0) matrix(1.03114 0 0 1 -21.3287 -0.5)"';
const TF_F = ' transform="matrix(1.03114 0 0 1 -21.3287 -0.5)"';
const shapeShadows = [
  ['CH_A', 'ellipse', SH('CH_A', 298, 474, 48, 31)],
  ['CH_B', 'ellipse', SH('CH_B', 422, 474, 48, 31)],
  ['CH_C', 'rect', SH('CH_C', 173.75, 576, 47, 11)],
  ['CH_D', 'rect', SH('CH_D', 553.25, 575.75, 47, 11)],
  ['CH_E', 'circle', SH('CH_E', 244.53, 638, 40, 36, TF_E)],
  ['CH_F', 'circle', SH('CH_F', 498, 639, 40, 36, TF_F)],
  ['BUFFER', 'path', SH('BUFFER', 363.5, 650, 152, 13)],
  ['LLA', 'path', SH('LLA', 326.6, 649, 32, 7)],
  ['LLB', 'path', SH('LLB', 418.4, 649, 32, 7)],
];

// 标签徽章（w=徽章宽；E/F 复制文本变换）
const badges = [
  ['svg_13', 136, 240, 50],
  ['svg_19', 579, 241, 50],
  ['svg_25', 143, 308, 50],
  ['svg_31', 565, 300, 50],
  ['svg_59', 250, 482, 24],
  ['svg_60', 470, 480, 24],
  ['svg_68', 162, 510, 24],
  ['svg_65', 556, 507, 24],
  ['svg_69', 197.45, 650, 24, TF_E],
  ['svg_70', 546.46, 649.5, 24, TF_E],
];

function badgeRect(id, x, y, w, t = '') {
  return `<rect class="label-badge" data-for="s3:${id}" x="${x - w / 2}" y="${y - 15.5}" width="${w}" height="20" rx="10" fill="url(#badgeMetal)" stroke="#93a3ba" stroke-width="0.7" opacity="0.96"${t}/>`;
}

function insertAfterGroupOpen(s, gid, markup, key) {
  if (s.includes(`data-for="s3:${key}"`)) return { s, done: false };
  const re = new RegExp(`(<g id="${gid}"[^>]*>)`);
  const m = s.match(re);
  if (!m) return { s, missing: gid };
  return { s: s.replace(re, m[1] + '\n   ' + markup), done: true };
}

function insertBeforeShape(s, id, tag, markup, key) {
  if (s.includes(`data-for="s3:${key}"`)) return { s, done: false };
  const re = new RegExp(`(<${tag}\\b[^>]*id="${id}"[^>]*>)`);
  const m = s.match(re);
  if (!m) return { s, missing: id };
  return { s: s.replace(re, markup + '\n  ' + m[1]), done: true };
}

function insertBeforeText(s, id, markup) {
  if (s.includes(`data-for="s3:${id}"`)) return { s, done: false };
  const re = new RegExp(`(<text\\b[^>]*id="${id}"[^>]*>)`);
  const m = s.match(re);
  if (!m) return { s, missing: id };
  return { s: s.replace(re, markup + '\n   ' + m[1]), done: true };
}

for (const rel of files) {
  const f = path.join(root, rel);
  let s = fs.readFileSync(f, 'utf8');
  const log = [];
  let n = 0;

  if (!s.includes('id="groundShadow"')) {
    s = s.replace('</defs>', DEFS + '</defs>');
    log.push('defs');
  }
  if (!s.includes('#smif1OuterFrame')) {
    s = s.replace('</style>', CSS + '</style>');
    log.push('css');
  }

  for (const [gid, markup] of groupShadows) {
    const r = insertAfterGroupOpen(s, gid, markup, gid);
    if (r.missing) { console.log(rel, 'ERROR: missing group', r.missing); process.exit(1); }
    s = r.s; if (r.done) n++;
  }
  for (const [id, tag, markup] of shapeShadows) {
    const r = insertBeforeShape(s, id, tag, markup, id);
    if (r.missing) { console.log(rel, 'ERROR: missing shape', r.missing); process.exit(1); }
    s = r.s; if (r.done) n++;
  }
  for (const [id, x, y, w, t] of badges) {
    const r = insertBeforeText(s, id, badgeRect(id, x, y, w, t));
    if (r.missing) { console.log(rel, 'ERROR: missing label', r.missing); process.exit(1); }
    s = r.s; if (r.done) n++;
  }

  fs.writeFileSync(f, s);
  console.log(rel, log.join('+') || 'defs/css ok', 'added=' + n);
}
