import { NextRequest, NextResponse } from "next/server";

const STYLES: Record<string, string> = {
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
};

const GLYPHS = "https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf";

// MapLibre's demo glyph server only has Noto Sans variants.
// Rewrite every layer's text-font to use a supported font.
function patchFonts(style: Record<string, unknown>): void {
  const layers = style.layers as Array<Record<string, unknown>> | undefined;
  if (!Array.isArray(layers)) return;

  for (const layer of layers) {
    const layout = layer.layout as Record<string, unknown> | undefined;
    if (!layout) continue;
    const font = layout["text-font"];
    if (!font) continue;

    // font may be a plain array or a MapLibre expression
    if (Array.isArray(font)) {
      const hasBold = font.some(
        (f) => typeof f === "string" && /bold/i.test(f),
      );
      layout["text-font"] = hasBold
        ? ["Noto Sans Bold"]
        : ["Noto Sans Regular"];
    } else if (
      typeof font === "object" &&
      font !== null &&
      "stops" in font
    ) {
      // legacy zoom-function stops
      (font as { stops: [number, string[]][] }).stops = (
        font as { stops: [number, string[]][] }
      ).stops.map(([zoom, arr]) => {
        const hasBold = arr.some((f) => /bold/i.test(f));
        return [zoom, hasBold ? ["Noto Sans Bold"] : ["Noto Sans Regular"]];
      });
    }
  }
}

export async function GET(req: NextRequest) {
  const theme = req.nextUrl.searchParams.get("theme") ?? "light";
  const styleUrl = STYLES[theme] ?? STYLES.light;

  const res = await fetch(styleUrl, { next: { revalidate: 3600 } });
  if (!res.ok) {
    return NextResponse.json({ error: "Failed to fetch style" }, { status: 502 });
  }

  const style = await res.json();
  style.glyphs = GLYPHS;
  patchFonts(style);

  return NextResponse.json(style, {
    headers: { "Cache-Control": "public, max-age=3600" },
  });
}
