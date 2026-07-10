import { describe, expect, it } from "vitest";
import { isBrightImageData } from "./image-tone";

function pixels(...values: Array<[number, number, number, number?]>) {
  return new Uint8ClampedArray(values.flatMap(([red, green, blue, alpha = 255]) => [red, green, blue, alpha]));
}

describe("isBrightImageData", () => {
  it("detects a white image as bright", () => {
    expect(isBrightImageData(pixels([255, 255, 255], [245, 245, 245]))).toBe(true);
  });

  it("keeps dark images in the normal tone range", () => {
    expect(isBrightImageData(pixels([10, 18, 28], [60, 70, 85], [100, 90, 80]))).toBe(false);
  });

  it("ignores transparent pixels", () => {
    expect(isBrightImageData(pixels([255, 255, 255, 0], [40, 40, 40]))).toBe(false);
  });

  it("detects images dominated by bright pixels", () => {
    expect(
      isBrightImageData(
        pixels(
          [230, 230, 230],
          [230, 230, 230],
          [230, 230, 230],
          [230, 230, 230],
          [20, 20, 20],
        ),
      ),
    ).toBe(true);
  });
});
