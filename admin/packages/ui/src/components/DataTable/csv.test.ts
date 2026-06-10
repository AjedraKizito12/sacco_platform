import { describe, expect, it } from "vitest";
import { rowsToCsv } from "./csv";

describe("rowsToCsv", () => {
  it("serialises rows with the header line", () => {
    const csv = rowsToCsv(
      [
        { id: "1", member: "Mary Akello" },
        { id: "2", member: "John" },
      ],
      [
        { key: "id", header: "ID" },
        { key: "member", header: "Member" },
      ],
    );
    expect(csv).toBe("ID,Member\n1,Mary Akello\n2,John\n");
  });

  it("escapes commas + newlines + quotes", () => {
    const csv = rowsToCsv(
      [{ note: 'has "quote", and\nnewline' }],
      [{ key: "note", header: "Note" }],
    );
    expect(csv).toContain('"has ""quote"", and\nnewline"');
  });

  it("handles null and undefined", () => {
    const csv = rowsToCsv(
      [{ a: null, b: undefined, c: 0 }],
      [
        { key: "a", header: "A" },
        { key: "b", header: "B" },
        { key: "c", header: "C" },
      ],
    );
    expect(csv).toContain(",,0");
  });
});
