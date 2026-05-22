/**
 * music.mjs — 音乐曲目查询、路径解析、大模型可用性检查
 * 依赖: config.mjs, utils.mjs
 */
import { existsSync, readdirSync, statSync } from "fs";
import { basename, extname, resolve } from "path";
import {
  MUSIC_DIR,
  MUSIC_EXTENSIONS,
  MUSIC_MIME_TYPES,
  PORT,
  PYTHON_API,
} from "./config.mjs";
import { getJson, isInside } from "./utils.mjs";

export function titleFromMusicFilename(filename) {
  const name = basename(filename, extname(filename)).replace(/-mixkit$/i, "");
  return name
    .split(/[-_]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function resolveMusicTrack(rawId) {
  let decoded = "";
  try {
    decoded = decodeURIComponent(String(rawId ?? ""));
  } catch {
    return null;
  }
  const filename = basename(decoded);
  if (!filename || filename !== decoded) return null;
  const ext = extname(filename).toLowerCase();
  if (!MUSIC_EXTENSIONS.has(ext)) return null;
  const filePath = resolve(MUSIC_DIR, filename);
  if (!isInside(filePath, MUSIC_DIR) || !existsSync(filePath)) return null;
  const stat = statSync(filePath);
  if (!stat.isFile() || stat.size <= 0) return null;
  return {
    id: filename,
    name: titleFromMusicFilename(filename),
    url: `http://localhost:${PORT}/music/${encodeURIComponent(filename)}`,
    size: stat.size,
    contentType: MUSIC_MIME_TYPES.get(ext) ?? "application/octet-stream",
    filePath,
  };
}

export function listMusicTracks() {
  return readdirSync(MUSIC_DIR, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => resolveMusicTrack(entry.name))
    .filter(Boolean)
    .map(({ id, name, url, size }) => ({ id, name, url, size }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

export async function ensureLargeModelAvailable() {
  try {
    await getJson(`${PYTHON_API}/health/llm`);
  } catch (err) {
    throw new Error(
      `大模型暂时连接不上，已停止本次任务；请检查模型配置和网络后重试。${err.message ? ` 详情：${err.message}` : ""}`,
    );
  }
}
