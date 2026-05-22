/**
 * jobs.mjs — jobs 状态管理
 * 依赖: config.mjs
 */
import { existsSync, readFileSync, writeFileSync, writeFile as writeFileAsync } from "fs";
import { promisify } from "util";
import { JOBS_FILE } from "./config.mjs";

export function loadJobs() {
  try {
    if (existsSync(JOBS_FILE)) {
      return JSON.parse(readFileSync(JOBS_FILE, "utf8"));
    }
  } catch (err) {
    console.warn("[jobs] Failed to read jobs.json:", err.message);
  }
  return {};
}

export const jobs = loadJobs();

// 追踪待保存操作，避免并发写入
let saveOperation = null;
let saveJobsDirty = false;

/**
 * 异步保存 jobs 到磁盘，防止阻塞事件循环。
 * 对并发调用进行防抖，避免过多磁盘 I/O。
 */
export async function saveJobsAsync() {
  if (saveOperation) {
    saveJobsDirty = true;
    return saveOperation;
  }

  saveOperation = (async () => {
    try {
      do {
        saveJobsDirty = false;
        const data = JSON.stringify(jobs, null, 2);
        await promisify(writeFileAsync)(JOBS_FILE, data, "utf8");
      } while (saveJobsDirty);
    } catch (err) {
      console.warn("[jobs] Failed to save jobs.json:", err.message);
    } finally {
      saveOperation = null;
    }
  })();

  return saveOperation;
}

/**
 * 同步保存，仅用于启动/初始化阶段。
 * 服务器完全启动后不应调用此函数。
 */
export function saveJobsSync() {
  try {
    writeFileSync(JOBS_FILE, JSON.stringify(jobs, null, 2), "utf8");
  } catch (err) {
    console.warn("[jobs] Failed to save jobs.json:", err.message);
  }
}

export function updateJob(jobId, patch) {
  if (!jobs[jobId]) return;
  jobs[jobId] = { ...jobs[jobId], ...patch };
  saveJobsAsync();
}
