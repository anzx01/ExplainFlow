"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/console/videos", label: "视频库", icon: "🎞" },
  { href: "/console/settings", label: "设置", icon: "⚙" },
];

export default function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

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
            const active = pathname?.startsWith(item.href);
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
          <div className="rounded-lg border border-dashed border-[--border-default] px-3 py-2.5">
            <p className="text-xs font-medium text-[--fg-muted]">👤 用户体系</p>
            <p className="text-[11px] text-[--fg-muted] mt-1 leading-relaxed">
              登录功能开发中,当前为公共模式;上线后视频库与设置将按用户隔离。
            </p>
          </div>
          <Link href="/" className="text-xs text-[--fg-muted] hover:text-[--fg-default] transition-colors">
            ← 返回首页
          </Link>
        </div>
      </aside>

      <div className="flex-1 flex flex-col overflow-hidden">{children}</div>
    </div>
  );
}
