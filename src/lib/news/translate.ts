import { detectLanguage } from "./normalize";

type TranslationResult = {
  titleZh: string;
  summaryZh?: string | null;
  language: string;
};

export async function translateIfNeeded(title: string, summary?: string | null): Promise<TranslationResult> {
  const language = detectLanguage(title, summary);
  if (language === "zh" || !process.env.OPENAI_API_KEY) {
    return {
      titleZh: title,
      summaryZh: summary,
      language,
    };
  }

  try {
    const response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: "gpt-5-mini",
        input: [
          {
            role: "system",
            content: "Translate news metadata into concise Simplified Chinese. Return strict JSON.",
          },
          {
            role: "user",
            content: JSON.stringify({ title, summary }),
          },
        ],
        text: {
          format: {
            type: "json_schema",
            name: "translated_news",
            schema: {
              type: "object",
              additionalProperties: false,
              required: ["titleZh", "summaryZh"],
              properties: {
                titleZh: { type: "string" },
                summaryZh: { type: "string" },
              },
            },
          },
        },
      }),
    });

    if (!response.ok) throw new Error(`OpenAI translation failed: ${response.status}`);
    const data = (await response.json()) as { output_text?: string };
    const parsed = JSON.parse(data.output_text ?? "{}") as Partial<TranslationResult>;
    return {
      titleZh: parsed.titleZh || title,
      summaryZh: parsed.summaryZh || summary,
      language,
    };
  } catch {
    return {
      titleZh: title,
      summaryZh: summary,
      language,
    };
  }
}

