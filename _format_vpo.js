const fs = require('fs');
const path = require('path');

const BASE = 'C:/Users/A/AppData/Roaming/TRAE SOLO CN/ModularData/ai-agent/work-mode-projects/6a558d0e1709fecd225c0cc2/fab-twin-pro';
const src = path.join(BASE, 'VPO_2D.HTML');
const dst = path.join(BASE, 'VPO2D.HTML');

// Copy VPO_2D.HTML to VPO2D.HTML
const content = fs.readFileSync(src, 'utf8');
fs.writeFileSync(dst, content, 'utf8');

// Format the file
const { execSync } = require('child_process');
try {
  execSync(`npx.cmd js-beautify --type html --indent-size 2 --wrap-line-length 120 --preserve-newlines -r "${dst}"`, {
    encoding: 'utf8',
    cwd: BASE,
    timeout: 60000
  });
  console.log('Formatted VPO2D.HTML');
} catch (e) {
  console.log('Format failed:', e.message.substring(0, 200));
}
