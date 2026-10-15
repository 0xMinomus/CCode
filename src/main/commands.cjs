'use strict';

const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');

const MARKER = '.ccode-default-commands.json';
const MARKER_VERSION = 1;
const COMMAND_NAME = /^[a-z0-9][a-z0-9-]*$/;
const SHA256 = /^[a-f0-9]{64}$/;

function sha256(data) {
  return crypto.createHash('sha256').update(data).digest('hex');
}

function ensureDirectory(directory) {
  fs.mkdirSync(directory, { recursive: true, mode: 0o700 });
  const stat = fs.lstatSync(directory);
  if (stat.isSymbolicLink() || !stat.isDirectory()) {
    throw new Error(`Default command path is not a real directory: ${directory}`);
  }
}

function readMarker(markerPath) {
  let stat;
  try {
    stat = fs.lstatSync(markerPath);
  } catch (error) {
    if (error.code === 'ENOENT') return { marker: { version: MARKER_VERSION, commands: {} }, exists: false };
    throw error;
  }
  if (stat.isSymbolicLink() || !stat.isFile()) throw new Error(`Invalid default command marker: ${markerPath}`);
  const marker = JSON.parse(fs.readFileSync(markerPath, 'utf8'));
  if (marker.version !== MARKER_VERSION || !marker.commands || Array.isArray(marker.commands) || typeof marker.commands !== 'object') {
    throw new Error(`Unsupported default command marker: ${markerPath}`);
  }
  for (const [name, entry] of Object.entries(marker.commands)) {
    if (!COMMAND_NAME.test(name) || !entry || !['managed', 'preserved'].includes(entry.state) ||
        (entry.state === 'managed' && !SHA256.test(entry.sha256))) {
      throw new Error(`Invalid default command ownership entry: ${name}`);
    }
  }
  return { marker, exists: true };
}

function atomicWrite(filePath, data) {
  const temporary = `${filePath}.${process.pid}.${crypto.randomBytes(8).toString('hex')}.tmp`;
  try {
    fs.writeFileSync(temporary, data, { flag: 'wx', mode: 0o600 });
    fs.renameSync(temporary, filePath);
  } finally {
    try { fs.unlinkSync(temporary); } catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}

function listDefaults(resourceDir) {
  const stat = fs.lstatSync(resourceDir);
  if (stat.isSymbolicLink() || !stat.isDirectory()) throw new Error(`Invalid default command resources: ${resourceDir}`);
  const files = fs.readdirSync(resourceDir, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.md'))
    .map((entry) => entry.name)
    .sort();
  if (!files.length || files.some((file) => !COMMAND_NAME.test(file.slice(0, -3)))) {
    throw new Error(`Default command resources have invalid names: ${resourceDir}`);
  }
  return files;
}

function seedDefaultCommands({ storageDir = process.env.CCODE_STORAGE_DIR, resourceDir = path.join(__dirname, 'defaults') } = {}) {
  if (typeof storageDir !== 'string' || !path.isAbsolute(storageDir)) {
    throw new Error('CCODE_STORAGE_DIR must be an absolute path before seeding default commands');
  }
  const commandDir = path.join(storageDir, 'commands');
  ensureDirectory(commandDir);
  const markerPath = path.join(commandDir, MARKER);
  const { marker, exists: markerExists } = readMarker(markerPath);
  const defaults = listDefaults(resourceDir);
  let changed = !markerExists;
  let seeded = 0;
  let updated = 0;
  let preserved = 0;
  for (const file of defaults) {
    const name = file.slice(0, -3);
    const target = path.join(commandDir, file);
    const source = fs.readFileSync(path.join(resourceDir, file));
    const sourceHash = sha256(source);
    const previous = marker.commands[name];
    let targetStat;
    try {
      targetStat = fs.lstatSync(target);
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
    }
    const regularFile = targetStat?.isFile() && !targetStat.isSymbolicLink();
    if (previous?.state === 'preserved') {
      preserved++;
      continue;
    }
    if (previous?.state === 'managed') {
      if (!regularFile) continue;
      const currentHash = sha256(fs.readFileSync(target));
      if (currentHash !== previous.sha256 && currentHash !== sourceHash) continue;
      if (currentHash !== sourceHash) {
        atomicWrite(target, source);
        updated++;
      }
      if (previous.sha256 !== sourceHash) {
        marker.commands[name] = { state: 'managed', sha256: sourceHash };
        changed = true;
      }
      continue;
    }
    if (targetStat) {
      marker.commands[name] = { state: 'preserved' };
      changed = true;
      preserved++;
      continue;
    }
    atomicWrite(target, source);
    marker.commands[name] = { state: 'managed', sha256: sourceHash };
    changed = true;
    seeded++;
  }
  if (changed) atomicWrite(markerPath, `${JSON.stringify(marker, null, 2)}\n`);
  return { seeded, updated, preserved, total: defaults.length };
}

function register() {
  try {
    seedDefaultCommands();
  } catch (error) {
    console.error('[CCode default commands]', error);
  }
}

module.exports = { MARKER, seedDefaultCommands, register };
