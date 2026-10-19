"use client";

import { useCallback, useEffect, useState } from "react";
import { getAppSettings, generateLocalTestVideo, testLocalText2Video, updateAppSettings } from "@/lib/api";
import type { AppSettingsView, Text2VideoGenerateResult, Text2VideoTestResult } from "@/lib/types";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8010";

type SecretState = "" | "(unchanged)" | (string & {});

function isSavedSecret(v: unknown): v is { set: boolean; tail?: string } {
  return typeof v === "object" && v !== null && "set" in v;
}

export default function SettingsPage() {
  const [view, setView] = useState<AppSettingsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);

  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  const [llmKey, setLlmKey] = useState<SecretState>("");
  const [llmModel, setLlmModel] = useState("");
  const [coderModel, setCoderModel] = useState("");
  const [imageProvider, setImageProvider] = useState("local");
  const [imgBaseUrl, setImgBaseUrl] = useState("");
  const [imgModel, setImgModel] = useState("");
  const [cT2vBaseUrl, setCT2vBaseUrl] = useState("");
  const [cT2vModel, setCT2vModel] = useState("");
  const [cT2vKey, setCT2vKey] = useState<SecretState>("");
  const [cT2vGen, setCT2vGen] = useState<Text2VideoGenerateResult | null>(null);
  const [cT2vGenerating, setCT2vGenerating] = useState(false);
  const [arkKey, setArkKey] = useState<SecretState>("");
  const [t2vBaseUrl, setT2vBaseUrl] = useState("");
  const [t2vModel, setT2vModel] = useState("");
  const [t2vKey, setT2vKey] = useState<SecretState>("");
  const [t2vResult, setT2vResult] = useState<Text2VideoTestResult | null>(null);
  const [t2vTesting, setT2vTesting] = useState(false);
  const [t2vPrompt, setT2vPrompt] = useState("手绘白板风格动画:一列小火车从左向右行驶,蜡笔质感,简洁背景");
  const [t2vGen, setT2vGen] = useState<Text2VideoGenerateResult | null>(null);
  const [t2vGenerating, setT2vGenerating] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await getAppSettings();
      setView(data);
      const savedMap = data.saved as Record<string, unknown>;
      setLlmBaseUrl(data.effective.llm_base_url);
      setLlmModel(data.effective.llm_model);
      setCoderModel(data.effective.coder_model);
      setImageProvider(data.effective.imagegen_provider);
      setImgBaseUrl(data.effective.imagegen_base_url);
      setImgModel(data.effective.imagegen_model);
      setCT2vBaseUrl(data.effective.cloud_text2video_base_url);
      setCT2vModel(data.effective.cloud_text2video_model);
      setT2vBaseUrl(data.effective.local_text2video_base_url);
      setT2vModel(data.effective.local_text2video_model);
      const llmKeySaved = savedMap["llm_api_key"];
      setLlmKey(isSavedSecret(llmKeySaved) ? "(unchanged)" : "");
      const arkSaved = savedMap["ark_api_key"];
      setArkKey(isSavedSecret(arkSaved) ? "(unchanged)" : "");
      const t2vSaved = savedMap["local_text2video_api_key"];
      setT2vKey(isSavedSecret(t2vSaved) ? "(unchanged)" : "");
      const cT2vSaved = savedMap["cloud_text2video_api_key"];
      setCT2vKey(isSavedSecret(cT2vSaved) ? "(unchanged)" : "");
    } catch (err) {
      setError((err as Error).message);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async () => {
    setBusy(true);
    setSaved(false);
    setError(null);
    try {
      const values: Record<string, string> = {
        llm_base_url: llmBaseUrl.trim(),
        llm_model: llmModel.trim(),
        coder_model: coderModel.trim(),
        imagegen_provider: imageProvider,
        imagegen_base_url: imgBaseUrl.trim(),
        imagegen_model: imgModel.trim(),
        cloud_text2video_base_url: cT2vBaseUrl.trim(),
        cloud_text2video_model: cT2vModel.trim(),
        local_text2video_base_url: t2vBaseUrl.trim(),
        local_text2video_model: t2vModel.trim(),
      };
      if (llmKey && llmKey !== "(unchanged)") values["llm_api_key"] = llmKey.trim();
      if (arkKey && arkKey !== "(unchanged)") values["ark_api_key"] = arkKey.trim();
      if (t2vKey && t2vKey !== "(unchanged)") values["local_text2video_api_key"] = t2vKey.trim();
      if (cT2vKey && cT2vKey !== "(unchanged)") values["cloud_text2video_api_key"] = cT2vKey.trim();
      const data = await updateAppSettings(values);
      setView(data);
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const handleT2vTest = async () => {
    setT2vTesting(true);
    setT2vResult(null);
    try {
      const key = t2vKey && t2vKey !== "(unchanged)" ? t2vKey.trim() : undefined;
      setT2vResult(await testLocalText2Video(t2vBaseUrl.trim(), key));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setT2vTesting(false);
    }
  };

  const handleT2vGenerate = async () => {
    setT2vGenerating(true);
    setT2vGen(null);
    setError(null);
    try {
      const key = t2vKey && t2vKey !== "(unchanged)" ? t2vKey.trim() : undefined;
      setT2vGen(await generateLocalTestVideo(t2vPrompt.trim(), t2vBaseUrl.trim(), t2vModel.trim(), key));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setT2vGenerating(false);
    }
  };

  const handleCT2vGenerate = async () => {
    setCT2vGenerating(true);
    setCT2vGen(null);
    setError(null);
    try {
      const key = cT2vKey && cT2vKey !== "(unchanged)" ? cT2vKey.trim() : undefined;
      setCT2vGen(await generateLocalTestVideo("云端文生视频链路测试:一段简洁的动画", cT2vBaseUrl.trim(), cT2vModel.trim(), key));
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setCT2vGenerating(false);
    }
  };

  const inputCls =
    "h-9 w-full px-3 rounded-md bg-[--bg-elevated] border border-[--border-default] text-sm text-[--fg-default] placeholder:text-[--fg-muted] focus:outline-none focus:border-purple-500 transition-colors";
  const labelCls = "block text-xs font-medium text-[--fg-muted] mb-1.5";

  return (
    <div className="flex flex-col h-full bg-[--bg-base] text-[--fg-default] overflow-y-auto">
      <header className="flex items-center gap-2.5 px-6 h-14 border-b border-[--border-subtle] bg-[--bg-surface] flex-shrink-0">
        <div className="w-6 h-6 rounded-md bg-gradient-to-br from-purple-500 to-pink-500" />
        <span className="font-semibold">设置</span>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-10 flex flex-col gap-8">
        {error && (
          <div className="rounded-md border border-red-500/40 bg-red-950/20 px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        {/* 云端大模型 */}
        <section className="rounded-xl border border-[--border-default] bg-[--bg-surface] p-6">
          <h2 className="text-base font-semibold mb-1">大模型(云端)</h2>
          <p className="text-xs text-[--fg-muted] mb-4">
            任意 OpenAI 兼容服务(DeepSeek / 通义 / OpenAI / 本机 vLLM 等)。留空则沿用 .env 默认,保存后立即生效,无需重启。
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className={labelCls}>Base URL</label>
              <input className={inputCls} value={llmBaseUrl} onChange={(e) => setLlmBaseUrl(e.target.value)} placeholder="https://api.deepseek.com/v1" />
            </div>
            <div>
              <label className={labelCls}>API Key</label>
              <input className={inputCls} type="password" value={llmKey} onChange={(e) => setLlmKey(e.target.value)} placeholder="sk-..." />
            </div>
            <div>
              <label className={labelCls}>规划模型</label>
              <input className={inputCls} value={llmModel} onChange={(e) => setLlmModel(e.target.value)} placeholder="deepseek-chat" />
            </div>
            <div className="col-span-2">
              <label className={labelCls}>代码生成模型</label>
              <input className={inputCls} value={coderModel} onChange={(e) => setCoderModel(e.target.value)} placeholder="deepseek-coder" />
            </div>

            <div className="col-span-2 mt-4 pt-4 border-t border-[--border-subtle]">
              <p className="text-sm font-medium mb-3">文生图模型(云端,Ark/OpenAI 兼容)</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Base URL</label>
                  <input className={inputCls} value={imgBaseUrl} onChange={(e) => setImgBaseUrl(e.target.value)} placeholder="https://ark.cn-beijing.volces.com/api/v3" />
                </div>
                <div>
                  <label className={labelCls}>模型名</label>
                  <input className={inputCls} value={imgModel} onChange={(e) => setImgModel(e.target.value)} placeholder="doubao-seedream-5-0-260128" />
                </div>
              </div>
              <p className="text-xs text-[--fg-muted] mt-2">API Key 在下方「图像生成」板块配置;provider 选 ark / local_then_ark 时生效。</p>
            </div>

            <div className="col-span-2 mt-4 pt-4 border-t border-[--border-subtle]">
              <p className="text-sm font-medium mb-3">文生视频模型(云端,OpenAI 兼容 /v1/videos)</p>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelCls}>Base URL</label>
                  <input className={inputCls} value={cT2vBaseUrl} onChange={(e) => setCT2vBaseUrl(e.target.value)} placeholder="https://your-video-api.example.com" />
                </div>
                <div>
                  <label className={labelCls}>模型名</label>
                  <input className={inputCls} value={cT2vModel} onChange={(e) => setCT2vModel(e.target.value)} placeholder="sora-2 / wan2.2-api" />
                </div>
                <div className="col-span-2">
                  <label className={labelCls}>API Key</label>
                  <input className={inputCls} type="password" value={cT2vKey} onChange={(e) => setCT2vKey(e.target.value)} placeholder="sk-..." />
                </div>
              </div>
              <div className="flex items-center gap-3 mt-3 flex-wrap">
                <button
                  onClick={handleCT2vGenerate}
                  disabled={cT2vGenerating || !cT2vBaseUrl.trim() || !cT2vModel.trim()}
                  className="h-9 px-4 rounded-md border border-purple-500/60 text-purple-300 text-xs font-medium disabled:opacity-50 transition-colors hover:bg-purple-950/30"
                >
                  {cT2vGenerating ? "生成中(最长5分钟)..." : "生成测试视频(云端)"}
                </button>
                {cT2vGen && (
                  <span className="text-xs font-mono text-green-400">
                    ✓ {cT2vGen.filename} · {cT2vGen.elapsedSeconds}s · {cT2vGen.model}
                  </span>
                )}
              </div>
              {cT2vGen && (
                <video
                  src={`${API_BASE_URL}${cT2vGen.videoUrl}`}
                  controls autoPlay muted loop playsInline
                  className="mt-3 w-full max-h-64 rounded-md bg-black"
                />
              )}
            </div>
          </div>
        </section>

        {/* 图像生成 */}
        <section className="rounded-xl border border-[--border-default] bg-[--bg-surface] p-6">
          <h2 className="text-base font-semibold mb-1">图像生成</h2>
          <p className="text-xs text-[--fg-muted] mb-4">
            本地 Flux(stable-diffusion.cpp)为默认;可切换火山 Ark 云端生图(需 API Key)。
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className={labelCls}>Provider</label>
              <select className={inputCls} value={imageProvider} onChange={(e) => setImageProvider(e.target.value)}>
                <option value="local">local(本地 Flux,推荐)</option>
                <option value="local_then_ark">local_then_ark(本地优先,失败转 Ark)</option>
                <option value="ark">ark(火山 Seedream)</option>
                <option value="comfyui">comfyui(本地 SD1.5)</option>
              </select>
            </div>
            <div>
              <label className={labelCls}>Ark API Key(仅 Ark 类 provider 需要)</label>
              <input className={inputCls} type="password" value={arkKey} onChange={(e) => setArkKey(e.target.value)} placeholder="留空则沿用 .env" />
            </div>
          </div>
          {view && (
            <p className="text-xs font-mono text-[--fg-muted] mt-3">
              当前生效:{view.effective.imagegen_provider}
              {view.effective.local_text2image_available ? " · 本地文生图可用" : ""}
            </p>
          )}
        </section>

        {/* 本地文生视频 */}
        <section className="rounded-xl border border-[--border-default] bg-[--bg-surface] p-6">
          <h2 className="text-base font-semibold mb-1">本地文生视频(实验性)</h2>
          <p className="text-xs text-[--fg-muted] mb-4">
            配置本地文生视频服务(如 Wan2.2 / FreeVideo 的 OpenAI 兼容端点,支持直接返回视频、内嵌 URL、异步任务三种协议)。保存后可测试连通性,并可直接生成一段测试视频验证调用链路。
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div className="col-span-2">
              <label className={labelCls}>服务地址</label>
              <input className={inputCls} value={t2vBaseUrl} onChange={(e) => setT2vBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8300" />
            </div>
            <div>
              <label className={labelCls}>模型名</label>
              <input className={inputCls} value={t2vModel} onChange={(e) => setT2vModel(e.target.value)} placeholder="wan2.2-t2v" />
            </div>
            <div>
              <label className={labelCls}>API Key(可选)</label>
              <input className={inputCls} type="password" value={t2vKey} onChange={(e) => setT2vKey(e.target.value)} placeholder="本地服务通常留空" />
            </div>
          </div>
          <div className="mt-4">
            <label className={labelCls}>测试提示词</label>
            <input className={inputCls} value={t2vPrompt} onChange={(e) => setT2vPrompt(e.target.value)} />
          </div>
          <div className="flex items-center gap-3 mt-4 flex-wrap">
            <button
              onClick={handleT2vGenerate}
              disabled={t2vGenerating || !t2vBaseUrl.trim() || !t2vModel.trim()}
              className="h-9 px-4 rounded-md bg-purple-500 hover:bg-purple-400 text-white text-xs font-medium disabled:opacity-50 transition-colors"
            >
              {t2vGenerating ? "生成中(最长5分钟)..." : "生成测试视频"}
            </button>
            <button
              onClick={handleT2vTest}
              disabled={t2vTesting || !t2vBaseUrl.trim()}
              className="h-9 px-4 rounded-md border border-[--border-default] hover:border-purple-500 text-sm disabled:opacity-50 transition-colors"
            >
              {t2vTesting ? "测试中..." : "测试连通性"}
            </button>
            {t2vResult && (
              <span className={`text-xs font-mono ${t2vResult.ok ? "text-green-400" : "text-red-400"}`}>
                {t2vResult.ok ? "✓ 可连通" : "✗ 未连通"}
                {t2vResult.probes.map((p) => ` · ${p.path}: ${p.status ?? p.error ?? "?"}`).join("")}
              </span>
            )}
          </div>
          {t2vGen && (
            <div className="mt-4 rounded-lg border border-[--border-default] bg-[--bg-base] p-3">
              <p className="text-xs font-mono text-[--fg-muted] mb-2">
                ✓ 已生成 {t2vGen.filename} · {(t2vGen.sizeBytes / 1048576).toFixed(1)}MB · {t2vGen.elapsedSeconds}s · {t2vGen.model}
              </p>
              <video
                src={`${API_BASE_URL}${t2vGen.videoUrl}`}
                controls
                autoPlay
                muted
                loop
                playsInline
                className="w-full max-h-72 rounded-md bg-black"
              />
            </div>
          )}
        </section>

        <div className="flex items-center gap-4">
          <button
            onClick={handleSave}
            disabled={busy}
            className="h-10 px-6 rounded-md bg-purple-500 hover:bg-purple-400 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {busy ? "保存中..." : "保存设置"}
          </button>
          {saved && <span className="text-sm text-green-400">已保存并生效</span>}
        </div>
      </main>
    </div>
  );
}
