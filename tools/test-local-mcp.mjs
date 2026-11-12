import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { copyFileSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { ROOT, SERVERS, buildConfig, localEnvironment, readManifest, validateInstallation } from './local-mcp.mjs';
import { verifyInstallation, verifyServer } from './verify-mcp.mjs';

const manifest = readManifest();

function fixtureRoot(t) {
  const parent = path.join(ROOT, '_tmp', 'temp');
  mkdirSync(parent, { recursive: true });
  const root = mkdtempSync(path.join(parent, 'mcp-fixture-'));
  t.after(() => rmSync(root, { recursive: true }));
  return root;
}

function protocolFixture(tool) {
  return {
    command: process.execPath,
    args: ['-e', `
      const tool = ${JSON.stringify(tool)};
      require('node:readline').createInterface({ input: process.stdin }).on('line', line => {
        const request = JSON.parse(line);
        if (request.id === undefined) return;
        const result = request.method === 'initialize'
          ? { protocolVersion: '2025-11-25', capabilities: { tools: {} } }
          : request.params.cursor
            ? { tools: [{ ...tool, name: 'second' }] }
            : { tools: [tool], nextCursor: 'page-2' };
        console.log(JSON.stringify({ jsonrpc: '2.0', id: request.id, result }));
      });
    `],
    cwd: ROOT,
    env: { ...localEnvironment(ROOT), PATH: process.env.PATH || '' },
  };
}

test('all five pinned tools use project-local runtime, scripts and state', () => {
  const config = buildConfig(ROOT, manifest);
  assert.equal(Object.keys(config.servers).length, 5);
  for (const [name, entry] of Object.entries(config.servers)) {
    assert.ok(entry.command.startsWith(path.join(ROOT, '.tools', 'runtime')));
    assert.ok(entry.args[0].startsWith(path.join(ROOT, 'tools', 'node_modules')));
    assert.equal(entry.cwd, ROOT);
    for (const key of ['HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'TEMP', 'TMP', 'NPM_CONFIG_CACHE', 'PLAYWRIGHT_BROWSERS_PATH', 'HF_HOME', 'TORCH_HOME', 'CUPY_CACHE_DIR', 'CUDA_CACHE_PATH']) {
      assert.ok(entry.env[key].startsWith(path.join(ROOT, '.tools')), `${name}/${key}`);
    }
    assert.ok(entry.env.PATH.endsWith('${env:PATH}'));
    assert.ok(entry.env.PATH.includes(path.join(ROOT, '.venv', 'Scripts')));
  }
});

test('filesystem starts read-only in a dedicated folder, not the repository or drive', () => {
  const entry = buildConfig(ROOT, manifest).servers.filesystem;
  assert.deepEqual(entry.args.slice(1), ['--read-only', path.join(ROOT, '.tools', 'workspace')]);
});

test('browser servers use isolated project profiles and disable Chrome telemetry', () => {
  const servers = buildConfig(ROOT, manifest).servers;
  assert.ok(servers.playwright.args.includes('--isolated'));
  assert.ok(servers.playwright.args.includes('--headless'));
  assert.ok(servers['chrome-devtools'].args.includes('--no-usage-statistics'));
  assert.ok(servers['chrome-devtools'].args.includes('--no-performance-crux'));
  assert.equal(servers['chrome-devtools'].env.CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS, '1');
});

test('runtime environment never captures credentials from the launching shell', () => {
  const env = localEnvironment(ROOT);
  assert.equal(env.GITHUB_TOKEN, undefined);
  assert.equal(env.OPENAI_API_KEY, undefined);
});

test('lockfile matches exact package pins and install scripts stay disabled', () => {
  const lock = JSON.parse(readFileSync(path.join(ROOT, 'tools', 'package-lock.json'), 'utf8'));
  for (const server of SERVERS) {
    const version = manifest.dependencies[server.package];
    assert.match(version, /^\d+\.\d+\.\d+$/);
    assert.equal(lock.packages[`node_modules/${server.package}`].version, version);
  }
  const npmrc = readFileSync(path.join(ROOT, 'tools', '.npmrc'), 'utf8');
  assert.match(npmrc, /^ignore-scripts=true$/m);
  assert.match(npmrc, /^engine-strict=true$/m);
});

test('installation checks reject tampered runtimes and mismatched package versions', t => {
  const root = fixtureRoot(t);
  const config = buildConfig(root, manifest);
  const node = config.servers.filesystem.command;
  mkdirSync(path.dirname(node), { recursive: true });
  writeFileSync(node, 'fixture');
  assert.throws(() => validateInstallation(root, manifest, config), /checksum mismatch/);
  const fixtureManifest = structuredClone(manifest);
  fixtureManifest.deeppanda.nodeExecutableSha256 = createHash('sha256').update('fixture').digest('hex');
  for (const server of SERVERS) {
    const directory = path.join(root, 'tools', 'node_modules', server.package);
    mkdirSync(path.dirname(config.servers[server.name].args[0]), { recursive: true });
    writeFileSync(path.join(directory, 'package.json'), JSON.stringify({ version: '0.0.0' }));
  }
  assert.throws(() => validateInstallation(root, fixtureManifest, config), /pinned manifest/);
});

test('preflight failures replace a stale successful verification report', async t => {
  const root = fixtureRoot(t);
  const target = path.join(root, '.tools', 'mcp-verification.json');
  mkdirSync(path.dirname(target), { recursive: true });
  writeFileSync(target, JSON.stringify({ installation_valid: true, results: [{ ok: true }] }));
  const logger = t.mock.method(console, 'error', () => {});
  assert.equal(await verifyInstallation(root), false);
  const report = JSON.parse(readFileSync(target, 'utf8'));
  assert.equal(report.installation_valid, false);
  assert.equal(report.results[0].ok, false);
  assert.match(report.results[0].error, /ENOENT/);
  assert.equal(logger.mock.callCount(), 1);
});

test('PowerShell checksum failure unpublishes host config and invalidates prior success', { skip: process.platform !== 'win32' }, t => {
  const root = fixtureRoot(t);
  copyFileSync(path.join(ROOT, 'setup-tools.ps1'), path.join(root, 'setup-tools.ps1'));
  mkdirSync(path.join(root, 'tools'));
  writeFileSync(path.join(root, 'tools', 'package.json'), JSON.stringify(manifest));
  const node = buildConfig(root, manifest).servers.filesystem.command;
  mkdirSync(path.dirname(node), { recursive: true });
  writeFileSync(node, 'not executable');
  const config = path.join(root, '.tools', 'mcp-servers.json');
  const report = path.join(root, '.tools', 'mcp-verification.json');
  writeFileSync(config, '{}');
  writeFileSync(report, JSON.stringify({ installation_valid: true }));
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-File', path.join(root, 'setup-tools.ps1'), '-VerifyOnly'], {
    cwd: root, env: { ...process.env, ...localEnvironment(root) }, encoding: 'utf8', timeout: 10000, windowsHide: true,
  });
  assert.ifError(result.error);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /checksum mismatch/);
  assert.equal(existsSync(config), false);
  const checked = JSON.parse(readFileSync(report, 'utf8'));
  assert.equal(checked.installation_valid, false);
  assert.match(checked.results[0].error, /checksum mismatch/);
});

test('MCP verifier discovers every page of a read-only filesystem fixture', async () => {
  const result = await verifyServer('filesystem', protocolFixture({
    name: 'first', inputSchema: { type: 'object' }, annotations: { readOnlyHint: true },
  }));
  assert.equal(result.ok, true);
  assert.equal(result.protocol, '2025-11-25');
  assert.equal(result.count, 2);
  assert.deepEqual(result.tools, ['first', 'second']);
});

test('MCP verifier rejects malformed schemas, empty names and writable filesystem tools', async () => {
  for (const tool of [
    { name: 'first', inputSchema: {} },
    { name: '', inputSchema: { type: 'object' } },
    { name: 'first', inputSchema: { type: 'object' }, annotations: { readOnlyHint: false } },
  ]) {
    await assert.rejects(verifyServer('filesystem', protocolFixture(tool)), /Missing tool names|not marked read-only/);
  }
});

test('MCP verifier terminates an unresponsive child within the configured deadline', async () => {
  const start = Date.now();
  await assert.rejects(verifyServer('fixture', {
    command: process.execPath,
    args: ['-e', 'setInterval(() => {}, 1000)'],
    cwd: ROOT,
    env: { ...localEnvironment(ROOT), PATH: process.env.PATH || '' },
  }, 200), /timed out/);
  assert.ok(Date.now() - start < 3000);
});

test('MCP verifier reports an early process failure instead of hanging', async () => {
  await assert.rejects(verifyServer('fixture', {
    command: process.execPath, args: ['-e', 'process.exit(7)'], cwd: ROOT,
    env: { ...localEnvironment(ROOT), PATH: process.env.PATH || '' },
  }), /Server exited \(7\)/);
});
