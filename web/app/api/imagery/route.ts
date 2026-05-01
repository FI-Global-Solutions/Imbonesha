import { NextRequest, NextResponse } from "next/server";

/**
 * Proxy imagery from MinIO through Next.js so browsers can fetch presigned
 * URLs regardless of whether MinIO's internal hostname is reachable from the
 * browser.
 *
 * Usage: GET /api/imagery?url=<presigned-minio-url>
 *
 * The Django api returns presigned URLs with minio:9000 (internal Docker
 * hostname). Next.js server-side can reach minio:9000; browsers cannot.
 * This route fetches the image server-side and streams it to the browser.
 */
// In dev the Next.js process runs on the host; minio:9000 is only reachable
// inside Docker. Rewrite to the host-side MinIO port.
function resolveMinioUrl(url: string): string {
  const minioPublic = process.env.MINIO_PUBLIC_URL ?? "http://localhost:9007";
  return url.replace(/^http:\/\/minio:9000/, minioPublic);
}

export async function GET(req: NextRequest) {
  const url = req.nextUrl.searchParams.get("url");
  if (!url) return NextResponse.json({ error: "url required" }, { status: 400 });

  try {
    const upstream = await fetch(resolveMinioUrl(url), { cache: "no-store" });
    if (!upstream.ok) {
      return new NextResponse(null, { status: upstream.status });
    }
    const body = await upstream.arrayBuffer();
    const contentType = upstream.headers.get("content-type") ?? "image/png";
    return new NextResponse(body, {
      status: 200,
      headers: {
        "Content-Type": contentType,
        "Cache-Control": "private, max-age=840", // 14 min — presigned URL valid 15 min
      },
    });
  } catch {
    return new NextResponse(null, { status: 502 });
  }
}
