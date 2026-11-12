import { spawn } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { ROOT, SERVERS, buildConfig, prepareDirectories, readManifest, validateInstallation } from './local-mcp.mjs';

export async function verifyServer(name, entry, timeoutMs = 30000) {
  const env = { ...process.env, ...entry.env };
  env.PATH = env.PATH.replace('${env:PATH}', process.env.PATH || '');
  const child = spawn(entry.command, entry.args, {
    cwd: entry.cwd, env, windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'],
  });
  const pending = new Map();
  let buffer = '';
  let stderr = '';
  let sequence = 0;
  let timer;
  const failPending = error => {
    for (const waiter of pending.values()) waiter.reject(error);
    pending.clear();
  };
  const closed = new Promise(resolve => {
    child.once('error', error => { failPending(error); resolve(); });
    child.once('close', code => {
      failPending(new Error(`Server exited (${code}): ${stderr.slice(-1500)}`));
      resolve();
    });
  });
  child.stderr.on('data', data => { stderr = (stderr + data.toString('utf8')).slice(-8000); });
  child.stdout.setEncoding('utf8');
  child.stdout.on('data', data => {
    buffer += data;
    if (buffer.length > 10_000_000) {
      failPending(new Error('MCP response exceeded 10 MB.'));
      child.kill();
      return;
    }
    let newline;
    while ((newline = buffer.indexOf('\n')) !== -1) {
      const line = buffer.slice(0, newline);
      buffer = buffer.slice(newline + 1);
      if (!line.trim()) continue;
      try {
        const message = JSON.parse(line);
        const waiter = pending.get(message.id);
        if (waiter) {
          pending.delete(message.id);
          if (message.error) waiter.reject(new Error(message.error.message));
          else waiter.resolve(message.result);
        } else if (message.method && message.id !== undefined) {
          child.stdin.write(`${JSON.stringify({
            jsonrpc: '2.0', id: message.id, error: { code: -32601, message: 'Client method not supported' },
          })}\n`);
        }
      } catch (error) {
        failPending(new Error(`Invalid MCP response: ${error.message}`));
        child.kill();
      }
    }
  });
  child.stdin.on('error', failPending);
  const request = (method, params) => new Promise((resolve, reject) => {
    const id = ++sequence;
    pending.set(id, { resolve, reject });
    child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', id, method, params })}\n`);
  });
  try {
    const operation = async () => {
      const initialized = await request('initialize', {
        protocolVersion: '2025-11-25', capabilities: {},
        clientInfo: { name: 'deeppanda-install-check', version: '1.0.0' },
      });
      if (!initialized?.protocolVersion || !initialized?.capabilities?.tools) {
        throw new Error('Server did not advertise an MCP tools capability.');
      }
      child.stdin.write(`${JSON.stringify({ jsonrpc: '2.0', method: 'notifications/initialized' })}\n`);
      const tools = [];
      let cursor;
      for (let page = 0; page < 20; page++) {
        const result = await request('tools/list', cursor ? { cursor } : {});
        if (!Array.isArray(result?.tools)) throw new Error('Invalid tools/list result.');
        tools.push(...result.tools);
        cursor = result.nextCursor;
        if (!cursor) break;
      }
      if (cursor) throw new Error('Tool pagination exceeded 20 pages.');
      if (!tools.length || tools.some(tool => typeof tool?.name !== 'string' || !tool.name || tool.inputSchema?.type !== 'object')) {
        throw new Error('Missing tool names or input schemas.');
      }
      if (name === 'filesystem' && tools.some(tool => tool.annotations?.readOnlyHint !== true)) {
        throw new Error('Filesystem exposed a tool that is not marked read-only.');
      }
      return { name, ok: true, protocol: initialized.protocolVersion, count: tools.length, tools: tools.map(tool => tool.name) };
    };
    return await Promise.race([
      operation(),
      new Promise((_, reject) => {
        timer = setTimeout(() => reject(new Error(`MCP handshake/list timed out after ${timeoutMs} ms.`)), timeoutMs);
      }),
    ]);
  } finally {
    clearTimeout(timer);
    child.kill();
    await closed;
  }
}

function writeReport(root, results) {
  writeFileSync(path.join(root, '.tools', 'mcp-verification.json'), `${JSON.stringify({
    checked_at: new Date().toISOString(), scope: 'stdio initialize and tools/list only',
    installation_valid: results.length === SERVERS.length && results.every(result => result.ok), results,
  }, null, 2)}\n`, 'utf8');
}

export async function verifyInstallation(root = ROOT) {
  prepareDirectories(root);
  writeReport(root, [{ name: 'verification', ok: false, error: 'Verification is running or did not finish.' }]);
  const results = [];
  let config;
  try {
    const manifest = readManifest(root);
    config = buildConfig(root, manifest);
    validateInstallation(root, manifest, config);
  } catch (error) {
    console.error(`Installation is not ready: ${error.message}`);
    writeReport(root, [{ name: 'installation', ok: false, error: error.message }]);
    return false;
  }
  for (const [name, entry] of Object.entries(config.servers)) {
    try {
      const result = await verifyServer(name, entry);
      results.push(result);
      console.log(`${name}: ${result.count} tools; protocol ${result.protocol}`);
    } catch (error) {
      results.push({ name, ok: false, error: error.message });
      console.error(`${name}: FAILED: ${error.message}`);
    }
  }
  writeReport(root, results);
  return results.every(result => result.ok);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  verifyInstallation()
    .then(ok => { process.exitCode = ok ? 0 : 1; })
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
