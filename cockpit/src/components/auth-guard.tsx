"use client"

import { useEffect, useState } from "react"
import { getToken, getTokenUser } from "@/lib/auth"

const LOGIN_URL = "https://cogmem.ai/login"

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false)

  useEffect(() => {
    const token = getToken()
    const user = getTokenUser()

    if (!token || !user) {
      window.location.href = LOGIN_URL
      return
    }

    setReady(true)
  }, [])

  if (!ready) {
    return (
      <div className="flex min-h-svh items-center justify-center">
        <div className="flex flex-col items-center gap-3">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-sm text-muted-foreground">Loading cockpit…</p>
        </div>
      </div>
    )
  }

  return <>{children}</>
}
