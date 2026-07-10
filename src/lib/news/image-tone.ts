const BRIGHT_MEAN_THRESHOLD = 0.72;
const BRIGHT_PIXEL_THRESHOLD = 0.82;
const BRIGHT_PIXEL_RATIO_THRESHOLD = 0.62;

export function isBrightImageData(data: Uint8ClampedArray) {
  let luminanceTotal = 0;
  let visiblePixels = 0;
  let brightPixels = 0;

  for (let index = 0; index < data.length; index += 4) {
    const alpha = data[index + 3] / 255;
    if (alpha < 0.1) continue;

    const red = data[index] / 255;
    const green = data[index + 1] / 255;
    const blue = data[index + 2] / 255;
    const luminance = 0.2126 * red + 0.7152 * green + 0.0722 * blue;

    luminanceTotal += luminance;
    visiblePixels += 1;
    if (luminance >= BRIGHT_PIXEL_THRESHOLD) brightPixels += 1;
  }

  if (visiblePixels === 0) return false;

  return (
    luminanceTotal / visiblePixels >= BRIGHT_MEAN_THRESHOLD ||
    brightPixels / visiblePixels >= BRIGHT_PIXEL_RATIO_THRESHOLD
  );
}
