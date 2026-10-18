import { existsSync, mkdirSync, copyFileSync, readdirSync } from "fs";
import { createRequire } from "module";
import { dirname, join } from "path";
import { spawnSync } from "child_process";
import { OUTPUT_DIR } from "./config.mjs";

export function nvencArgs({ args }) {
  if (!args.includes("libx264")) return args;
  const result = [];
  for (let i = 0; i < args.length; i++) {
    if (["-crf", "-preset"].includes(args[i])) { i++; continue; }
    result.push(args[i] === "libx264" ? "h264_nvenc" : args[i]);
  }
  result.splice(result.length - 1, 0, "-preset", "p4", "-cq", "20");
  return result;
}

let cached;
export function nvencOptions() {
  if (cached) return cached;
  const ffmpeg = join(OUTPUT_DIR, ".tools", "ffmpeg.exe");
  if (process.platform !== "win32" || !existsSync(ffmpeg)) return (cached = {});
  const probe = spawnSync(ffmpeg, ["-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=s=960x540:r=24", "-frames:v", "1", "-c:v", "h264_nvenc", "-f", "null", "-"], { timeout: 15000, windowsHide: true });
  if (probe.status !== 0) {
    console.warn("[render] NVENC unavailable; using CPU encoding", probe.stderr?.toString());
    return (cached = {});
  }
  const require = createRequire(import.meta.url);
  const bundled = dirname(require.resolve("@remotion/compositor-win32-x64-msvc/package.json"));
  const binariesDirectory = join(OUTPUT_DIR, ".tools", "remotion-nvenc");
  mkdirSync(binariesDirectory, { recursive: true });
  for (const file of readdirSync(bundled)) {
    if (/\.(exe|dll)$/.test(file) && file !== "ffmpeg.exe") copyFileSync(join(bundled, file), join(binariesDirectory, file));
  }
  copyFileSync(ffmpeg, join(binariesDirectory, "ffmpeg.exe"));
  console.log("[render] NVIDIA h264_nvenc enabled (preset p4, CQ 20)");
  // The external GPL build has no libfdk_aac, which Remotion uses for AAC.
  return (cached = { binariesDirectory, ffmpegOverride: nvencArgs, audioCodec: "mp3" });
}
