/* 阶段1收尾：晶圆真实化
 * 1) defs 追加 waferShade(银蓝径向明暗罩) / edgeMetal(边缘金属高光) / slotMetal(片厚度纵向渐变)
 * 2) CSS 片槽规则 path->rect 适配
 * 3) L1~25/R1~25 path -> 圆角厚度 rect（id/组归属不变）
 * 4) Group1/2_CST_TOPVIEW 内追加 wafer-deco 装饰组（明暗罩+金属描边+高光弧+notch）
 * 三份文件同步，幂等（含 waferShade 则跳过 defs/deco 插入）
 */
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const files = [
  path.join(root, 'models/user/amat_metsput.svg'),
  path.join(root, 'backend/uploads/models/amat_metsput.svg'),
  path.join(root, 'backend/uploads/models/AMAT-METSPUT_v21_282af57e.svg'),
];

const newDefs = `  <radialGradient id="waferShade" cx="0.38" cy="0.32" r="0.78">
   <stop offset="0" stop-color="#ffffff" stop-opacity="0.4"/>
   <stop offset="0.45" stop-color="#dde8f6" stop-opacity="0.1"/>
   <stop offset="0.8" stop-color="#8395b8" stop-opacity="0.16"/>
   <stop offset="1" stop-color="#16233a" stop-opacity="0.5"/>
  </radialGradient>
  <linearGradient id="edgeMetal" x1="0" y1="0" x2="1" y2="1">
   <stop offset="0" stop-color="#ffffff"/>
   <stop offset="0.35" stop-color="#a9b4c4"/>
   <stop offset="0.6" stop-color="#eef3f9"/>
   <stop offset="1" stop-color="#59647a"/>
  </linearGradient>
  <linearGradient id="slotMetal" x1="0" y1="0" x2="0" y2="1">
   <stop offset="0" stop-color="#f2f6fb"/>
   <stop offset="0.45" stop-color="#c3ccd9"/>
   <stop offset="0.8" stop-color="#79828f"/>
   <stop offset="1" stop-color="#3f4650"/>
  </linearGradient>
</defs>`;

const cssOld = /#Group1_CST path\[id\^="L"\], #Group2_CST path\[id\^="R"\] \{ stroke: url\(#slotGrad\); stroke-width: 0\.75; stroke-linecap: round; \}/;
const cssNew = `#Group1_CST rect[id^="L"], #Group2_CST rect[id^="R"] { fill: url(#slotMetal); stroke: #10141a; stroke-width: 0.18; }`;

/* 俯视晶圆 CSS 限定到 LLA/LLB id，避免覆盖 wafer-deco 装饰 circle 的 inline fill/stroke */
const cssTopOld = `#Group1_CST_TOPVIEW circle, #Group2_CST_TOPVIEW circle { fill: url(#waferPattern); stroke: #2f3a4d; stroke-width: 1.2; }`;
const cssTopNew = `#Group1_CST_TOPVIEW circle[id^="LLA"], #Group2_CST_TOPVIEW circle[id^="LLB"] { fill: url(#waferPattern); stroke: #2f3a4d; stroke-width: 1.2; }`;

const slotRe = /<path d="m326,([\d.]+)l20,0" fill="[^"]*" id="([LR])(\d+)" opacity="0\.95" stroke="#000000" stroke-linecap="round" stroke-width="0\.5"(?: transform="[^"]*")?\/>/g;

const deco = (gid) => `
   <g class="wafer-deco" pointer-events="none">
    <circle cx="155" cy="771" r="23" fill="url(#waferShade)"/>
    <circle cx="155" cy="771" r="22.1" fill="none" stroke="url(#edgeMetal)" stroke-width="1.5"/>
    <path d="M140.5,755.5 A20.8,20.8 0 0 1 162,751.5" fill="none" stroke="#ffffff" stroke-opacity="0.8" stroke-width="1.7" stroke-linecap="round"/>
    <path d="M151.6,794.2 L155,790.9 L158.4,794.2 Z" fill="#0d1117"/>
   </g>`;

for (const f of files) {
  let s = fs.readFileSync(f, 'utf8');
  const rel = path.relative(root, f);
  let nDefs = 0, nCss = 0, nDeco = 0;

  if (!s.includes('id="waferShade"')) {
    s = s.replace('</defs>', newDefs);
    nDefs = 1;
  }

  if (cssOld.test(s)) { s = s.replace(cssOld, cssNew); nCss = 1; }
  if (s.includes(cssTopOld)) { s = s.replace(cssTopOld, cssTopNew); nCss = 1; }

  let nSlot = 0;
  s = s.replace(slotRe, (m, y, g) => {
    nSlot++;
    const yy = (parseFloat(y) - 0.41).toFixed(2);
    return `<rect x="325.8" y="${yy}" width="20.4" height="0.82" rx="0.41" id="${g}${m.match(/id="([LR]\d+)"/)[1].slice(1)}" fill="url(#slotMetal)" stroke="#10141a" stroke-width="0.18"/>`;
  });

  if (!s.includes('class="wafer-deco"')) {
    for (const cid of ['LLA1', 'LLB1']) {
      const anchor = `<circle cx="155" cy="771" fill="#000000" id="${cid}" r="23" stroke="#000000"/>`;
      if (s.includes(anchor)) { s = s.replace(anchor, anchor + deco(cid)); nDeco++; }
    }
  }

  fs.writeFileSync(f, s);
  console.log(`${rel}: defs=${nDefs} css=${nCss} slots=${nSlot} deco=${nDeco}`);
}
