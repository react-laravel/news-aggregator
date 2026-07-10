import { describe, expect, it } from "vitest";
import { qualityScore } from "./ranking";

describe("qualityScore", () => {
  it("scores published results without depending on summaries or images", () => {
    expect(qualityScore({ publishedAt: new Date("2026-07-10T00:00:00Z") })).toBe(20);
    expect(qualityScore({ publishedAt: null })).toBe(0);
  });
});
