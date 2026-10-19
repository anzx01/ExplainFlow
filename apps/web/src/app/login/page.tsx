"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { loginUser, registerUser, saveToken } from "@/lib/auth";

type Mode = "login" | "register";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<Mode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const inputCls =
    "h-10 w-full px-3 rounded-md bg-[--bg-elevated] border border-[--border-default] text-sm text-[--fg-default] placeholder:text-[--fg-muted] focus:outline-none focus:border-purple-500 transition-colors";
  const labelCls = "block text-xs font-medium text-[--fg-muted] mb-1.5";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res =
        mode === "login"
          ? await loginUser(username.trim(), password)
          : await registerUser(username.trim(), password, displayName.trim());
      saveToken(res.token);
      router.push("/console");
    } catch (err) {
      setError((err as Error).message || "请求失败,请稍后再试");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-[--bg-base] text-[--fg-default] px-4">
      <Link href="/" className="flex items-center gap-2.5 mb-8">
        <div className="w-8 h-8 rounded-md bg-gradient-to-br from-purple-500 to-pink-500" />
        <span className="text-xl font-bold tracking-tight">ExplainFlow</span>
      </Link>

      <div className="w-full max-w-sm rounded-2xl border border-[--border-default] bg-[--bg-surface] p-7">
        <div className="flex gap-1 p-1 rounded-lg bg-[--bg-elevated] mb-6">
          {(["login", "register"] as Mode[]).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => {
                setMode(m);
                setError(null);
              }}
              className={`flex-1 h-8 rounded-md text-sm transition-colors ${
                mode === m ? "bg-purple-500 text-white font-medium" : "text-[--fg-muted] hover:text-[--fg-default]"
              }`}
            >
              {m === "login" ? "登录" : "注册"}
            </button>
          ))}
        </div>

        <form onSubmit={submit} className="flex flex-col gap-4">
          {mode === "register" && (
            <div>
              <label className={labelCls}>昵称(可选)</label>
              <input className={inputCls} value={displayName} onChange={(e) => setDisplayName(e.target.value)} placeholder="展示在控制台的名称" maxLength={32} />
            </div>
          )}
          <div>
            <label className={labelCls}>用户名</label>
            <input className={inputCls} value={username} onChange={(e) => setUsername(e.target.value)} placeholder="中文/字母/数字,2-32 个字符" autoComplete="username" />
          </div>
          <div>
            <label className={labelCls}>密码</label>
            <input className={inputCls} type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="至少 6 个字符" autoComplete={mode === "login" ? "current-password" : "new-password"} />
          </div>

          {error && (
            <p className="rounded-md border border-red-500/40 bg-red-950/20 px-3 py-2 text-xs text-red-300">{error}</p>
          )}

          <button
            type="submit"
            disabled={busy || !username.trim() || !password}
            className="h-10 rounded-md bg-purple-500 hover:bg-purple-400 disabled:opacity-50 text-white text-sm font-medium transition-colors"
          >
            {busy ? "请稍候..." : mode === "login" ? "登录" : "注册并登录"}
          </button>
        </form>

        <p className="mt-5 text-[11px] text-[--fg-muted] leading-relaxed">
          账号保存在本机(data/users.json),当前为本地模式;未登录也可在公共模式下使用控制台。
        </p>
      </div>

      <Link href="/console" className="mt-6 text-xs text-[--fg-muted] hover:text-[--fg-default] transition-colors">
        先不登录,进入控制台 →
      </Link>
    </main>
  );
}
