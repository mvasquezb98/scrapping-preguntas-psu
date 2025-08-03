import logging
import fitz

def crop_image(page, y0, y1):
    """
    Recorta la imagen de la página entre las coordenadas y0 e y1,
    asegurando que el recorte es válido.
    
    y0: coordenada de la esquina superior izq. del span donde se encuentra la palabra PREGUNTA
    y1: final de la página o coordenada de la esquina superior izq. del siguiente texto en negrita
    """
    if y0 >= y1:
        logging.warning(f"⚠️ Recorte inválido: y0 ({y0}) >= y1 ({y1}). Se omite la imagen.")
        return None

    rect = fitz.Rect(0, y0, page.rect.width, y1)
    mat = fitz.Matrix(2, 2)  # aumentar resolución
    try:
        return page.get_pixmap(matrix=mat, clip=rect)
    except Exception as e:
        logging.error(f"❌ Error al generar imagen: {e}")
        return None

def get_question_image_bounds_by_bold_blocks(blocks, y0, page_height):
    """
    Retorna los límites verticales de la imagen desde `y0` hasta el primer span en negrita,
    o hasta el final de la página si no se encuentra texto en negrita.
    """
    for block in blocks:
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                font = span.get("font", "").lower()
                if "bold" in font and span["bbox"][1] > y0:
                    return y0, span["bbox"][1]

    logging.info(f"ℹ️ No se encontró texto en negrita después de y0={y0}. Usando fin de página como y1={page_height}")
    return y0, page_height
