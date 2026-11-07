// Regenerates desktop/tool_forms.json from the TOOLS array in frontend/tools.js so the Qt client
// shows exactly the same tool forms as the web UI.  Usage: node desktop/sync_tool_forms.mjs
import { readFileSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const source = readFileSync(join(root, 'frontend', 'tools.js'), 'utf8');
const start = source.indexOf('const TOOLS = [');
const end = source.indexOf('\n  ];', start);
if (start < 0 || end < 0) throw new Error('TOOLS array not found in frontend/tools.js');
const literal = source.slice(start + 'const TOOLS = '.length, end + '\n  ]'.length);
const tools = new Function(`"use strict"; return (${literal});`)();
writeFileSync(join(root, 'desktop', 'tool_forms.json'), `${JSON.stringify(tools, null, 2)}\n`, 'utf8');
console.log(`tool_forms.json: ${tools.length} groups, ${tools.reduce((n, t) => n + t.forms.length, 0)} forms`);
