def parse_selection(raw: str, total: int) -> list[int]:
    if total <= 0:
        raise ValueError("nenhum vídeo disponível para seleção")

    normalized = raw.strip().lower()
    if not normalized:
        raise ValueError("entrada vazia")

    if normalized in ("todos", "all"):
        return list(range(1, total + 1))

    indices = []
    for part in normalized.split(","):
        part = part.strip()
        if not part.isdigit():
            raise ValueError(f"'{part}' não é um número válido")
        index = int(part)
        if index < 1 or index > total:
            raise ValueError(f"{index} está fora do intervalo (1-{total})")
        indices.append(index)

    return sorted(set(indices))
