import assert from "node:assert/strict";
import { mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { main as restoreState } from "../scripts/restore-indexnow-state.mjs";
import { main as runStateStep } from "../scripts/indexnow-state.mjs";
import { SITES } from "../scripts/indexnow-publisher.mjs";

const host = "the-mind.xyz";
const site = SITES[host];
const workflowPath = ".github/workflows/indexnow-production.yml";
const mainSha = site.baselineSha;
const currentSha = "cf581a3a991229139f9fd60d3a8ee9605a137f05";
const prefix = `IndexNow ${site.projectName} `;

async function tempDir(t) {
  const directory = await mkdtemp(path.join(os.tmpdir(), "mind-indexnow-replay-"));
  t.after(() => rm(directory, { recursive: true, force: true }));
  return directory;
}

function response(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } });
}

function noEntryHistory() {
  const skippedRun = {
    id: 8101, path: workflowPath, head_branch: "main", event: "check_run", status: "completed",
    conclusion: "skipped", run_attempt: 1, display_title: `${prefix}preview-fixture`,
  };
  const failedRun = {
    id: 8102, path: workflowPath, head_branch: "main", event: "check_run", status: "completed",
    conclusion: "failure", run_attempt: 1, display_title: `${prefix}restore-fixture`,
  };
  const skippedJob = {
    name: "notify", status: "completed", conclusion: "skipped", run_attempt: 1,
    runner_id: null, runner_name: null, steps: [],
  };
  const workflowBusinessSteps = [
    "Persist first-activation marker",
    "Upload first-activation marker",
    "Download exact prior state artifact",
    "Install production build dependencies",
    "Build successful production source",
    "Build fixed production baseline for first activation",
    "Verify live publication and persist the request plan",
    "Persist pending and in-flight state before requesting Bing",
    "Submit one bounded IndexNow request",
    "Persist accepted receipt or retained pending state",
  ].map((name) => ({ name, status: "completed", conclusion: "skipped" }));
  const failedJob = {
    name: "notify", status: "completed", conclusion: "failure", run_attempt: 1,
    runner_id: 500, runner_name: "GitHub Actions 500",
    steps: [
      { name: "Restore last IndexNow state or identify first activation", status: "completed", conclusion: "failure" },
      ...workflowBusinessSteps,
    ],
  };
  return {
    runs: [skippedRun, failedRun],
    jobs: new Map([
      [skippedRun.id, { total_count: 1, jobs: [skippedJob] }],
      [failedRun.id, { total_count: 1, jobs: [failedJob] }],
    ]),
    runDetails: new Map([[8101, skippedRun], [8102, failedRun]]),
  };
}

function githubTransport({ artifacts = [], runs = [], jobs = new Map(), runDetails = new Map(), partialArtifacts = false, partialRuns = false } = {}) {
  return async (rawUrl, init = {}) => {
    assert.equal(init.headers.Authorization, "Bearer replay-token");
    const url = new URL(rawUrl);
    if (url.pathname.endsWith("/actions/artifacts")) {
      const listed = artifacts.filter((artifact) => !artifact.deleted);
      return response({ total_count: listed.length, artifacts: partialArtifacts ? [] : listed });
    }
    if (url.pathname.endsWith("/actions/workflows/indexnow-production.yml/runs")) {
      return response({ total_count: runs.length, workflow_runs: partialRuns ? runs.slice(0, -1) : runs });
    }
    const jobsMatch = url.pathname.match(/\/actions\/runs\/(\d+)\/jobs$/u);
    if (jobsMatch) return response(jobs.get(Number(jobsMatch[1])) || { total_count: 0, jobs: [] });
    const runMatch = url.pathname.match(/\/actions\/runs\/(\d+)$/u);
    if (runMatch) {
      const run = runDetails.get(Number(runMatch[1]));
      return run ? response(run) : response({ message: "Not Found" }, 404);
    }
    throw new Error(`Unexpected GitHub API request: ${rawUrl}`);
  };
}

function envFor(root, runId, runAttempt = "1") {
  return {
    GITHUB_TOKEN: "replay-token",
    GITHUB_REPOSITORY: "p0s/the-mind",
    GITHUB_RUN_ID: String(runId),
    GITHUB_RUN_ATTEMPT: runAttempt,
    GITHUB_API_URL: "https://api.github.test",
    GITHUB_OUTPUT: path.join(root, `output-${runId}.txt`),
  };
}

async function outputs(filePath) {
  const lines = (await readFile(filePath, "utf8")).trim().split("\n");
  return Object.fromEntries(lines.map((line) => {
    const index = line.indexOf("=");
    return [line.slice(0, index), line.slice(index + 1)];
  }));
}

async function buildFixture(t, text) {
  const directory = await tempDir(t);
  const key = site.keyFile.slice(0, -4);
  await writeFile(path.join(directory, site.keyFile), `${key}\n`);
  await writeFile(path.join(directory, "index.html"), `<html><body>${text}</body></html>`);
  await writeFile(path.join(directory, "sitemap.xml"), `<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"><url><loc>https://${host}/</loc></url></urlset>`);
  return directory;
}

function fakeLive(current, calls = []) {
  const key = site.keyFile.slice(0, -4);
  return async (url, init = {}) => {
    if (url === `https://${host}/.well-known/indexnow-release.json`) {
      return new Response(JSON.stringify({ version: 1, host, revision: current.revision }), { status: 200 });
    }
    if (url === `https://${host}/${site.keyFile}`) return new Response(`${key}\n`, { status: 200 });
    if (url === site.sitemapUrl) {
      const locs = Object.keys(current.pages).map((pageUrl) => `<url><loc>${pageUrl}</loc></url>`).join("");
      return new Response(`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${locs}</urlset>`, { status: 200 });
    }
    if (url === "https://www.bing.com/indexnow" && init.method === "POST") {
      calls.push(JSON.parse(init.body));
      return new Response("", { status: 202 });
    }
    throw new Error(`Unexpected publication request: ${url}`);
  };
}

test("production check suite runs while preview check suite stays skipped", async () => {
  const workflow = await readFile(".github/workflows/indexnow-production.yml", "utf8");
  assert.match(workflow, /github\.event\.check_run\.check_suite\.head_branch == 'main'/u);
  assert.match(workflow, /git merge-base --is-ancestor "\$TARGET_SHA" origin\/main/u);
  const base = {
    app: { slug: "cloudflare-workers-and-pages" }, status: "completed", conclusion: "success",
    head_branch: null, name: site.projectName,
  };
  const selected = (checkRun) => checkRun.app.slug === "cloudflare-workers-and-pages" &&
    checkRun.status === "completed" && checkRun.conclusion === "success" &&
    checkRun.check_suite.head_branch === "main" && checkRun.name === site.projectName;
  assert.equal(selected({ ...base, check_suite: { head_branch: "main" } }), true);
  assert.equal(selected({ ...base, check_suite: { head_branch: "codex/indexnow-automation-20261012" } }), false);
});

test("complete no-entry history bootstraps once, then restores exact state for an unchanged release", async (t) => {
  const root = await tempDir(t);
  const buildDirectory = await buildFixture(t, "unchanged public page");
  const history = noEntryHistory();
  const artifacts = [];
  const stateFiles = new Map();
  const calls = [];
  const recordArtifact = async (stage, runId, filePath, createdAt) => {
    const name = `indexnow-state-${site.artifactSlug}-${stage}-${runId}-1`;
    const state = JSON.parse(await readFile(filePath, "utf8"));
    artifacts.push({ id: artifacts.length + 1, name, created_at: createdAt, expired: false, workflow_run: { id: runId } });
    stateFiles.set(`${runId}/${name}`, state);
    history.runDetails.set(runId, { id: runId, path: workflowPath, head_branch: "main", event: "check_run", status: "completed", conclusion: "success", run_attempt: 1 });
    return name;
  };

  const firstEnv = envFor(root, 9000);
  await restoreState(["--host", host], {
    fetchImpl: githubTransport({ artifacts, runs: history.runs, jobs: history.jobs, runDetails: history.runDetails }),
    env: firstEnv,
    cwd: root,
  });
  assert.equal((await outputs(firstEnv.GITHUB_OUTPUT)).bootstrap, "true");

  const markerPath = path.join(root, ".indexnow/run/bootstrap/state.json");
  await runStateStep(["bootstrap", "--host", host, "--baseline-source-sha", mainSha, "--output", markerPath], {
    env: { GITHUB_RUN_ID: "9000", GITHUB_RUN_ATTEMPT: "1" },
  });
  await recordArtifact("bootstrap", 9000, markerPath, "2026-10-12T06:00:00.000Z");

  const baselinePath = path.join(root, "baseline.json");
  const currentPath = path.join(root, "current.json");
  await runStateStep(["manifest", "--host", host, "--directory", buildDirectory, "--source-sha", mainSha, "--output", baselinePath]);
  await runStateStep(["manifest", "--host", host, "--directory", buildDirectory, "--source-sha", currentSha, "--output", currentPath]);
  const current = JSON.parse(await readFile(currentPath, "utf8"));
  const firstResult = path.join(root, ".indexnow/run");
  await runStateStep(["prepare", "--host", host, "--current", currentPath, "--baseline", baselinePath, "--output-directory", firstResult], { fetchImpl: fakeLive(current, calls) });
  assert.equal(JSON.parse(await readFile(path.join(firstResult, "result.json"), "utf8")).status, "no_changes");
  assert.deepEqual(calls, []);
  await recordArtifact("after", 9000, path.join(firstResult, "after/state.json"), "2026-10-12T06:00:01.000Z");

  const nextEnv = envFor(root, 9001);
  await restoreState(["--host", host], {
    fetchImpl: githubTransport({ artifacts, runs: history.runs, jobs: history.jobs, runDetails: history.runDetails }),
    env: nextEnv,
    cwd: root,
  });
  const next = await outputs(nextEnv.GITHUB_OUTPUT);
  assert.equal(next.bootstrap, "false");
  assert.equal(next.run_id, "9000");
  const restored = stateFiles.get(`${next.run_id}/${next.artifact_name}`);
  assert.ok(restored);
  const restoreDirectory = path.join(root, ".indexnow/restore");
  await mkdir(restoreDirectory, { recursive: true });
  const restoredPath = path.join(restoreDirectory, "state.json");
  await writeFile(restoredPath, `${JSON.stringify(restored)}\n`);
  const noOpResult = path.join(root, ".indexnow/no-op");
  await runStateStep(["prepare", "--host", host, "--current", currentPath, "--state", restoredPath, "--output-directory", noOpResult], { fetchImpl: fakeLive(current, calls) });
  assert.equal(JSON.parse(await readFile(path.join(noOpResult, "result.json"), "utf8")).status, "no_changes");
  assert.deepEqual(calls, [], "first activation and unchanged release make no Bing request");
});

test("restore holds for reached marker or submit steps, expired state, and partial history", async (t) => {
  const root = await tempDir(t);
  const env = envFor(root, 9100);
  const base = noEntryHistory();
  const reached = {
    id: 9101, path: workflowPath, head_branch: "main", event: "check_run", status: "completed",
    conclusion: "failure", run_attempt: 1, display_title: `${prefix}state-was-reached`,
  };
  const steps = [...base.jobs.get(8102).jobs[0].steps].map((step) => ({ ...step }));
  steps[0].conclusion = "success";
  const reachedStep = steps.find((step) => step.name === "Upload first-activation marker");
  reachedStep.conclusion = "success";
  const reachedJob = { ...base.jobs.get(8102).jobs[0], conclusion: "failure", steps };
  const api = githubTransport({
    artifacts: [],
    runs: [reached],
    jobs: new Map([[reached.id, { total_count: 1, jobs: [reachedJob] }]]),
    runDetails: new Map([[reached.id, reached]]),
  });
  await assert.rejects(restoreState(["--host", host], { fetchImpl: api, env, cwd: root }), /missing after activation/u);

  const artifact = { id: 99, name: `indexnow-state-${site.artifactSlug}-after-9009-1`, created_at: "2026-10-12T05:00:00.000Z", expired: true, workflow_run: { id: 9009 } };
  const prior = { id: 9009, path: workflowPath, head_branch: "main", status: "completed", event: "check_run", conclusion: "success", run_attempt: 1 };
  await assert.rejects(restoreState(["--host", host], {
    fetchImpl: githubTransport({ artifacts: [artifact], runDetails: new Map([[prior.id, prior]]) }), env, cwd: root,
  }), /expired/u);

  await assert.rejects(restoreState(["--host", host], {
    fetchImpl: githubTransport({ artifacts: [artifact], partialArtifacts: true }), env, cwd: root,
  }), /artifact history is partial/u);
});

test("partial job history and failed artifact download never fall back to first activation", async (t) => {
  const root = await tempDir(t);
  const history = noEntryHistory();
  const env = envFor(root, 9200);
  const incompleteJobApi = githubTransport({
    artifacts: [],
    runs: [history.runs[0]],
    jobs: new Map([[history.runs[0].id, { total_count: 1, jobs: [] }]]),
    runDetails: history.runDetails,
  });
  await assert.rejects(restoreState(["--host", host], { fetchImpl: incompleteJobApi, env, cwd: root }), /missing after activation/u);

  const artifact = {
    id: 100, name: `indexnow-state-${site.artifactSlug}-after-9199-1`,
    created_at: "2026-10-12T06:30:00.000Z", expired: false, workflow_run: { id: 9199 },
  };
  const completedRun = {
    id: 9199, path: workflowPath, head_branch: "main", event: "check_run",
    status: "completed", conclusion: "success", run_attempt: 1,
  };
  const artifactApi = githubTransport({ artifacts: [artifact], runDetails: new Map([[9199, completedRun]]) });
  await restoreState(["--host", host], { fetchImpl: artifactApi, env, cwd: root });
  const selected = await outputs(env.GITHUB_OUTPUT);
  assert.equal(selected.bootstrap, "false");
  const stateFiles = new Map();
  const calls = [];
  const state = stateFiles.get(`${selected.run_id}/${selected.artifact_name}`);
  assert.equal(state, undefined);
  await assert.rejects(async () => {
    if (!state) throw new Error("mock artifact download failed");
  }, /artifact download failed/u);
  assert.deepEqual(calls, [], "failed download leaves prepare and submit unreachable");
});

test("a retry with missing state cannot bootstrap, while attempt two restores an existing artifact", async (t) => {
  const root = await tempDir(t);
  const retryRun = {
    id: 9300, path: workflowPath, head_branch: "main", event: "check_run", status: "completed",
    conclusion: "failure", run_attempt: 2, display_title: `${prefix}retried-after-submission`,
  };
  const priorAttemptJob = {
    name: "notify", status: "completed", conclusion: "failure", run_attempt: 1,
    runner_id: 500, runner_name: "GitHub Actions 500",
    steps: noEntryHistory().jobs.get(8102).jobs[0].steps.map((step) => ({ ...step })),
  };
  for (const name of [
    "Restore last IndexNow state or identify first activation",
    "Persist first-activation marker",
    "Upload first-activation marker",
    "Download exact prior state artifact",
    "Install production build dependencies",
    "Build successful production source",
    "Verify live publication and persist the request plan",
    "Persist pending and in-flight state before requesting Bing",
    "Submit one bounded IndexNow request",
  ]) {
    const step = priorAttemptJob.steps.find((entry) => entry.name === name);
    if (step) step.conclusion = "success";
  }
  const retryEnv = envFor(root, retryRun.id, "2");
  const apiRequests = [];
  const transport = githubTransport({
    artifacts: [],
    runs: [retryRun],
    jobs: new Map([[retryRun.id, { total_count: 1, jobs: [priorAttemptJob] }]]),
    runDetails: new Map([[retryRun.id, retryRun]]),
  });
  const trackedTransport = async (url, init = {}) => {
    apiRequests.push({ url: String(url), method: init.method || "GET" });
    return transport(url, init);
  };
  await assert.rejects(restoreState(["--host", host], { fetchImpl: trackedTransport, env: retryEnv, cwd: root }), /retry without restored state/u);
  await assert.rejects(readFile(retryEnv.GITHUB_OUTPUT), { code: "ENOENT" });
  assert.deepEqual(apiRequests.map((request) => request.method), ["GET"]);
  assert.ok(apiRequests.every((request) => new URL(request.url).pathname.endsWith("/actions/artifacts")));
  assert.equal(apiRequests.some((request) => request.url === "https://www.bing.com/indexnow"), false);

  const artifact = {
    id: 101, name: `indexnow-state-${site.artifactSlug}-after-9299-1`,
    created_at: "2026-10-12T06:30:00.000Z", expired: false, workflow_run: { id: 9299 },
  };
  const completedRun = {
    id: 9299, path: workflowPath, head_branch: "main", event: "check_run",
    status: "completed", conclusion: "success", run_attempt: 1,
  };
  const restoredEnv = envFor(root, retryRun.id, "2");
  await restoreState(["--host", host], {
    fetchImpl: githubTransport({ artifacts: [artifact], runDetails: new Map([[completedRun.id, completedRun]]) }),
    env: restoredEnv,
    cwd: root,
  });
  assert.equal((await outputs(restoredEnv.GITHUB_OUTPUT)).bootstrap, "false");
});
