import { HighlightStyle, StreamLanguage, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

interface State {
  line: number;
}

// A number with an optional SI suffix (meg before m!) and optional trailing unit letters: 10u, 1meg, 2.2kohm, 1e-9.
const NUMBER = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?(?:meg|[fpnumkgt])?[a-z]*/i;
const WORDS = /^(?:pulse|sin|dc|ac|uic|dec|oct|lin|nmos|pmos)\b/i;

/** SPICE netlist tokens: the title (line 1), `*` comments, `.dot` commands, element names, numbers with SI suffixes. */
export const spice = StreamLanguage.define<State>({
  name: "spice",
  startState: () => ({ line: 0 }),
  token(stream, state) {
    if (stream.sol()) state.line++;
    if (state.line === 1) {
      stream.skipToEnd();
      return "heading";
    }
    if (stream.sol()) {
      if (stream.peek() === "*") {
        stream.skipToEnd();
        return "comment";
      }
      if (stream.peek() === "+") {
        stream.next();
        return "operator";
      }
      if (stream.match(/^\.[a-z]+/i)) return "keyword";
      if (stream.match(/^[a-z][\w.$#]*/i)) return "typeName";
    }
    if (stream.eatSpace()) return null;
    if (stream.peek() === ";") {
      stream.skipToEnd();
      return "comment";
    }
    if (stream.match(WORDS)) return "atom";
    if (stream.match(/^[a-z_]\w*(?=\s*=)/i)) return "propertyName";
    if (stream.match(NUMBER)) return "number";
    if (stream.match(/^[\w.$#]+/)) return null; // a node or model name
    stream.next();
    return null;
  },
  languageData: { commentTokens: { line: "*" } },
});

// Colors come from CSS variables so the light and dark themes restyle the editor without rebuilding it.
export const spiceHighlight = syntaxHighlighting(
  HighlightStyle.define([
    { tag: t.heading, color: "var(--syn-title)", fontWeight: "600" },
    { tag: t.comment, color: "var(--syn-comment)", fontStyle: "italic" },
    { tag: t.keyword, color: "var(--syn-dot)", fontWeight: "600" },
    { tag: t.typeName, color: "var(--syn-element)", fontWeight: "600" },
    { tag: t.number, color: "var(--syn-number)" },
    { tag: t.atom, color: "var(--syn-atom)" },
    { tag: t.propertyName, color: "var(--syn-prop)" },
    { tag: t.operator, color: "var(--muted)" },
  ]),
);