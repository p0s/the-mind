import { appendFile, mkdir } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { SITES } from "./indexnow-publisher.mjs";

const WORKFLOW_PATH = ".github/workflows/indexnow-production.yml";
const RESTORE_STEP = "Restore last IndexNow state or identify first activation";
const NO_ENTRY_STEPS = [
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
];

function parseHost(argv) {
  if (argv.length !== 2 || argv[0] !== "--host" || !SITES[argv[1]]) throw new Error("Usage: node scripts/restore-indexnow-state.mjs --host HOST");
  return argv[1];
}

async function api(url, env, fetchImpl) {
  const token = env.GITHUB_TOKEN;
  if (!token) throw new Error("GITHUB_TOKEN is required to restore delivery state");
  const response = await fetchImpl(url, {
    redirect: "error",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  if (!response.ok) throw new Error(`GitHub state read returned HTTP ${response.status}`);
  return response.json();
}

async function output(values, env) {
  const outputPath = env.GITHUB_OUTPUT;
  if (!outputPath) throw new Error("GITHUB_OUTPUT is required");
  await appendFile(outputPath, `${Object.entries(values).map(([key, value]) => `${key}=${value}`).join("\n")}\n`);
}

function exactStep(job, name) {
  const matches = job.steps.filter((step) => step.name === name);
  return matches.length === 1 ? matches[0] : null;
}

function isKnownNoEntryRun(run, jobsResult) {
  if (
    run.status !== "completed" ||
    run.head_branch !== "main" ||
    run.path !== WORKFLOW_PATH ||
    run.event !== "check_run" ||
    !Number.isInteger(run.run_attempt) ||
    !Array.isArray(jobsResult.jobs) ||
    jobsResult.total_count !== jobsResult.jobs.length ||
    jobsResult.jobs.length !== 1
  ) return false;

  const [job] = jobsResult.jobs;
  if (
    job.name !== "notify" ||
    job.status !== "completed" ||
    job.run_attempt !== run.run_attempt ||
    !Array.isArray(job.steps) ||
    job.steps.some((step) => step.status !== "completed")
  ) return false;

  if (
    run.conclusion === "skipped" &&
    job.conclusion === "skipped" &&
    job.runner_id === null &&
    job.runner_name === null &&
    job.steps.length === 0
  ) return true;

  if (
    run.conclusion !== "failure" ||
    job.conclusion !== "failure" ||
    !Number.isInteger(job.runner_id) ||
    typeof job.runner_name !== "string" ||
    job.steps.filter((step) => step.conclusion === "failure").length !== 1
  ) return false;

  const restore = exactStep(job, RESTORE_STEP);
  if (!restore || restore.conclusion !== "failure") return false;
  return NO_ENTRY_STEPS.every((name) => {
    const step = exactStep(job, name);
    return step?.conclusion === "skipped";
  });
}

export async function main(argv, { fetchImpl = fetch, env = process.env, cwd = process.cwd() } = {}) {
  const host = parseHost(argv);
  const site = SITES[host];
  const repository = env.GITHUB_REPOSITORY;
  const currentRunId = env.GITHUB_RUN_ID;
  const apiRoot = env.GITHUB_API_URL || "https://api.github.com";
  if (!repository || !currentRunId) throw new Error("GitHub repository and run context are required");
  if (!/^[1-9]\d*$/u.test(currentRunId)) throw new Error("Current GitHub run ID is malformed; refusing to restore IndexNow state");
  const prefix = `indexnow-state-${site.artifactSlug}-`;
  const matches = [];
  for (let page = 1; page <= 100; page += 1) {
    const result = await api(`${apiRoot}/repos/${repository}/actions/artifacts?per_page=100&page=${page}`, env, fetchImpl);
    if (!Number.isSafeInteger(result.total_count) || !Array.isArray(result.artifacts)) {
      throw new Error("IndexNow artifact history is incomplete; refusing to reset delivery state");
    }
    if (result.artifacts.some((artifact) => !artifact || typeof artifact.name !== "string" || !artifact.name)) {
      throw new Error("IndexNow artifact history contains an unknown record; refusing to reset delivery state");
    }
    const expectedCount = Math.min(100, Math.max(0, result.total_count - ((page - 1) * 100)));
    if (result.artifacts.length !== expectedCount) throw new Error("IndexNow artifact history is partial; refusing to reset delivery state");
    matches.push(...result.artifacts.filter((artifact) => artifact.name.startsWith(prefix)));
    if (page * 100 >= result.total_count) break;
    if (page === 100) throw new Error("IndexNow artifact history exceeded the 100-page restore limit");
  }
  for (const artifact of matches) {
    if (!Number.isFinite(Date.parse(artifact.created_at)) || !Number.isInteger(artifact.workflow_run?.id)) {
      throw new Error("IndexNow state artifact metadata is incomplete; refusing to select a restore point");
    }
  }
  const attempt = (name) => Number(name.match(/-(\d+)$/u)?.[1] || 0);
  const stage = (name) => name.includes("-after-") ? 2 : (name.includes("-before-") ? 1 : 0);
  matches.sort((left, right) =>
    Date.parse(right.created_at) - Date.parse(left.created_at) ||
    right.workflow_run.id - left.workflow_run.id ||
    attempt(right.name) - attempt(left.name) ||
    stage(right.name) - stage(left.name),
  );
  const selected = matches[0] || null;

  if (selected) {
    if (selected.expired) throw new Error("Latest IndexNow delivery state artifact has expired; refusing to reset state");
    const run = await api(`${apiRoot}/repos/${repository}/actions/runs/${selected.workflow_run?.id}`, env, fetchImpl);
    if (run.path !== WORKFLOW_PATH || run.head_branch !== "main") throw new Error("Latest IndexNow delivery state belongs to another workflow or branch");
    if (selected.workflow_run?.id !== Number(currentRunId) && run.status !== "completed") throw new Error("Previous IndexNow state run is not complete");
    const suffix = selected.name.slice(prefix.length);
    const artifactStage = suffix.match(/^(bootstrap|before|after)-\d+-\d+$/u)?.[1];
    if (!artifactStage) throw new Error("IndexNow state artifact name is invalid");
    if (artifactStage === "bootstrap") {
      await output({ bootstrap: "true", artifact_name: selected.name, run_id: selected.workflow_run.id, artifact_slug: site.artifactSlug }, env);
      return;
    }
    await mkdir(path.resolve(cwd, ".indexnow/restore"), { recursive: true });
    await output({ bootstrap: "false", artifact_name: selected.name, run_id: selected.workflow_run.id, artifact_slug: site.artifactSlug }, env);
    return;
  }

  const currentRunAttempt = env.GITHUB_RUN_ATTEMPT;
  if (!/^[1-9]\d*$/u.test(currentRunAttempt || "")) {
    throw new Error("Current GitHub run attempt is missing or malformed; refusing to reset delivery state");
  }
  if (Number(currentRunAttempt) !== 1) throw new Error("Current GitHub run is a retry without restored state; refusing to reset delivery state");

  const workflow = await api(`${apiRoot}/repos/${repository}/actions/workflows/indexnow-production.yml/runs?branch=main&per_page=100&page=1`, env, fetchImpl);
  if (!Number.isSafeInteger(workflow.total_count) || !Array.isArray(workflow.workflow_runs) || workflow.total_count !== workflow.workflow_runs.length) {
    throw new Error("IndexNow workflow history is incomplete; refusing to reset delivery state");
  }
  if (workflow.total_count > 100) throw new Error("IndexNow workflow history exceeded the 100-run restore limit");
  const runPrefix = `IndexNow ${site.projectName} `;
  const knownPrefixes = Object.values(SITES).map((entry) => `IndexNow ${entry.projectName} `);
  const hostRuns = [];
  for (const run of workflow.workflow_runs) {
    if (String(run.id) === currentRunId) continue;
    if (run.display_title?.startsWith(runPrefix)) {
      if (run.path !== WORKFLOW_PATH) throw new Error("IndexNow workflow history contains an unexpected run path");
      hostRuns.push(run);
      continue;
    }
    if (!knownPrefixes.some((knownPrefix) => run.display_title?.startsWith(knownPrefix))) {
      throw new Error("IndexNow workflow history contains an unknown run; refusing to reset delivery state");
    }
  }
  for (const run of hostRuns) {
    const jobs = await api(`${apiRoot}/repos/${repository}/actions/runs/${run.id}/jobs?per_page=100&page=1`, env, fetchImpl);
    if (!isKnownNoEntryRun(run, jobs)) throw new Error("IndexNow state artifact is missing after activation; refusing to reset delivery state");
  }
  await output({ bootstrap: "true", artifact_name: "", run_id: "", artifact_slug: site.artifactSlug }, env);
}

export { isKnownNoEntryRun };

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  try {
    await main(process.argv.slice(2));
  } catch (error) {
    process.stderr.write(`IndexNow state restore failed closed: ${error.message}\n`);
    process.exitCode = 1;
  }
}
