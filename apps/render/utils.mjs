/**
 * utils.mjs — 工具函数
 * 依赖: config.mjs, jobs.mjs
 */
import http from "http";
import { resolve } from "path";
import {
  ACTIVE_PEN_STYLE,
  ACTIVE_VIDEO_STYLE,
  ENABLE_ALL_STYLE_OPTIONS,
  GOLPO_VIDEO_STYLES,
  VIDEO_STYLE_ALIASES,
} from "./config.mjs";

// ---------- HTTP helpers ----------

export function readBody(req, limitBytes = 10 * 1024 * 1024) {
  return new Promise((resolvePromise, reject) => {
    const chunks = [];
    let totalBytes = 0;
    req.on("data", (chunk) => {
      const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      chunks.push(buffer);
      totalBytes += buffer.length;
      if (totalBytes > limitBytes) {
        reject(new Error("Request body too large"));
        req.destroy();
      }
    });
    req.on("end", () => resolvePromise(Buffer.concat(chunks).toString("utf8")));
    req.on("error", reject);
  });
}

export function postJson(url, payload, timeoutMs = 300000) {
  const body = JSON.stringify(payload);
  return new Promise((resolvePromise, reject) => {
    const req = http.request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const text = Buffer.concat(chunks).toString("utf8");
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${url} returned ${res.statusCode}: ${text}`));
            return;
          }
          try {
            resolvePromise(JSON.parse(text));
          } catch (err) {
            reject(new Error(`Invalid JSON from ${url}: ${err.message}`));
          }
        });
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`${url} timed out`)));
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

export function getJson(url, timeoutMs = 12000) {
  return new Promise((resolvePromise, reject) => {
    const req = http.request(url, { method: "GET" }, (res) => {
      const chunks = [];
      res.on("data", (chunk) => chunks.push(chunk));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let payload = {};
        try {
          payload = text ? JSON.parse(text) : {};
        } catch {}
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const detail = payload.detail || payload.error || text || `HTTP ${res.statusCode}`;
          reject(new Error(String(detail)));
          return;
        }
        resolvePromise(payload);
      });
    });
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`${url} timed out`)));
    req.on("error", reject);
    req.end();
  });
}

export function postBuffer(url, payload, timeoutMs = 120000) {
  const body = JSON.stringify(payload);
  return new Promise((resolvePromise, reject) => {
    const req = http.request(
      url,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Content-Length": Buffer.byteLength(body),
        },
      },
      (res) => {
        const chunks = [];
        res.on("data", (chunk) => chunks.push(chunk));
        res.on("end", () => {
          const buffer = Buffer.concat(chunks);
          if (res.statusCode < 200 || res.statusCode >= 300) {
            reject(new Error(`${url} returned ${res.statusCode}: ${buffer.toString("utf8")}`));
            return;
          }
          resolvePromise(buffer);
        });
      },
    );
    req.setTimeout(timeoutMs, () => req.destroy(new Error(`${url} timed out`)));
    req.on("error", reject);
    req.write(body);
    req.end();
  });
}

export function sleep(ms) {
  return new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

export function clampNumber(value, min, max, fallback) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.max(min, Math.min(max, parsed));
}

// ---------- 文本处理 ----------

export function looksLikeMojibake(value) {
  const text = String(value ?? "");
  if (!text) return false;
  const suspicious = (text.match(/[�€ÃÂåæçèéäöü-]/g) ?? []).length;
  const cjk = (text.match(/[㐀-鿿]/g) ?? []).length;
  return suspicious >= 2 && suspicious > Math.max(1, Math.floor(cjk * 0.2));
}

export function mojibakeScore(value) {
  const text = String(value ?? "");
  return (text.match(/[�€ÃÂåæçèéäöü-]/g) ?? []).length * 3 - (text.match(/[㐀-鿿]/g) ?? []).length;
}

export function tryRepairMojibake(value) {
  const text = String(value ?? "");
  if (!looksLikeMojibake(text)) return text;
  const attempts = [
    () => Buffer.from(text, "latin1").toString("utf8"),
    () => Buffer.from(text, "binary").toString("utf8"),
  ];
  let best = text;
  let bestScore = mojibakeScore(text);
  for (const attempt of attempts) {
    try {
      const candidate = attempt();
      const score = mojibakeScore(candidate);
      if (score < bestScore && /[㐀-鿿]/.test(candidate)) {
        best = candidate;
        bestScore = score;
      }
    } catch {}
  }
  return best;
}

export function localizeChineseTerms(text) {
  return String(text ?? "").replace(/相互依赖/g, "互相依赖").replace(/互赖/g, "互相依赖");
}

export function cleanUserText(value, fallback = "", maxLength = 500) {
  return localizeChineseTerms(tryRepairMojibake(value))
    .replace(/\x1b\[[0-9;]*m/g, "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, maxLength) || fallback;
}

// ---------- 样式标准化 ----------

export function canonicalVideoStyle(value, fallback = "whiteboard") {
  const raw = String(value ?? fallback ?? "whiteboard").trim().toLowerCase();
  const style = VIDEO_STYLE_ALIASES.get(raw) ?? raw;
  if (!ENABLE_ALL_STYLE_OPTIONS && style !== ACTIVE_VIDEO_STYLE) return ACTIVE_VIDEO_STYLE;
  return GOLPO_VIDEO_STYLES.has(style) ? style : fallback;
}

export function normalizePenStyle(value, fallback = "marker") {
  const style = String(value ?? fallback ?? "marker").trim().toLowerCase();
  if (!ENABLE_ALL_STYLE_OPTIONS && style !== ACTIVE_PEN_STYLE) return ACTIVE_PEN_STYLE;
  return ["marker", "pen", "fountain_pen", "no_hand"].includes(style) ? style : fallback;
}

// ---------- 视觉规则工具 ----------

export function ruleList(values) {
  return Array.isArray(values)
    ? values.map((value) => String(value || "").trim()).filter(Boolean).join("; ")
    : "";
}

// Re-export storyboard utilities (moved to storyboard-utils.mjs)
export {
  sanitizeStoryboardText,
  collectStoryboardMojibake,
  assertStoryboardEncodingHealthy,
  visualTeachingRulesPrompt,
} from "./storyboard-utils.mjs";

// Re-export music utilities (moved to music.mjs)
export {
  titleFromMusicFilename,
  resolveMusicTrack,
  listMusicTracks,
  ensureLargeModelAvailable,
} from "./music.mjs";

// ---------- 场景分类辅助（从 scene-strategy.mjs re-export） ----------

export {
  sceneTextForStrategy,
  countPatternMatches,
  countSceneLabels,
  explicitRasterStrategy,
  sceneBoardMode,
  sceneHandUsage,
  sceneVideoStyle,
  sceneVisualStyle,
  sceneShouldDirectRender,
  shouldGenerateReferenceImage,
  normalizeBase64Image,
  isProbablyBase64Image,
  sceneLocalImageBuffer,
} from "./scene-strategy.mjs";

// ---------- 通用工具 ----------

export function makeSlug(value) {
  return String(value || "video")
    .normalize("NFKC")
    .replace(/[^\p{L}\p{N}_-]+/gu, "_")
    .replace(/^_+|_+$/g, "")
    .slice(0, 80) || "video";
}

export function safeAssetSegment(value, fallback) {
  return (
    String(value ?? fallback)
      .normalize("NFKC")
      .replace(/[^a-zA-Z0-9_-]+/g, "_")
      .replace(/^_+|_+$/g, "")
      .slice(0, 80) || fallback
  );
}

export function isInside(child, parent) {
  const resolvedChild = resolve(child);
  const resolvedParent = resolve(parent);
  return resolvedChild === resolvedParent || resolvedChild.startsWith(resolvedParent + "\\");
}
