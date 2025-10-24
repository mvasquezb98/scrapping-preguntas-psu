import os
import re
from datetime import datetime
from pathlib import Path

import fitz  # PyMuPDF
import pandas as pd


from pathlib import Path
from PIL import Image
import os

def reduce_image(in_path,
    out_path= None,
    *,
    max_width = 1600,
    max_height= 1600,
    quality = 80,           # 60–85 is a good range
    dpi = 150,       # None = keep original
    progressive = True,
    optimize = True,
    background=(255, 255, 255)) -> Path:
    """
    Load an image, optionally downscale, convert to JPEG, and save with lower quality.
    """
    in_path = Path(in_path)
    if out_path is None:
        out_path = in_path.with_suffix(".jpg")
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with Image.open(in_path) as im:
        # Convert to RGB (remove alpha if present)
        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
            base = Image.new("RGB", im.size, background)
            im = im.convert("RGBA")
            base.paste(im, mask=im.split()[-1])  # alpha channel
            im = base
        else:
            im = im.convert("RGB")

        # Optional resize with aspect ratio
        if max_width or max_height:
            im.thumbnail((max_width or im.width, max_height or im.height), Image.LANCZOS) # type: ignore

        # Save as JPEG
        save_kwargs = dict(
            format="JPEG",
            quality=quality,
            optimize=optimize,
            progressive=progressive,
        )
        if dpi is not None:
            save_kwargs["dpi"] = (dpi, dpi) # type: ignore

        im.save(out_path, **save_kwargs) # type: ignore

    return out_path

# --- Regex útiles ---
LEADING_NUM_RE = re.compile(r"^\s*(\d+)")
QUESTION_TOKEN = re.compile(r"^\s*(\d{1,3})[.)]?\s*$")
HAS_LATIN_LETTERS = re.compile(r"[A-Za-z]")  # simplificado (ajusta si necesitas unicode)


def get_questions(input_path: str,
                  output_path: str,
                  padding_cm: float = 0.5,
                  left_ratio: float = 0.143) -> pd.DataFrame:
    """
    Extrae preguntas desde PDFs en 'input_path' recortando por la franja izquierda,
    detectando tokens numéricos (1..3 dígitos) como 'n', 'n.', 'n)' en el margen.
    Exporta cada pregunta como PDF y PNG en 'output_path' y retorna un DataFrame
    con columnas: ['page', 'question_number', 'pdf_path', 'png_path', 'pdf_file'].

    - Procesa por-PDF y concatena al final
    - Calcula y_bottom por página
    - Guarda Excel con timestamp para no sobreescribir.
    """
    out_lowq_path = output_path +"lowq/"
    os.makedirs(output_path, exist_ok=True)
    os.makedirs(out_lowq_path, exist_ok=True)

    all_docs: list[pd.DataFrame] = []

    # Conversión cm -> puntos
    padding = padding_cm * 72 / 2.54

    for pdf_file in os.listdir(input_path):
        if not pdf_file.lower().endswith(".pdf"):
            print(f"Skipping non-PDF file: {pdf_file}")
            continue

        pdf_path = os.path.join(input_path, pdf_file)
        try:
            doc = fitz.open(pdf_path)
        except Exception as e:
            print(f"[WARN] No se pudo abrir {pdf_path}: {e}")
            continue

        if len(doc) == 0:
            print(f"[WARN] PDF vacío: {pdf_file}")
            doc.close()
            continue

        # Función para obtener el rectángulo de recorte izquierdo por página
        def left_clip(page: fitz.Page) -> fitz.Rect:
            r = page.rect
            return fitz.Rect(0, 0, left_ratio * r.width, r.height)

        #1) Detectar preguntas y páginas inválidas por PDF
        records = []          # filas con (page, qnum, y_top, W, H)
        invalid_pages = set() # páginas sin número pero con letras (según criterio)

        for page in doc:
            try:
                words = page.get_text("words", clip=left_clip(page)) #type: ignore
            except Exception as e:
                print(f"[WARN] get_text fallo en {pdf_file} p.{page.number}: {e}")
                continue

            # Buscar tokens tipo "12", "12)", "12." en la franja izquierda
            tokens = []
            for x0, y0, x1, y1, w, *_ in words:
                m = QUESTION_TOKEN.match(w)
                if m:
                    tokens.append((int(m.group(1)), y0))

            if tokens:
                for qnum, y0 in tokens:
                    records.append({
                        "page": page.number, # 0-based
                        "question_number": qnum,
                        "y_top": y0 + padding,
                        "W": page.rect.width,
                        "H": page.rect.height,
                    })
            else:
                # Si NO hay número, marcar inválida sólo si vemos letras en la franja
                has_letters = any(HAS_LATIN_LETTERS.search(item[4]) for item in words)
                if has_letters:
                    invalid_pages.add(page.number)

        # Si no se detectó nada en este PDF, seguir
        if not records:
            doc.close()
            continue

        df_doc = pd.DataFrame(records)

        # --- 2) Filtrar páginas inválidas dentro de ESTE PDF ---
        if invalid_pages:
            df_doc = df_doc.loc[~df_doc["page"].isin(invalid_pages)].copy()
        if df_doc.empty:
            doc.close()
            continue

        # --- 3) Calcular y_bottom por PÁGINA ---
        df_doc = df_doc.sort_values(["page", "y_top"]).copy()
        df_doc["y_bottom"] = df_doc.groupby("page")["y_top"].shift(-1)

        # Para la última pregunta de cada página, usar H - padding
        df_doc["y_bottom"] = df_doc["y_bottom"].fillna(df_doc["H"] - padding)

        # Correcciones de seguridad
        bad_mask = (df_doc["y_bottom"] <= df_doc["y_top"]) | ((df_doc["y_bottom"] - df_doc["y_top"]) < 1)
        df_doc.loc[bad_mask, "y_bottom"] = df_doc["H"] - padding

        # --- 4) Exportar recortes de ESTE PDF y asignar rutas sólo a sus filas ---
        pdf_paths, png_paths, low_quality_paths = [], [], []
        base = os.path.splitext(pdf_file)[0]

        for _, row in df_doc.iterrows():
            try:
                W, H = float(row["W"]), float(row["H"])
                y_top = float(row["y_top"])
                y_bottom = float(row["y_bottom"])
                q_clip = fitz.Rect(0, y_top, W, y_bottom)

                # Crear PDF de la pregunta
                out = fitz.open()
                dst = out.new_page(width=W, height=q_clip.height) #type: ignore
                dst.show_pdf_page(
                    fitz.Rect(0, 0, W, q_clip.height),
                    doc,
                    int(row["page"]),
                    clip=q_clip
                )

                out_pdf = os.path.join(output_path, f"{base}_Pregunta_{row['question_number']}.pdf")
                out_png = os.path.join(output_path, f"{base}_Pregunta_{row['question_number']}.png")
                out_lowq = os.path.join(out_lowq_path, f"{base}_Pregunta_{row['question_number']}_lowq.jpg")
                
                out.save(out_pdf)
                out.close()

                # Crear PNG de la pregunta
                dpi = 200
                mat = fitz.Matrix(dpi/72, dpi/72)  # de puntos PDF a pixeles
                pix = doc[int(row["page"])].get_pixmap(clip=q_clip, matrix=mat, alpha=False) #type: ignore
                pix.save(out_png)
                
                # Crear imagen baja calidad
                dpi = 130  # dots per inch
                width_px = int((W * dpi / 72)/2) # reducir la imagen a la mitad
                reduce_image(out_png, out_lowq, quality=80, dpi=dpi, max_width=width_px)

                pdf_paths.append(out_pdf)
                png_paths.append(out_png)
                low_quality_paths.append(out_lowq)
            except Exception as e:
                print(f"[WARN] Export falló en {pdf_file} p.{row['page']} q.{row['question_number']}: {e}")
                pdf_paths.append(None)
                png_paths.append(None)
                low_quality_paths.append(None)

        df_doc["pdf_path"] = pdf_paths
        df_doc["png_path"] = png_paths
        df_doc["pdf_file"] = base
        df_doc["lowq_path"] = low_quality_paths

        # Columnas finales
        df_doc = df_doc[["page", "question_number", "pdf_path", "png_path", "pdf_file", "lowq_path"]]
        all_docs.append(df_doc)

        doc.close()

    # --- 5) Unión final (sin reescrituras cruzadas) ---
    final_df = (
        pd.concat(all_docs, ignore_index=True)
        if all_docs else
        pd.DataFrame(columns=["page", "question_number", "pdf_path", "png_path", "pdf_file", "lowq_path"])
    )

    # --- 6) Guardado (con timestamp para no sobrescribir) ---
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_xlsx = os.path.join(output_path, f"bbdd_PAES_{stamp}.xlsx")
    try:
        final_df.to_excel(out_xlsx, index=False)
        print(f"[OK] Exportado Excel: {out_xlsx}")
    except Exception as e:
        print(f"[WARN] No se pudo escribir Excel '{out_xlsx}': {e}")

    return final_df
