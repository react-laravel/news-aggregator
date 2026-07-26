type ResponseContent = {
  type?: string;
  text?: string;
};

type ResponseOutput = {
  content?: ResponseContent[];
};

type OpenAIResponseBody = {
  output_text?: string;
  output?: ResponseOutput[];
};

export function getResponseOutputText(data: OpenAIResponseBody): string {
  if (data.output_text) return data.output_text;

  return (data.output ?? [])
    .flatMap((item) => item.content ?? [])
    .filter((content) => content.type === "output_text" || typeof content.text === "string")
    .map((content) => content.text ?? "")
    .join("");
}