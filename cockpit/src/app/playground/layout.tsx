"use client";

import { IconBrain, IconArrowLeft, IconSettings, IconSun, IconMoon } from "@tabler/icons-react";
import { useTheme } from "next-themes";
import { Button } from "@/components/ui/button";

function PlaygroundNav() {
  const { theme, setTheme } = useTheme();

  return (
    <header className="flex h-12 items-center justify-between border-b bg-background px-4">
      <div className="flex items-center gap-3">
        <a
          href="/"
          className="flex items-center gap-1.5 text-muted-foreground hover:text-foreground transition-colors"
        >
          <IconArrowLeft className="size-4" />
          <span className="text-sm">Cockpit</span>
        </a>
        <div className="h-4 w-px bg-border" />
        <div className="flex items-center gap-1.5">
          <IconBrain className="size-4 text-primary" />
          <span className="text-sm font-semibold">Playground</span>
        </div>
      </div>
      <div className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="icon"
          className="size-8"
          onClick={() => setTheme(theme === "dark" ? "light" : "dark")}
        >
          <IconSun className="size-4 rotate-0 scale-100 transition-all dark:-rotate-90 dark:scale-0" />
          <IconMoon className="absolute size-4 rotate-90 scale-0 transition-all dark:rotate-0 dark:scale-100" />
          <span className="sr-only">Toggle theme</span>
        </Button>
        <Button variant="ghost" size="icon" className="size-8">
          <IconSettings className="size-4" />
          <span className="sr-only">Settings</span>
        </Button>
      </div>
    </header>
  );
}

export default function PlaygroundLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen flex-col">
      <PlaygroundNav />
      <div className="flex flex-1 overflow-hidden">{children}</div>
    </div>
  );
}
