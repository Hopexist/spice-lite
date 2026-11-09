import { describe, expect, it } from "vitest";
import { decodeShare, encodeShare, fromBase64Url, toBase64Url } from "../src/hash";

const roundTrip = async (text: string) => decodeShare(await encodeShare({ kind: "netlist", text }));

describe("share links", () => {
  it("round-trips a bundled example name", async () => {
    const hash = await encodeShare({ kind: "example", name: "rc_lowpass" });
    expect(hash).toBe("ex=rc_lowpass");
    expect(await decodeShare(`#${hash}`)).toEqual({ kind: "example", name: "rc_lowpass" });
  });

  it("round-trips a short netlist uncompressed and is URL-safe", async () => {
    const text = "t\nR1 a 0 1k\n";
    const hash = await encodeShare({ kind: "netlist", text });
    expect(hash.startsWith("n=")).toBe(true);
    expect(hash).toMatch(/^[a-z]=[A-Za-z0-9_-]+$/);
    expect(await roundTrip(text)).toEqual({ kind: "netlist", text });
  });

  it("compresses a long repetitive netlist and still round-trips it", async () => {
    const text = "ladder\n" + Array.from({ length: 200 }, (_, k) => `R${k} n${k} n${k + 1} 1k\nC${k} n${k + 1} 0 1n`).join("\n") + "\n.op\n";
    const hash = await encodeShare({ kind: "netlist", text });
    expect(hash.startsWith("z=")).toBe(true);
    expect(hash.length).toBeLessThan(text.length);
    expect(await roundTrip(text)).toEqual({ kind: "netlist", text });
  });

  it("round-trips unicode, blank lines, CRLF and the empty netlist", async () => {
    for (const text of ["T\u00edtulo \u00b5F \u03a9 \u2192\nR1 a 0 1k\n", "a\r\n\r\nb\n\n\n", "", "x".repeat(5000)]) {
      expect(await roundTrip(text)).toEqual({ kind: "netlist", text });
    }
  });

  it("accepts a hash with or without the leading #", async () => {
    expect(await decodeShare("ex=divider")).toEqual(await decodeShare("#ex=divider"));
  });

  it("rejects anything that is not a share link instead of throwing", async () => {
    for (const bad of ["", "#", "#foo", "#n=", "#n=***", "#z=AAAA", "#n=%%%", "#q=abc", "#ex", "#n=abc&x=1"]) {
      if (bad === "#n=") continue; // an empty payload is a valid empty netlist
      expect(await decodeShare(bad)).toBeNull();
    }
    expect(await decodeShare("#n=")).toEqual({ kind: "netlist", text: "" });
  });

  it("base64url helpers are inverse and unpadded", () => {
    const bytes = Uint8Array.from([251, 255, 254, 0, 1, 2, 3]);
    const text = toBase64Url(bytes);
    expect(text).not.toMatch(/[+/=]/);
    expect(Array.from(fromBase64Url(text))).toEqual(Array.from(bytes));
  });
});