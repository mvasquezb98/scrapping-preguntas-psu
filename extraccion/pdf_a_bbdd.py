import fitz
import logging
import os
import pandas as pd
from config.creacion_directorio import *
from funciones.extraccion_datos import *
from funciones.extraccion_imagenes import *
from funciones.identificacion_preguntas import *

def process_pdf(pdf_path, pregunta_identifier, ficha_identifier):
    doc = fitz.open(pdf_path)
    pdf_title = pdf_path.split("/")[-1][0:4]
    output_folder = "output"
    img_folder = "Preguntas"
    output_folder_img = create_output_folder(os.path.join(output_folder,img_folder))
    data = []

    questions = extract_all_questions(doc, pregunta_identifier)

    for idx, q in enumerate(questions):
        page_num = q["page_num"]
        question_number = q["question_number"]
        bbox = q["bbox"]  # Ya corresponde al bbox del span exacto

        logging.info(f"➡️ Procesando PREGUNTA {question_number} en página {page_num + 1}")
        page = doc[page_num]
        blocks = page.get_text("dict")["blocks"]  # type: ignore

        # Coordenada vertical desde donde inicia la pregunta
        y0 = bbox[1]  # y del span de "PREGUNTA"

        # Determinar y1 según primer texto en negrita o fin de página
        y0, y1 = get_question_image_bounds_by_bold_blocks(blocks, y0, page.rect.height) # type: ignore

        # Recortar imagen
        image = crop_image(page, y0, y1)
        image_name = f"pregunta_{question_number}_{pdf_title}.png"
        image_path = os.path.join(output_folder_img, image_name)

        if image:
            image.save(image_path)
            logging.info(f"🖼 Imagen guardada: {image_path}")
        else:
            logging.warning(f"⚠️ No se pudo guardar la imagen de PREGUNTA {question_number}")

        # Buscar la ficha correspondiente
        block_index = q["block_index"]
        if idx < len(questions) - 1:
            next_q = questions[idx + 1]
            ficha_text = extract_ficha_between_blocks(
                doc,
                start_page=page_num,
                start_block_idx=block_index,
                end_page=next_q["page_num"],
                end_block_idx=next_q["block_index"],
                ficha_identifier=ficha_identifier
            )
        else:
            ficha_text = extract_ficha_between_blocks(
                doc,
                start_page=page_num,
                start_block_idx=block_index,
                end_page=len(doc) - 1,
                end_block_idx=len(doc[-1].get_text("dict")["blocks"]), # type: ignore
                ficha_identifier=ficha_identifier
            )

        if not ficha_text:
            logging.warning(f"⚠️ [Pregunta {question_number}] No se encontró ficha curricular.")

        data.append({
            "question_path": image_path,
            "pdf_title": pdf_title.replace("_", " "),
            "question_number": question_number,
            "eje_tematico": extract_field(ficha_text, "Eje Temático") if ficha_text else None,
            "area_tematica": extract_field(ficha_text, "Área Temática") if ficha_text else None,
            "nivel": extract_field(ficha_text, "Nivel") if ficha_text else None,
            "objetivo_fundamental": extract_field(ficha_text, "Objetivo Fundamental") if ficha_text else None,
            "contenido": extract_field(ficha_text, "Contenido") if ficha_text else None,
            "habilidad_cognitiva": extract_field(ficha_text, "Habilidad Cognitiva") if ficha_text else None,
            "clave_correcta": extract_field(ficha_text, "Clave") if ficha_text else None,
        })

    return pd.DataFrame(data)
