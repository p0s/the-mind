import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import {
  SITES,
  buildLocalManifest,
  initialState,
  prepareDelivery,
  submitPrepared,
  verifyLivePublication,
} from "./indexnow-publisher.mjs";

function argumentsMap(argv) {
  const options = new Map();
  for (let index = 0; index < argv.length; index += 1) {
    const key = argv[index];
    if (!key.startsWith("--") || !argv[index + 1] || argv[index + 1].startsWith("--")) throw new Error(`Expected a value after ${key}`);
    options.set(key, argv[index + 1]);
    index += 1;
  }
  return options;
}

function required(options, key) {
  const value = options.get(key);
  if (!value) throw new Error(`Missing required option ${key}`);
  return value;
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function writeNewJson(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, { flag: "wx", mode: 0o600 });
}

async function writeJson(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
}

async function verifyWithBoundedWait(args, fetchImpl) {
  let lastError;
  for (let attempt = 0; attempt < 5; attempt += 1) {
    try {
      await verifyLivePublication({ ...args, fetchImpl });
      return;
    } catch (error) {
      lastError = error;
      if (attempt < 4) await new Promise((resolve) => setTimeout(resolve, Math.min(1_000 * (2 ** attempt), 8_000)));
    }
  }
  throw new Error(`Live production preflight did not pass: ${lastError?.message || "unknown error"}`);
}

async function manifest(options) {
  const value = await buildLocalManifest({
    host: required(options, "--host"),
    directory: path.resolve(required(options, "--directory")),
    sourceSha: required(options, "--source-sha"),
  });
  await writeNewJson(path.resolve(required(options, "--output")), value);
}

async function bootstrap(options, env) {
  const host = required(options, "--host");
  const baselineSourceSha = required(options, "--baseline-source-sha");
  if (SITES[host]?.baselineSha !== baselineSourceSha) throw new Error(`Bootstrap baseline does not match the verified ${host} source`);
  await writeNewJson(path.resolve(required(options, "--output")), {
    version: 1,
    host,
    baselineSourceSha,
    runId: env.GITHUB_RUN_ID || null,
    runAttempt: env.GITHUB_RUN_ATTEMPT || null,
  });
}

async function prepare(options, fetchImpl) {
  const host = required(options, "--host");
  const current = await readJson(path.resolve(required(options, "--current")));
  const state = options.has("--state")
    ? await readJson(path.resolve(options.get("--state")))
    : initialState(host, await readJson(path.resolve(required(options, "--baseline"))));
  const now = options.has("--now") ? new Date(options.get("--now")) : new Date();
  if (!Number.isFinite(now.getTime())) throw new Error("--now must be a valid ISO date");
  await verifyWithBoundedWait({ host, current, state }, fetchImpl);
  const prepared = prepareDelivery(state, current, now);
  const directory = path.resolve(required(options, "--output-directory"));
  if (prepared.urls.length) {
    await writeNewJson(path.join(directory, "before", "state.json"), prepared.state);
    await writeNewJson(path.join(directory, "request.json"), { host, urls: prepared.urls });
    await writeJson(path.join(directory, "result.json"), { status: "ready", added: prepared.delta.added.length, changed: prepared.delta.changed.length, deleted: prepared.delta.deleted.length, selected: prepared.urls.length });
  } else {
    await writeNewJson(path.join(directory, "after", "state.json"), prepared.state);
    await writeJson(path.join(directory, "result.json"), { status: prepared.status, added: prepared.delta.added.length, changed: prepared.delta.changed.length, deleted: prepared.delta.deleted.length, selected: 0 });
  }
}

async function submit(options, fetchImpl) {
  const host = required(options, "--host");
  const current = await readJson(path.resolve(required(options, "--current")));
  const preparedState = await readJson(path.resolve(required(options, "--before-state")));
  const request = await readJson(path.resolve(required(options, "--request")));
  if (request.host !== host || !Array.isArray(request.urls)) throw new Error("Prepared IndexNow request is invalid");
  const result = await submitPrepared({ host, current, preparedState, urls: request.urls, fetchImpl });
  const directory = path.resolve(required(options, "--output-directory"));
  await writeNewJson(path.join(directory, "after", "state.json"), result.state);
  await writeJson(path.join(directory, "result.json"), {
    status: result.status,
    httpStatus: result.httpStatus,
    selected: request.urls.length,
    error: result.error,
  });
  if (result.error) throw new Error(result.error);
}

export async function main(argv, { fetchImpl = fetch, env = process.env } = {}) {
  const [command, ...rest] = argv;
  const options = argumentsMap(rest);
  if (command === "bootstrap") return bootstrap(options, env);
  if (command === "manifest") return manifest(options);
  if (command === "prepare") return prepare(options, fetchImpl);
  if (command === "submit") return submit(options, fetchImpl);
  throw new Error("Usage: node scripts/indexnow-state.mjs <bootstrap|manifest|prepare|submit> ...");
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  try {
    await main(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`IndexNow workflow step failed: ${error.message}\n`);
    process.exitCode = 1;
  }
}
