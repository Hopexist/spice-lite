import { defaultKeymap, history, historyKeymap } from "@codemirror/commands";
import { type Extension, RangeSet, StateEffect, StateField } from "@codemirror/state";
import { Decoration, EditorView, GutterMarker, drawSelection, gutter, highlightActiveLine, highlightActiveLineGutter, keymap, lineNumbers } from "@codemirror/view";
import { spice, spiceHighlight } from "./spice-lang";

const setErrorLine = StateEffect.define<number | null>();
const errorLine = StateField.define<number | null>({
  create: () => null,
  update(value, tr) {
    for (const e of tr.effects) if (e.is(setErrorLine)) return e.value;
    return value;
  },
});

class ErrorMarker extends GutterMarker {
  toDOM() {
    const el = document.createElement("span");
    el.className = "err-mark";
    el.textContent = "!";
    el.title = "error on this line";
    el.setAttribute("role", "img");
    el.setAttribute("aria-label", "error on this line");
    return el;
  }
}
const marker = new ErrorMarker();

const errorGutter = gutter({
  class: "cm-error-gutter",
  lineMarker(view, line) {
    const n = view.state.field(errorLine);
    return n !== null && view.state.doc.lineAt(line.from).number === n ? marker : null;
  },
  lineMarkerChange: (u) => u.startState.field(errorLine) !== u.state.field(errorLine),
  initialSpacer: () => marker,
});

const errorLineDecoration = EditorView.decorations.compute([errorLine], (state) => {
  const n = state.field(errorLine);
  if (n === null || n < 1 || n > state.doc.lines) return Decoration.none;
  return RangeSet.of([Decoration.line({ class: "cm-error-line" }).range(state.doc.line(n).from)]);
});

const theme = EditorView.theme({
  "&": { height: "100%", color: "var(--ink)", backgroundColor: "var(--surface)" },
  ".cm-scroller": { fontFamily: "var(--mono)", fontSize: "13.5px", lineHeight: "1.6" },
  ".cm-content": { caretColor: "var(--accent)", padding: "10px 0" },
  ".cm-gutters": { backgroundColor: "var(--surface)", color: "var(--muted)", border: "none", borderRight: "1px solid var(--line)" },
  ".cm-activeLine": { backgroundColor: "var(--active-line)" },
  ".cm-activeLineGutter": { backgroundColor: "var(--active-line)", color: "var(--ink)" },
  ".cm-selectionBackground, &.cm-focused > .cm-scroller > .cm-selectionLayer .cm-selectionBackground": { backgroundColor: "var(--selection) !important" },
  "&.cm-focused": { outline: "2px solid var(--accent)", outlineOffset: "-2px" },
  ".cm-cursor": { borderLeftColor: "var(--accent)", borderLeftWidth: "2px" },
});

export interface EditorApi {
  getText(): string;
  setText(text: string): void;
  setError(line: number | null): void;
  goToLine(line: number): void;
  focus(): void;
}

export function createEditor(parent: HTMLElement, doc: string, handlers: { onChange(text: string): void; onRun(): void }): EditorApi {
  const extensions: Extension[] = [
    lineNumbers(),
    errorGutter,
    highlightActiveLineGutter(),
    highlightActiveLine(),
    drawSelection(),
    history(),
    errorLine,
    errorLineDecoration,
    spice,
    spiceHighlight,
    theme,
    EditorView.contentAttributes.of({ "aria-label": "SPICE netlist editor", spellcheck: "false", autocapitalize: "off", autocorrect: "off" }),
    keymap.of([{ key: "Mod-Enter", preventDefault: true, run: () => (handlers.onRun(), true) }, ...defaultKeymap, ...historyKeymap]),
    EditorView.updateListener.of((u) => u.docChanged && handlers.onChange(u.state.doc.toString())),
  ];
  const view = new EditorView({ doc, extensions, parent });
  return {
    getText: () => view.state.doc.toString(),
    setText: (text) => view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: text }, effects: setErrorLine.of(null), selection: { anchor: 0 } }),
    setError: (line) => view.dispatch({ effects: setErrorLine.of(line) }),
    goToLine(line) {
      const n = Math.min(Math.max(line, 1), view.state.doc.lines);
      const pos = view.state.doc.line(n).from;
      view.dispatch({ selection: { anchor: pos }, effects: EditorView.scrollIntoView(pos, { y: "center" }) });
      view.focus();
    },
    focus: () => view.focus(),
  };
}