import { describe, expect, it } from "vitest";
import { getResponseOutputText } from "./openai-response";

describe("getResponseOutputText", () => {
  it("reads the convenience output_text field", () => {
    expect(getResponseOutputText({ output_text: '{"items":[]}' })).toBe('{"items":[]}');
  });

  it("reads text from the REST Responses API output array", () => {
    expect(
      getResponseOutputText({
        output: [
          { content: [{ type: "output_text", text: '{"items":[' }] },
          { content: [{ type: "output_text", text: "]}" }] },
        ],
      }),
    ).toBe('{"items":[]}');
  });
});