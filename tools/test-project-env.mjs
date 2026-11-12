import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { ROOT } from './local-mcp.mjs';

function fixtureRoot(t) {
  const parent = path.join(ROOT, '_tmp', 'temp');
  mkdirSync(parent, { recursive: true });
  const root = mkdtempSync(path.join(parent, 'python-fixture-'));
  t.after(() => rmSync(root, { recursive: true }));
  mkdirSync(path.join(root, 'tools'));
  copyFileSync(path.join(ROOT, 'setup-python.ps1'), path.join(root, 'setup-python.ps1'));
  for (const name of ['project-env.ps1', 'python-runtime.json']) {
    copyFileSync(path.join(ROOT, 'tools', name), path.join(root, 'tools', name));
  }
  return root;
}

function setupPython(root, args = []) {
  return spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-File',
    path.join(root, 'setup-python.ps1'), ...args], {
    encoding: 'utf8', windowsHide: true, timeout: 15000,
  });
}

test('verify-only never downloads or creates an absent Python environment', {
  skip: process.platform !== 'win32',
}, t => {
  const root = fixtureRoot(t);
  const result = setupPython(root, ['-VerifyOnly']);
  assert.ifError(result.error);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /Project Python is missing/);
  assert.equal(existsSync(path.join(root, '_tmp', 'downloads')), false);
  assert.equal(existsSync(path.join(root, '.venv')), false);
});

test('a tampered download is never extracted and existing venv is untouched', {
  skip: process.platform !== 'win32',
}, t => {
  const root = fixtureRoot(t);
  const manifest = JSON.parse(readFileSync(path.join(root, 'tools', 'python-runtime.json'), 'utf8'));
  const downloads = path.join(root, '_tmp', 'downloads');
  mkdirSync(downloads, { recursive: true });
  writeFileSync(path.join(downloads, `python.${manifest.version}.nupkg`), 'invalid archive');
  mkdirSync(path.join(root, '.venv'));
  const previous = path.join(root, '.venv', 'pyvenv.cfg');
  writeFileSync(previous, 'previous configuration');
  const result = setupPython(root);
  assert.ifError(result.error);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /archive checksum mismatch/);
  assert.equal(existsSync(path.join(root, 'runtimes', `python-${manifest.version}`)), false);
  assert.equal(readFileSync(previous, 'utf8'), 'previous configuration');
});

test('a tampered installed Python is rejected before execution', {
  skip: process.platform !== 'win32',
}, t => {
  const root = fixtureRoot(t);
  const manifest = JSON.parse(readFileSync(path.join(root, 'tools', 'python-runtime.json'), 'utf8'));
  const directory = path.join(root, 'runtimes', `python-${manifest.version}`, 'tools');
  mkdirSync(directory, { recursive: true });
  writeFileSync(path.join(directory, 'python.exe'), 'invalid executable');
  const result = setupPython(root, ['-VerifyOnly']);
  assert.ifError(result.error);
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /executable checksum mismatch/);
  assert.equal(existsSync(path.join(root, '.venv')), false);
});

test('project environment keeps caches local without replacing the real user profile', {
  skip: process.platform !== 'win32',
}, () => {
  const script = path.join(ROOT, 'tools', 'project-env.ps1').replaceAll("'", "''");
  const result = spawnSync('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', `
    $ErrorActionPreference = 'Stop'
    $originalProfile = $env:USERPROFILE
    $originalAppdata = $env:APPDATA
    . '${script}'
    . '${script}'
    $names = @('TEMP','TMP','TMPDIR','PIP_CACHE_DIR','XDG_CACHE_HOME','HF_HOME','TORCH_HOME',
      'CUPY_CACHE_DIR','CUDA_CACHE_PATH','PLAYWRIGHT_BROWSERS_PATH')
    $paths = @{}
    foreach ($name in $names) { $paths[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    @{
      paths = $paths
      profileUnchanged = ($env:USERPROFILE -eq $originalProfile)
      appdataUnchanged = ($env:APPDATA -eq $originalAppdata)
      pathEntries = @($env:PATH -split ';')
      pythonNoUserSite = $env:PYTHONNOUSERSITE
    } | ConvertTo-Json -Depth 4 -Compress
  `], { encoding: 'utf8', windowsHide: true, timeout: 15000 });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  const value = JSON.parse(result.stdout);
  assert.equal(value.profileUnchanged, true);
  assert.equal(value.appdataUnchanged, true);
  assert.equal(value.pythonNoUserSite, '1');
  for (const [name, target] of Object.entries(value.paths)) {
    assert.ok(target.startsWith(`${ROOT}${path.sep}`), `${name}: ${target}`);
  }
  const scripts = path.join(ROOT, '.venv', 'Scripts');
  assert.equal(value.pathEntries[0], scripts);
  assert.equal(value.pathEntries.filter(entry => entry === scripts).length, 1);
});
