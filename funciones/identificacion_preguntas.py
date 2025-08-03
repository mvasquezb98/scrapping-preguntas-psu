import re

# def extract_all_questions(doc,pregunta_identifier):
#     """
#     Extrae todas las preguntas con su ubicación: número, página, índice de bloque y posición.
#     """
#     questions = []
#     for page_num, page in enumerate(doc):
#         blocks = page.get_text("dict")["blocks"]
#         for i, block in enumerate(blocks):
#             lines = block.get("lines", [])
#             if not lines:
#                 continue
#             text = "\n".join(
#                 span.get("text", "")
#                 for line in block.get("lines", [])
#                 for span in line.get("spans", [])
#             ).strip()
#             match = re.search(pregunta_identifier, text, re.IGNORECASE)
#             if match:
#                 question_number = int(match.group(1))
#                 questions.append({
#                     "question_number": question_number,
#                     "page_num": page_num,
#                     "block_index": i,
#                     "bbox": block["bbox"]
#                 })
#     return sorted(questions, key=lambda x: (x["page_num"], x["block_index"]))
def extract_all_questions(doc, pregunta_identifier):
    """
    Extrae la ubicación exacta de la palabra PREGUNTA {n}, incluyendo su bbox.
    """
    questions = []
    for page_num, page in enumerate(doc): # Recorre cada página
        blocks = page.get_text("dict")["blocks"] # Todos los bloques de texto de la pagina
        for block_index, block in enumerate(blocks): # Itera por cada bloque de la página
            lines = block.get("lines", []) 
            for line in lines: # Cada línea contiene uno o más spans
                for span in line.get("spans", []): # Por cada span (segmento de texto con fuente y estilo uniforme, ej. una palabra en negrita)
                    text = span.get("text", "").strip() # Extrae el texto del span
                    match = re.search(pregunta_identifier, text, re.IGNORECASE) # Verifica si pregunta_identifier está en ese span
                    if match: #Si es que hay match...
                        question_number = int(match.group(1))
                        questions.append({
                            "question_number": question_number,
                            "page_num": page_num,
                            "block_index": block_index,
                            "bbox": span["bbox"]  # Ubicacion exacta del span que contiene la palabra PREGUNTA.
                            # bbox tiene una tupla de 4 elementos (x0, y0, x1, y1) donde (x0,y0):esquina superior izq. y (x1,y1): esquina inferior derecha.
                        })
    return sorted(questions, key=lambda x: (x["page_num"], x["block_index"]))
