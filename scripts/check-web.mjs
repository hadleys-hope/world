/** No npm install: parse application modules with Node and verify local imports. */
import { readdirSync, readFileSync, existsSync } from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
let checked = 0;
function walk(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const file = join(dir, entry.name);
    if (entry.isDirectory()) { walk(file); continue; }
    if (!file.endsWith('.js')) continue;
    const result = spawnSync(process.execPath, ['--check', file], { encoding: 'utf8' });
    if (result.status !== 0) throw new Error(result.stderr);
    const code = readFileSync(file, 'utf8');
    for (const match of code.matchAll(/\bfrom\s+['"]([^'"]+)['"]/g)) {
      const name = match[1];
      const target = name.startsWith('.') ? resolve(dirname(file), name)
        : name === 'three' ? join(root, 'vendor/three/build/three.module.js')
        : name.startsWith('three/addons/') ? join(root, 'vendor/three/examples/jsm', name.slice(13)) : null;
      if (!target || !existsSync(target)) throw new Error(`${file}: unresolved import ${name}`);
    }
    checked++;
  }
}
walk(join(root, 'web/static/js'));
console.log(`Parsed ${checked} JS files; all local module imports resolve.`);
