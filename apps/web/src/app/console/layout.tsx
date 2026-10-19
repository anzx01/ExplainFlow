"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { fetchCurrentUser, logoutUser } from "@/lib/auth";
import type { AuthUser } from "@/lib/types";

const NAV = [
  { href: "/studio", label: "创作室", icon: "✦", external: true },
  { href: "/console/videos", label: "视频库", icon: "🎞" },
  { href: "/console/settings", label: "设置", icon: "⚙" },
];

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    let alive = true;
    fetchCurrentUser().then((u) => {
      if (alive) {
        setUser(u);
        setChecked(true);
      }
    });
    return () => {
      alive = false;
    };
  }, []);

  const handleLogout = async () => {
    await logoutUser();
    setUser(null);
    router.refresh();
  };

  return (
    <div className="flex h-screen bg-[--bg-base] text-[--fg-default] overflow-hidden">
      {/* 侧边栏:未来登录后按用户隔离内容 */}
      <aside className="w-56 flex-shrink-0 flex flex-col border-r border-[--border-subtle] bg-[--bg-surface]">
        <div className="flex items-center gap-2.5 px-4 h-14 border-b border-[--border-subtle]">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-purple-500 to-pink-500" />
          <span className="font-bold tracking-tight">控制台</span>
        </div>

        <nav className="flex flex-col gap-1 px-3 py-4">
          {NAV.map((item) => {
            const active = !item.external && pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex items-center gap-2.5 h-9 px-3 rounded-md text-sm transition-colors ${
                  active
                    ? "bg-purple-950/40 text-[--fg-default] border border-purple-500/40"
                    : "text-[--fg-muted] hover:text-[--fg-default] hover:bg-[--bg-elevated] border border-transparent"
                }`}
              >
                <span>{item.icon}</span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="mt-auto px-4 pb-4 flex flex-col gap-3">
          {checked && user ? (
            <div className="rounded-lg border border-[--border-default] bg-[--bg-elevated] px-3 py-2.5">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center text-sm font-bold text-white flex-shrink-0">
                  {(user.display_name || user.username).slice(0, 1)}
                </div>
                <div className="min-w-0">
                  <p className="text-xs font-medium truncate">{user.display_name || user.username}</p>
                  <p className="text-[11px] text-[--fg-muted] truncate">@{user.username}</p>
                </div>
              </div>
              <button
                onClick={handleLogout}
                className="mt-2.5 w-full h-7 rounded-md border border-[--border-default] hover:border-red-500/60 text-[11px] text-[--fg-muted] hover:text-red-300 transition-colors"
              >
                退出登录
              </button>
            </div>
          ) : (
            <div className="rounded-lg border border-dashed border-[--border-default] px-3 py-2.5">
              <p className="text-xs font-medium text-[--fg-muted]">👤 未登录</p>
              <p className="text-[11px] text-[--fg-muted] mt-1 leading-relaxed">
                当前为公共模式;登录后视频库与设置将按用户隔离。
              </p>
              <Link
                href="/login"
                className="mt-2 inline-block text-[11px] text-purple-400 hover:text-purple-300 transition-colors"
              >
                登录 / 注册 →
              </Link>
            </div>
          )}
          <Link href="/" className="text-xs text-[--fg-muted] hover:text-[--fg-default] transition-colors">
            ← 返回首页
          </Link>
        </div>
      </aside>

      <div className="flex-1 flex flex-col overflow-hidden">{children}</div>
    </div>
  );
}
