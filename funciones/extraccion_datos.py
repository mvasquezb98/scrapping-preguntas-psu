import re

def extract_field(ficha_text, label):
    match = re.search(f"{label}\s*:\s*(.+)", ficha_text, re.IGNORECASE) # type: ignore
    return match.group(1).strip() if match else None

def extract_ficha_between_blocks(doc, start_page, start_block_idx, end_page, end_block_idx, ficha_identifier):
    """
    Busca la ficha curricular entre los bloques indicados.
    """
    collecting = False
    collected = []

    for i in range(start_page, end_page + 1):
        blocks = doc[i].get_text("dict")["blocks"]
        for j, block in enumerate(blocks):
            if (i == start_page and j <= start_block_idx):
                continue
            if (i == end_page and j >= end_block_idx):
                break
            text = "\n".join(
                span.get("text", "") for line in block.get("lines", []) for span in line.get("spans", [])
            )
            if ficha_identifier in text.upper():
                collecting = True
            if collecting:
                collected.append(text)
    return "\n".join(collected) if collected else None
