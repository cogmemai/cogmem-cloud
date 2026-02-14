import { cookies } from "next/headers";
import { NextRequest, NextResponse } from "next/server";

const BACKEND_URL =
  process.env.BACKEND_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "https://api.cogmem.ai";

export async function GET(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("cogmem_token");
  if (!token?.value) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { searchParams } = req.nextUrl;
  const params = new URLSearchParams();
  searchParams.forEach((value, key) => params.set(key, value));

  const res = await fetch(
    `${BACKEND_URL}/api/v1/kos/documents?${params.toString()}`,
    { headers: { Authorization: `Bearer ${token.value}` } }
  );
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}

export async function POST(req: NextRequest) {
  const cookieStore = await cookies();
  const token = cookieStore.get("cogmem_token");
  if (!token?.value) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  // Forward the multipart form data directly to the backend
  const formData = await req.formData();

  const res = await fetch(`${BACKEND_URL}/api/v1/kos/documents/upload`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token.value}`,
    },
    body: formData,
  });

  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
