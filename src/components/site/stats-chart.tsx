"use client";

import { useEffect, useRef, useSyncExternalStore } from "react";
import * as echarts from "echarts/core";
import { BarChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { ECharts, EChartsCoreOption } from "echarts/core";
import { cn } from "@/lib/utils";

echarts.use([BarChart, GridComponent, TooltipComponent, CanvasRenderer]);

type ChartPoint = {
  label: string;
  value: number;
};

function getTheme() {
  if (typeof document === "undefined") return "light";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
}

function subscribeTheme(callback: () => void) {
  window.addEventListener("news-theme-changed", callback);
  window.addEventListener("storage", callback);
  return () => {
    window.removeEventListener("news-theme-changed", callback);
    window.removeEventListener("storage", callback);
  };
}

export function StatsChart({
  title,
  data,
  className,
}: {
  title: string;
  data: ChartPoint[];
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const chartRef = useRef<ECharts | null>(null);
  const theme = useSyncExternalStore(subscribeTheme, getTheme, () => "light");

  useEffect(() => {
    if (!ref.current) return;
    chartRef.current = echarts.init(ref.current, undefined, { renderer: "canvas" });
    const resize = () => chartRef.current?.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chartRef.current?.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    if (!chartRef.current) return;
    const dark = theme === "dark";
    const option: EChartsCoreOption = {
      animationDuration: 450,
      backgroundColor: "transparent",
      grid: {
        left: 8,
        right: 8,
        top: 14,
        bottom: 28,
        containLabel: true,
      },
      tooltip: {
        trigger: "axis",
        axisPointer: { type: "shadow" },
        backgroundColor: dark ? "#18181b" : "#ffffff",
        borderColor: dark ? "#3f3f46" : "#e4e4e7",
        textStyle: { color: dark ? "#fafafa" : "#18181b" },
        valueFormatter: (value: string | number) => `${value} 条`,
      },
      xAxis: {
        type: "category",
        data: data.map((item) => item.label),
        axisTick: { show: false },
        axisLine: { lineStyle: { color: dark ? "#3f3f46" : "#d4d4d8" } },
        axisLabel: {
          color: dark ? "#a1a1aa" : "#71717a",
          fontSize: 11,
          interval: data.length > 12 ? 2 : 0,
        },
      },
      yAxis: {
        type: "value",
        minInterval: 1,
        splitLine: { lineStyle: { color: dark ? "#27272a" : "#f4f4f5" } },
        axisLabel: { color: dark ? "#a1a1aa" : "#71717a", fontSize: 11 },
      },
      series: [
        {
          name: title,
          type: "bar",
          data: data.map((item) => item.value),
          barMaxWidth: 24,
          itemStyle: {
            borderRadius: [4, 4, 0, 0],
            color: dark ? "#f4f4f5" : "#18181b",
          },
        },
      ],
    };
    chartRef.current.setOption(option, true);
  }, [data, theme, title]);

  return <div ref={ref} className={cn("h-72 w-full", className)} aria-label={title} />;
}
