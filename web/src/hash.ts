// Share links: the whole circuit lives in the URL hash, so a link reproduces it with no server.
//   #ex=<example name>   an unmodified bundled example (short link)
//   #n=<base64url>       the netlist as UTF-8
//   #z=<base64url>       the netlist, deflate-compressed (used when it is shorter)
export type Shared = { kind: "example"; name: string } | { kind: "netlist"; text: string };

export function toBase64Url(bytes: Uint8Array): string {
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) bin += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

export function fromBase64Url(text: string): Uint8Array {
  const pad = "=".repeat((4 - (text.length % 4)) % 4);
  const bin = atob(text.replace(/-/g, "+").replace(/_/g, "/") + pad);
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

async function pipe(bytes: Uint8Array, stream: CompressionStream | DecompressionStream): Promise<Uint8Array> {
  const writer = stream.writable.getWriter();
  // a corrupt stream rejects both of these as well as the read below; the read reports it, so these must not go unhandled
  writer.write(bytes as BufferSource).catch(() => {});
  writer.close().catch(() => {});
  return new Uint8Array(await new Response(stream.readable).arrayBuffer());
}

export async function encodeShare(s: Shared): Promise<string> {
  if (s.kind === "example") return `ex=${encodeURIComponent(s.name)}`;
  const raw = new TextEncoder().encode(s.text);
  const plain = `n=${toBase64Url(raw)}`;
  if (typeof CompressionStream === "undefined" || raw.length < 120) return plain;
  const packed = `z=${toBase64Url(await pipe(raw, new CompressionStream("deflate-raw")))}`;
  return packed.length < plain.length ? packed : plain;
}

/** Decode a hash (with or without the leading #). Returns null for anything that is not a valid share link. */
export async function decodeShare(hash: string): Promise<Shared | null> {
  const m = /^#?(ex|n|z)=([^&]*)$/.exec(hash);
  if (!m) return null;
  try {
    if (m[1] === "ex") return { kind: "example", name: decodeURIComponent(m[2]) };
    const bytes = fromBase64Url(m[2]);
    const raw = m[1] === "z" ? await pipe(bytes, new DecompressionStream("deflate-raw")) : bytes;
    return { kind: "netlist", text: new TextDecoder("utf-8", { fatal: true }).decode(raw) };
  } catch {
    return null;
  }
}