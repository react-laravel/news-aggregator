"use client";

import Image from "next/image";
import { ImageOff } from "lucide-react";
import { useState, type SyntheticEvent } from "react";
import { isBrightImageData } from "@/lib/news/image-tone";
import { cn } from "@/lib/utils";

type ImageStatus = "loading" | "loaded" | "failed";

type NewsImageProps = {
  src: string;
  alt?: string;
  sizes: string;
  className?: string;
};

function canUseNextImage(src: string) {
  try {
    const url = new URL(src);
    return url.protocol === "https:" && url.hostname === "imgs.search.brave.com";
  } catch {
    return false;
  }
}

function detectBrightImage(image: HTMLImageElement) {
  if (!image.naturalWidth || !image.naturalHeight) return false;

  const canvas = document.createElement("canvas");
  canvas.width = 24;
  canvas.height = 24;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  if (!context) return false;

  try {
    context.drawImage(image, 0, 0, canvas.width, canvas.height);
    return isBrightImageData(context.getImageData(0, 0, canvas.width, canvas.height).data);
  } catch {
    // Cross-origin sources without CORS can still render, but their pixels cannot be inspected.
    return false;
  }
}

export function NewsImage({ src, alt = "", sizes, className }: NewsImageProps) {
  const [status, setStatus] = useState<ImageStatus>("loading");
  const [isBright, setIsBright] = useState(false);
  const optimized = canUseNextImage(src);

  function handleLoad(event: SyntheticEvent<HTMLImageElement>) {
    setIsBright(detectBrightImage(event.currentTarget));
    setStatus("loaded");
  }

  const imageClassName = cn(
    "object-cover opacity-0 transition-[filter,opacity] duration-300",
    status === "loaded" && "opacity-100",
    isBright
      ? "dark:brightness-[.68] dark:saturate-[.82]"
      : "dark:brightness-[.84] dark:saturate-[.9]",
  );

  return (
    <div className={cn("relative overflow-hidden bg-zinc-100 dark:bg-zinc-900", className)}>
      {status !== "failed" ? (
        optimized ? (
          <Image
            src={src}
            alt={alt}
            fill
            sizes={sizes}
            className={imageClassName}
            onLoad={handleLoad}
            onError={() => setStatus("failed")}
          />
        ) : (
          // Other providers can return arbitrary hosts, so they stay unoptimized instead of widening remotePatterns.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt={alt}
            className={cn("absolute inset-0 h-full w-full", imageClassName)}
            loading="lazy"
            onLoad={handleLoad}
            onError={() => setStatus("failed")}
          />
        )
      ) : null}

      {status !== "loaded" ? (
        <div
          className={cn(
            "absolute inset-0 flex items-center justify-center text-zinc-400 dark:text-zinc-600",
            status === "loading" && "animate-pulse",
          )}
          aria-hidden="true"
        >
          {status === "failed" ? (
            <div className="flex flex-col items-center gap-2 text-xs">
              <ImageOff className="h-5 w-5" />
              <span>图片暂不可用</span>
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
