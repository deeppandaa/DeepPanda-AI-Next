import { createHash } from 'node:crypto';
import { mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
export const SERVERS = [
  { name: 'filesystem', package: '@modelcontextprotocol/server-filesystem', script: 'dist/index.js' },
  { name: 'sequential-thinking', package: '@modelcontextprotocol/server-sequential-thinking', script: 'dist/index.js' },
  { name: 'playwright', package: '@playwright/mcp', script: 'cli.js' },
  { name: 'chrome-devtools', package: 'chrome-devtools-mcp', script: 'build/src/bin/chrome-devtools-mcp.js' },
  { name: 'rea', package: 'rea-agents', script: 'scripts/rea.mjs' },
];

export function readManifest(root = ROOT) {
  return JSON.parse(readFileSync(path.join(root, 'tools', 'package.json'), 'utf8'));
}

export function localEnvironment(root) {
  const state = path.join(root, '.tools');
  return {
    HOME: path.join(state, 'home'),
    USERPROFILE: path.join(state, 'home'),
    APPDATA: path.join(state, 'home', 'AppData', 'Roaming'),
    LOCALAPPDATA: path.join(state, 'home', 'AppData', 'Local'),
    TEMP: path.join(state, 'temp'),
    TMP: path.join(state, 'temp'),
    TMPDIR: path.join(state, 'temp'),
    XDG_CACHE_HOME: path.join(state, 'cache'),
    HF_HOME: path.join(state, 'cache', 'huggingface'),
    TORCH_HOME: path.join(state, 'cache', 'torch'),
    CUPY_CACHE_DIR: path.join(state, 'cache', 'cupy'),
    CUDA_CACHE_PATH: path.join(state, 'cache', 'cuda'),
    PYTHONNOUSERSITE: '1',
    NPM_CONFIG_CACHE: path.join(state, 'npm-cache'),
    NPM_CONFIG_USERCONFIG: path.join(root, 'tools', '.npmrc'),
    NPM_CONFIG_GLOBALCONFIG: path.join(state, 'npm-globalrc'),
    PLAYWRIGHT_BROWSERS_PATH: path.join(state, 'browsers'),
    PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD: '1',
    PUPPETEER_SKIP_DOWNLOAD: 'true',
    CHROME_DEVTOOLS_MCP_NO_USAGE_STATISTICS: '1',
    CHROME_DEVTOOLS_MCP_NO_UPDATE_CHECKS: '1',
  };
}

export function buildConfig(root, manifest) {
  const runtime = path.join(root, '.tools', 'runtime', `node-v${manifest.deeppanda.nodeVersion}-win-x64`);
  const state = path.join(root, '.tools');
  const env = {
    ...localEnvironment(root),
    PATH: `${runtime}${path.delimiter}${path.join(root, '.venv', 'Scripts')}${path.delimiter}\${env:PATH}`,
  };
  const extraArgs = {
    filesystem: ['--read-only', path.join(state, 'workspace')],
    'sequential-thinking': [],
    playwright: ['--isolated', '--headless', '--output-dir', path.join(state, 'output', 'playwright')],
    'chrome-devtools': [
      '--headless', '--no-usage-statistics', '--no-performance-crux',
      '--user-data-dir', path.join(state, 'profiles', 'chrome'),
    ],
    rea: ['mcp'],
  };
  return {
    servers: Object.fromEntries(SERVERS.map(server => [server.name, {
      type: 'stdio',
      command: path.join(runtime, 'node.exe'),
      args: [path.join(root, 'tools', 'node_modules', server.package, server.script), ...extraArgs[server.name]],
      cwd: root,
      env,
    }])),
  };
}

export function validateInstallation(root, manifest, config) {
  const node = config.servers.filesystem.command;
  const hash = createHash('sha256').update(readFileSync(node)).digest('hex');
  if (hash !== manifest.deeppanda.nodeExecutableSha256) {
    throw new Error('Portable Node executable checksum mismatch; refusing to run it.');
  }
  for (const server of SERVERS) {
    const installed = JSON.parse(readFileSync(path.join(root, 'tools', 'node_modules', server.package, 'package.json'), 'utf8'));
    if (installed.version !== manifest.dependencies[server.package]) {
      throw new Error(`${server.package}: installed version does not match the pinned manifest.`);
    }
    readFileSync(config.servers[server.name].args[0]);
  }
}

export function prepareDirectories(root) {
  const state = path.join(root, '.tools');
  for (const folder of [
    'home', 'home/AppData/Roaming', 'home/AppData/Local', 'temp', 'cache', 'npm-cache',
    'cache/huggingface', 'cache/torch', 'cache/cupy', 'cache/cuda',
    'browsers', 'workspace', 'output/playwright', 'profiles/chrome', 'logs',
  ]) {
    mkdirSync(path.join(state, folder), { recursive: true });
  }
}

export function configure(root = ROOT) {
  const manifest = readManifest(root);
  const config = buildConfig(root, manifest);
  validateInstallation(root, manifest, config);
  prepareDirectories(root);
  const target = path.join(root, '.tools', 'mcp-servers.json');
  const staged = `${target}.tmp`;
  writeFileSync(staged, `${JSON.stringify(config, null, 2)}\n`, 'utf8');
  renameSync(staged, target);
  return target;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  try {
    console.log(`Configured ${SERVERS.length} local MCP servers: ${configure()}`);
    console.log('Package integrity is verified. Use setup-tools.ps1 -VerifyOnly for a complete protocol check.');
  } catch (error) {
    console.error(`Local MCP setup failed: ${error.message}`);
    process.exitCode = 1;
  }
}
