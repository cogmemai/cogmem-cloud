import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "https://api.cogmem.ai";

async function proxyGet(path: string, searchParams: URLSearchParams) {
  const cookieStore = await cookies();
  const token = cookieStore.get("cogmem_token");
  if (!token?.value) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const url = `${BACKEND_URL}/api/v1/kos${path}?${searchParams.toString()}`;
  const res = await fetch(url, {
    headers: { Authorization: `Bearer ${token.value}` },
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function GET(req: NextRequest) {
  const { searchParams } = req.nextUrl;
  const type = searchParams.get("type") || "kos_logs";

  const params = new URLSearchParams();
  // Forward all query params except 'type'
  searchParams.forEach((value, key) => {
    if (key !== "type") params.set(key, value);
  });

  if (type === "audit_log") {
    return proxyGet("/audit-log", params);
  } else if (type === "stats") {
    return proxyGet("/logs/stats", params);
  } else {
    return proxyGet("/logs", params);
  }
}
