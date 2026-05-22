/**
 * tts-core.mjs — TTS 并发控制、文本标准化、请求缓存、音频探测
 * 依赖: config.mjs, utils.mjs
 */
import { execFile } from "child_process";
import { existsSync, statSync } from "fs";
import { basename, extname, join } from "path";
import { createHash } from "crypto";
import { promisify } from "util";
import {
  AUDIO_DIR,
  FFMPEG_BINARY,
  FFPROBE_BINARY,
  MUSIC_DIR,
  PYTHON_API,
  TTS_CONCURRENCY,
  TTS_MAX_ATTEMPTS,
} from "./config.mjs";
import {
  cleanUserText,
  postBuffer,
  resolveMusicTrack,
  sleep,
} from "./utils.mjs";

const execFileAsync = promisify(execFile);
const ttsInFlight = new Map();
let activeTtsRequests = 0;
const ttsWaiters = [];

// ---------------------------------------------------------------------------
// TTS 并发控制
// ---------------------------------------------------------------------------

export async function acquireTtsSlot() {
  if (activeTtsRequests < TTS_CONCURRENCY) { activeTtsRequests += 1; return; }
  await new Promise((resolvePromise) => ttsWaiters.push(resolvePromise));
  activeTtsRequests += 1;
}

export function releaseTtsSlot() {
  activeTtsRequests = Math.max(0, activeTtsRequests - 1);
  const next = ttsWaiters.shift();
  if (next) next();
}

export async function withTtsSlot(fn) {
  await acquireTtsSlot();
  try { return await fn(); } finally { releaseTtsSlot(); }
}

// ---------------------------------------------------------------------------
// 文本标准化
// ---------------------------------------------------------------------------

export function normalizeTextForTts(text) {
  return String(text ?? "")
    .replace(/\bV_G\b/g, "V G").replace(/\bV_th\b/gi, "V threshold")
    .replace(/\bV_DS\b/g, "V D S").replace(/\bI_D\b/g, "I D")
    .replace(/\bW_eff\b/g, "W effective")
    .replace(/>=/g, " greater than or equal to ").replace(/<=/g, " less than or equal to ")
    .replace(/>/g, " greater than ").replace(/</g, " less than ").replace(/=/g, " equals ")
    .replace(/[{}[\]`*_#~^|\\]/g, " ").replace(/\s+/g, " ").trim();
}

export function cleanNarrationText(text) {
  let value = cleanUserText(text, "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  const replacements = [
    [/^\s*(?:首先|先|接着|然后|再|最后|这里|现在|我们|把|请)?\s*(?:先|再)?\s*(?:画|绘制|写|写上|标出|标注|圈出|框出|显示|展示|呈现|看|看到)\s*(?:左边|右边|上方|下方|中间|图中|画面中|这个图|这张图)?\s*(?:的|出|上)?\s*/i, ""],
    [/(?:先|再|然后|接着|最后)\s*(?:画|绘制|写|写上|标出|标注|圈出|框出|显示|展示|呈现)\s*/gi, ""],
    [/(?:左边|右边|上方|下方|中间|旁边|图中|画面中)\s*(?:画|绘制|写|写上|标出|标注|可以看到|看到)\s*/gi, ""],
    [/(?:这一步|这个 beat|此时)\s*(?:同步)?\s*(?:说|讲|说明|解释)\s*/gi, ""],
    [/(?:我们|这里|现在)\s*(?:来|可以)?\s*(?:画|绘制|写|写上|标出|标注|看)\s*/gi, ""],
  ];
  for (const [pattern, replacement] of replacements) value = value.replace(pattern, replacement);
  value = value.replace(/\s+/g, " ").replace(/^[ ：:，,。]+|[ ：:，,。]+$/g, "").trim();
  if (value && !/[。！？.!?]$/.test(value)) value += "。";
  return value;
}

export function trimNarrationToChars(text, maxChars) {
  const limit = Math.max(0, Number(maxChars) || 0);
  const source = cleanNarrationText(text);
  if (!limit || source.length <= limit) return source;
  const sentences = source.match(/[^。！？.!?]+[。！？.!?]?/g) ?? [source];
  let result = "";
  for (const sentence of sentences) {
    const next = `${result}${sentence}`;
    if (next.length <= limit) {
      result = next;
    } else if (!result && limit >= 28) {
      let candidate = sentence.slice(0, limit);
      const cut = Math.max(
        candidate.lastIndexOf("，"), candidate.lastIndexOf(","),
        candidate.lastIndexOf("；"), candidate.lastIndexOf(";"),
        candidate.lastIndexOf("："), candidate.lastIndexOf(":"), candidate.lastIndexOf("、"),
      );
      if (cut > Math.floor(limit * 0.45)) candidate = candidate.slice(0, cut);
      result = candidate.replace(/[，,；;：:、\s]+$/g, "");
      break;
    } else { break; }
  }
  result = result.replace(/[，,；;：:、\s]+$/g, "");
  if (result && !/[。！？.!?]$/.test(result)) result += "。";
  if (result) return result;
  const firstSentence = sentences[0]?.trim() || source;
  if (firstSentence.length <= Math.max(limit * 2, 96)) return firstSentence;
  return `${source.slice(0, limit).replace(/[，,；;：:、\s]+$/g, "")}。`;
}

export function splitNarrationSentences(text) {
  const source = cleanNarrationText(text);
  if (!source) return [];
  return (source.match(/[^。！？!?]+[。！？!?]?/g) ?? [source])
    .map((part) => cleanNarrationText(part)).filter(Boolean);
}

export function distributeNarrationAcrossBeats(sceneNarration, beatCount) {
  const count = Math.max(1, Number(beatCount) || 1);
  const source = cleanNarrationText(sceneNarration);
  if (!source) return [];
  if (count === 1) return [source];
  const sentences = splitNarrationSentences(source);
  if (sentences.length === 0) return [source];
  const chunks = Array.from({ length: count }, () => []);
  const totalChars = sentences.reduce((sum, s) => sum + s.length, 0);
  const targetChars = Math.max(1, totalChars / count);
  let chunkIndex = 0, chunkChars = 0;
  for (const [sentenceIndex, sentence] of sentences.entries()) {
    const remainingSentences = sentences.length - sentenceIndex;
    const remainingSlots = count - chunkIndex - 1;
    if (chunkIndex < count - 1 && chunkChars > 0 && chunkChars + sentence.length > targetChars && remainingSentences > remainingSlots) {
      chunkIndex += 1; chunkChars = 0;
    }
    chunks[chunkIndex].push(sentence);
    chunkChars += sentence.length;
  }
  return chunks.map((chunk) => cleanNarrationText(chunk.join(""))).filter(Boolean);
}

export function normalizeVoiceKey(voice) {
  const value = String(voice ?? "").trim();
  if (!value) return "xiaoxiao";
  const normalized = value.toLowerCase().replace(/[^a-z0-9]/g, "");
  const aliases = new Map([
    ["xiaoxiao", "xiaoxiao"], ["zhcnxiaoxiaoneural", "xiaoxiao"],
    ["yunxi", "yunxi"], ["zhcnyunxineural", "yunxi"],
    ["xiaoyi", "xiaoyi"], ["zhcnxiaoyineural", "xiaoyi"],
  ]);
  return aliases.get(normalized) ?? value;
}

// ---------------------------------------------------------------------------
// TTS 请求与缓存
// ---------------------------------------------------------------------------

export async function requestTtsAudio(narration, voice, sceneId) {
  const speechText = normalizeTextForTts(narration);
  let lastError = null;
  for (let attempt = 1; attempt <= TTS_MAX_ATTEMPTS; attempt += 1) {
    try {
      const audio = await withTtsSlot(() =>
        postBuffer(`${PYTHON_API}/narration/synthesize`, { text: speechText || narration, voice }),
      );
      if (!Buffer.isBuffer(audio) || audio.length < 512) throw new Error("No usable audio was received from TTS");
      return audio;
    } catch (err) {
      lastError = err;
      if (attempt < TTS_MAX_ATTEMPTS) {
        console.warn(`[tts] retry ${attempt}/${TTS_MAX_ATTEMPTS - 1} for ${sceneId}: ${err.message}`);
        await sleep(1200 + attempt * 1800);
      }
    }
  }
  throw lastError ?? new Error("TTS failed");
}

export function ttsCacheFilename(text, voice) {
  const hash = createHash("sha1")
    .update(JSON.stringify({ text: String(text ?? ""), voice: String(voice ?? "") }))
    .digest("hex").slice(0, 20);
  return `tts_${hash}.mp3`;
}

export function estimateNarrationSeconds(text) {
  const source = String(text ?? "").trim();
  if (!source) return 0;
  const cjk = [...source].filter((char) => /[㐀-鿿]/.test(char)).length;
  const latinWords = (source.match(/[A-Za-z0-9]+/g) ?? []).length;
  const punctuationPauses = (source.match(/[。！？；.!?;]/g) ?? []).length * 0.25;
  return Math.max(2.0, cjk * 0.18 + latinWords * 0.32 + punctuationPauses + 0.8);
}

// Re-export in-flight map for tts.mjs to share the same Map instance
export { ttsInFlight };

// ---------------------------------------------------------------------------
// 音频探测
// ---------------------------------------------------------------------------

export async function probeAudioDurationSeconds(filePath) {
  try {
    const { stdout } = await execFileAsync(
      FFPROBE_BINARY,
      ["-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", filePath],
      { windowsHide: true, timeout: 30000 },
    );
    const parsed = Number.parseFloat(String(stdout).trim());
    return Number.isFinite(parsed) && parsed > 0 ? parsed : 0;
  } catch (err) {
    console.warn(`[tts] ffprobe failed for ${basename(filePath)}: ${err.message}`);
    return 0;
  }
}

export async function probePlayableAudio(filePath) {
  try {
    const { stdout } = await execFileAsync(
      FFPROBE_BINARY,
      ["-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name,sample_rate,channels:format=duration", "-of", "json", filePath],
      { windowsHide: true, timeout: 30000 },
    );
    const parsed = JSON.parse(stdout || "{}");
    const stream = Array.isArray(parsed.streams) ? parsed.streams[0] : null;
    const duration = Number.parseFloat(String(parsed.format?.duration ?? "0"));
    return Boolean(stream?.codec_name && Number.isFinite(duration) && duration > 0);
  } catch (err) {
    console.warn(`[music] ffprobe rejected ${basename(filePath)}: ${err.message}`);
    return false;
  }
}

export async function probeMediaInfo(filePath) {
  const { stdout } = await execFileAsync(
    FFPROBE_BINARY,
    ["-v", "error", "-show_entries", "format=duration:stream=codec_type,codec_name,width,height", "-of", "json", filePath],
    { windowsHide: true, timeout: 30000 },
  );
  const parsed = JSON.parse(stdout || "{}");
  const duration = Number.parseFloat(String(parsed.format?.duration ?? "0"));
  const streams = Array.isArray(parsed.streams) ? parsed.streams : [];
  return {
    durationSeconds: Number.isFinite(duration) && duration > 0 ? duration : 0,
    hasAudio: streams.some((s) => s.codec_type === "audio"),
    hasVideo: streams.some((s) => s.codec_type === "video"),
    streams,
  };
}

export async function normalizeMusicTrackForRemotion(track) {
  if (!track) return null;
  const ext = extname(track.filePath).toLowerCase();
  if (ext !== ".mp3") return track;
  const safeName = `${basename(track.id, ext)}_remotion.wav`;
  const outPath = join(MUSIC_DIR, safeName);
  if (!existsSync(outPath) || statSync(outPath).size <= 0) {
    await execFileAsync(
      FFMPEG_BINARY,
      ["-y", "-i", track.filePath, "-vn", "-acodec", "pcm_s16le", "-ar", "48000", "-ac", "2", outPath],
      { windowsHide: true, timeout: 120000 },
    );
  }
  const normalized = resolveMusicTrack(safeName);
  return normalized || track;
}
