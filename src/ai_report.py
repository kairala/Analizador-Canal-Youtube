import json

SYSTEM_PROMPT = (
    "Você é um analista de dados de YouTube. Com base nos dados fornecidos, "
    "escreva um relatório em Markdown, em português, com exatamente estas "
    "seções: '## Resumo de desempenho', '## Comparação com a média do canal' "
    "e '## Recomendações acionáveis'. Seja específico e cite os números "
    "relevantes dos dados fornecidos."
)


def build_report_prompt(video_document: dict, channel_averages: dict) -> str:
    video_json = json.dumps(video_document, ensure_ascii=False, indent=2)
    averages_json = json.dumps(channel_averages, ensure_ascii=False, indent=2)
    return (
        "Dados completos do vídeo (metadados + métricas extraídas do YouTube Analytics):\n"
        f"```json\n{video_json}\n```\n\n"
        "Médias do canal (calculadas a partir de todos os vídeos já extraídos, "
        "para efeito de comparação):\n"
        f"```json\n{averages_json}\n```"
    )


def generate_report(
    client,
    video_document: dict,
    channel_averages: dict,
    model: str = "claude-opus-5",
) -> str:
    prompt = build_report_prompt(video_document, channel_averages)

    with client.messages.stream(
        model=model,
        max_tokens=8192,
        thinking={"type": "adaptive"},
        output_config={"effort": "medium"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("a análise foi recusada pelo modelo (stop_reason=refusal)")

    text_blocks = [block.text for block in response.content if block.type == "text"]
    return "\n".join(text_blocks)
