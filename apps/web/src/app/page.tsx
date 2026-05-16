import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen bg-[--bg-base] text-[--fg-default]">
      {/* Nav */}
      <nav className="flex items-center justify-between px-20 h-16 border-b border-[--border-subtle] bg-[--bg-base]">
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-gradient-to-br from-purple-500 to-pink-500" />
          <span className="text-lg font-bold tracking-tight">ExplainFlow</span>
        </div>
        <div className="flex items-center gap-8 text-sm text-[--fg-muted]">
          <a href="#features" className="hover:text-[--fg-default] transition-colors">功能</a>
          <a href="#how" className="hover:text-[--fg-default] transition-colors">使用流程</a>
        </div>
        <Link
          href="/studio"
          className="h-10 px-5 rounded-md bg-purple-500 hover:bg-purple-400 text-white text-sm font-medium inline-flex items-center transition-colors"
        >
          免费开始
        </Link>
      </nav>

      {/* Hero */}
      <section className="relative flex flex-col items-center text-center px-20 pt-24 pb-16 overflow-hidden">
        <div className="absolute top-10 left-1/4 w-96 h-64 bg-purple-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute top-20 right-1/4 w-80 h-56 bg-pink-500/8 rounded-full blur-3xl pointer-events-none" />

        <div className="relative z-10 flex flex-col items-center gap-7 max-w-4xl">
          <span className="inline-flex items-center gap-2 text-xs font-mono px-3 py-1 rounded-full border border-purple-500/50 text-purple-400 bg-purple-950/30">
            ✦ AI/ML 概念白板动画生成器
          </span>

          <h1 className="text-6xl font-bold leading-tight tracking-tight">
            把复杂概念变成
            <br />
            <span className="bg-gradient-to-r from-purple-400 via-pink-400 to-cyan-400 bg-clip-text text-transparent">
              Khan Academy 风格动画
            </span>
          </h1>

          <p className="text-lg text-[--fg-muted] leading-relaxed max-w-xl">
            输入 Prompt 或 Markdown，AI 自动生成中文白板讲解视频。梯度下降、Attention、Transformer，秒级出片。
          </p>

          <div className="flex items-center gap-4">
            <Link
              href="/studio"
              className="h-12 px-8 rounded-md bg-purple-500 hover:bg-purple-400 text-white font-semibold text-base inline-flex items-center gap-2 transition-colors shadow-lg shadow-purple-900/30"
            >
              ✦ 免费开始创作
            </Link>
            <a
              href="#how"
              className="h-12 px-8 rounded-md border border-[--border-default] hover:border-purple-500 text-[--fg-muted] hover:text-[--fg-default] text-base inline-flex items-center transition-colors"
            >
              ▶ 查看流程
            </a>
          </div>
        </div>

        {/* Demo card */}
        <div className="relative z-10 mt-16 w-full max-w-4xl rounded-2xl border border-[--border-default] bg-[--bg-elevated] overflow-hidden shadow-2xl shadow-purple-900/20">
          <div className="flex items-center gap-2 px-4 h-10 bg-[--bg-surface] border-b border-[--border-subtle]">
            <span className="w-3 h-3 rounded-full bg-red-500/70" />
            <span className="w-3 h-3 rounded-full bg-yellow-500/70" />
            <span className="w-3 h-3 rounded-full bg-green-500/70" />
            <span className="ml-3 text-xs font-mono text-[--fg-muted]">ExplainFlow Studio — 梯度下降</span>
          </div>
          <div className="h-64 flex items-center justify-center bg-[--bg-base] p-8">
            <div className="flex flex-col items-center gap-5">
              <h3 className="text-2xl font-bold">梯度下降 Gradient Descent</h3>
              <div className="px-5 py-3 rounded-xl border border-purple-500/40 bg-purple-950/20">
                <code className="text-lg font-mono text-purple-400">θ := θ − α · ∇L(θ)</code>
              </div>
              <div className="flex items-center gap-6">
                {[
                  { label: "θ₀", size: 48, color: "#a855f7" },
                  { label: "→" },
                  { label: "θ₁", size: 36, color: "#ec4899" },
                  { label: "→" },
                  { label: "θ*", size: 24, color: "#06b6d4" },
                ].map((item, i) =>
                  "size" in item ? (
                    <div key={i} className="flex flex-col items-center gap-1">
                      <div className="rounded-full" style={{ width: item.size, height: item.size, background: item.color, opacity: 0.8 }} />
                      <span className="text-xs font-mono text-[--fg-muted]">{item.label}</span>
                    </div>
                  ) : (
                    <span key={i} className="text-xl text-pink-500">→</span>
                  )
                )}
              </div>
              <p className="text-sm text-[--fg-muted]">↑ 参数逐步收敛到最优解</p>
            </div>
          </div>
        </div>
      </section>

      {/* Social proof bar */}
      <section className="border-y border-[--border-subtle] bg-[--bg-surface] py-4">
        <div className="flex items-center justify-center gap-12 text-sm">
          {[
            { label: "UP主使用", value: "2,000+" },
            { label: "B 站播放量", value: "1,000万+" },
            { label: "AI/ML 主题", value: "10+" },
          ].map((item, i) => (
            <div key={i} className="flex items-center gap-3">
              {i > 0 && <div className="w-px h-5 bg-[--border-default]" />}
              <span className="text-[--fg-muted]">{item.label}</span>
              <span className="font-bold">{item.value}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="px-20 py-20">
        <div className="text-center mb-14">
          <h2 className="text-4xl font-bold mb-4">为什么选择 ExplainFlow？</h2>
          <p className="text-[--fg-muted] text-lg">专为国内 AI/ML 技术博主设计，从 Prompt 到发布，全程 AI 辅助</p>
        </div>
        <div className="grid grid-cols-3 gap-6 max-w-4xl mx-auto">
          {[
            { icon: "✦", color: "purple", title: "AI 自动规划", desc: "LLM 深度理解 AI/ML 概念，自动规划教学顺序和 Explain 图谱，无需手动编排。" },
            { icon: "◈", color: "pink", title: "Khan Academy 风格", desc: "一键生成中文白板动画，手绘质感、中文字幕，直接适配 B 站和知乎。" },
            { icon: "⚡", color: "cyan", title: "秒级生成导出", desc: "1-3 分钟 MP4 1080p，横屏 + 竖屏 Shorts 双格式，生成完直接发布。" },
          ].map((f) => (
            <div key={f.title} className="rounded-2xl border border-[--border-subtle] bg-[--bg-surface] p-6 space-y-4">
              <div className={`w-11 h-11 rounded-xl flex items-center justify-center text-lg ${
                f.color === "purple" ? "bg-purple-950/40 text-purple-400" :
                f.color === "pink" ? "bg-pink-950/40 text-pink-400" :
                "bg-cyan-950/40 text-cyan-400"
              }`}>{f.icon}</div>
              <h3 className="text-lg font-semibold">{f.title}</h3>
              <p className="text-sm text-[--fg-muted] leading-relaxed">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how" className="px-20 py-20 bg-[--bg-surface]">
        <div className="text-center mb-14">
          <h2 className="text-4xl font-bold mb-4">三步生成讲解视频</h2>
        </div>
        <div className="flex items-start justify-center max-w-3xl mx-auto">
          {[
            { step: "1", title: "输入 Prompt", desc: "用中文描述想讲的 AI/ML 概念，或粘贴 Markdown 笔记" },
            null,
            { step: "2", title: "AI 生成动画", desc: "LLM 理解概念，自动规划 Explain 图谱和白板动画脚本" },
            null,
            { step: "3", title: "编辑并下载", desc: "在 Storyboard 中微调文案节奏，一键导出 1080p MP4" },
          ].map((item, i) =>
            !item ? (
              <div key={i} className="flex items-center justify-center w-16 pt-5 text-2xl text-purple-500">→</div>
            ) : (
              <div key={i} className="flex-1 flex flex-col items-center text-center gap-4 px-4">
                <div className="w-12 h-12 rounded-full bg-purple-500/20 border-2 border-purple-500 flex items-center justify-center text-purple-400 font-bold text-lg">
                  {item.step}
                </div>
                <h3 className="text-lg font-semibold">{item.title}</h3>
                <p className="text-sm text-[--fg-muted] leading-relaxed">{item.desc}</p>
              </div>
            )
          )}
        </div>
      </section>

      {/* CTA */}
      <section className="relative px-20 py-24 text-center overflow-hidden">
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
          <div className="w-96 h-64 bg-purple-500/8 rounded-full blur-3xl" />
        </div>
        <h2 className="relative text-5xl font-bold mb-6">现在开始，把 Prompt 变成视频</h2>
        <p className="relative text-[--fg-muted] text-lg mb-10">免费使用，无需信用卡，1 分钟出片</p>
        <Link
          href="/studio"
          className="inline-flex items-center gap-2 h-14 px-10 rounded-md bg-purple-500 hover:bg-purple-400 text-white font-semibold text-lg transition-colors"
        >
          ✦ 免费开始创作
        </Link>
      </section>

      {/* Footer */}
      <footer className="border-t border-[--border-subtle] bg-[--bg-surface] px-20 h-20 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-5 h-5 rounded bg-gradient-to-br from-purple-500 to-pink-500" />
          <span className="text-sm font-bold">ExplainFlow</span>
        </div>
        <p className="text-sm text-[--fg-muted]">© 2026 ExplainFlow. All rights reserved.</p>
        <div className="flex gap-6 text-sm text-[--fg-muted]">
          <a href="#" className="hover:text-[--fg-default]">隐私政策</a>
          <a href="#" className="hover:text-[--fg-default]">使用条款</a>
        </div>
      </footer>
    </main>
  );
}
