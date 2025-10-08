import fitz  # PyMuPDF

# ---------- helpers ----------
def draw_rects(page, rects, color, width=0.6):
    if not rects:
        return
    sh = page.new_shape()
    for r in rects:
        sh.draw_rect(r)
    sh.finish(color=color, width=width)
    sh.commit()

def get_all_boxes(page, clip_rect=None, include_drawings=True):
    """Return dict of category -> list[Rect] for text blocks/lines/spans/words/images/drawings/links."""
    boxes = {
        "blocks": [], "lines": [], "spans": [], "words": [],
        "images": [], "drawings": [], "links": []
    }

    # Text (rawdict gives blocks->lines->spans with bboxes)
    data = page.get_text("rawdict", clip=clip_rect)
    for b in data["blocks"]:
        if b["type"] == 0:  # text block
            boxes["blocks"].append(fitz.Rect(*b["bbox"]))
            for line in b["lines"]:
                boxes["lines"].append(fitz.Rect(*line["bbox"]))
                for span in line["spans"]:
                    boxes["spans"].append(fitz.Rect(*span["bbox"]))
        elif b["type"] == 1:  # image block
            boxes["images"].append(fitz.Rect(*b["bbox"]))

    # Words (often most precise)
    for x0, y0, x1, y1, *_ in page.get_text("words", clip=clip_rect):
        boxes["words"].append(fitz.Rect(x0, y0, x1, y1))

    # Vector drawings (rules, boxes, etc.)
    if include_drawings:
        for d in page.get_drawings():
            r = fitz.Rect(d["rect"])
            if (clip_rect is None) or r.intersects(clip_rect):
                boxes["drawings"].append(r)

    # Links / annotations rects
    for link in page.get_links():
        r = fitz.Rect(link["from"])
        if (clip_rect is None) or r.intersects(clip_rect):
            boxes["links"].append(r)

    return boxes

# ---------- main ----------
in_pdf  = "C://Users//mvasq//OneDrive//Documentos//Scrapper_PSU_PAES//input//PAES//2024-23-11-29-paes-regular-oficial-matematica1-p2024 (2).pdf"
out_pdf = "input//PAES//PRUEBA.pdf"

# doc = fitz.open(in_pdf)
# for page in doc:
#     W, H = page.rect.width, page.rect.height
#     # Optional: only the left 14.3% strip. Set clip=None to dr+ll page.
#     #clip = None
#     clip = fitz.Rect(0, 0, 0.143 * W, H)

#     boxes = get_all_boxes(page, clip_rect=clip, include_drawings=True)

#     # Draw each layer with its own color (RGB in 0..1)
#     #draw_rects(page, boxes["blocks"],   color=(1, 0, 0),   width=0.9)  # red       NOT USEFUL
#     #draw_rects(page, boxes["lines"],    color=(0, 1, 0),   width=0.7)  # green
#     draw_rects(page, boxes["spans"],    color=(0, 0, 1),   width=0.6)  # blue
#     #draw_rects(page, boxes["words"],    color=(1, 0, 1),   width=0.5)  # magenta
#     #draw_rects(page, boxes["images"],   color=(1, 0.5, 0), width=1.0)  # orange
#     #draw_rects(page, boxes["drawings"], color=(0, 1, 1),   width=0.8)  # cyan
#     #draw_rects(page, boxes["links"],    color=(1, 1, 0),   width=1.0)  # yellow

#doc.save(out_pdf)
# doc.close()
 
import re
import fitz  # PyMuPDF
import pandas as pd
import os
# Regex for leading number in a string, e.g. "1. Question text", "12) Another question"
LEADING_NUM_RE = re.compile(r"^\s*(\d+)")

# Acceptable "question number" tokens in the margin, e.g. "1", "12", "3.", "10)"
QUESTION_TOKEN = re.compile(r"^\s*(\d{1,3})[.)]?\s*$")
HAS_LATIN_LETTERS = re.compile(r"[A-Za-z]")  # or use str.isalpha per-char if you need Unicode

def get_questions(pdf_file,input_path, output_path, padding_cm = 1.5 , left_ratio=0.143):
    pdf_path = os.path.join(input_path,pdf_file)
    doc = fitz.open(pdf_path)
    padding = padding_cm * 72 / 2.54  # cm to points
    questions = []
    invalid_pages = set()
    page = doc[1] # just to get W, H
    W, H = page.rect.width, page.rect.height
    clip = fitz.Rect(0, 0, left_ratio * W, H)
    for page in doc:
        # words: [x0, y0, x1, y1, word, block_no, line_no, word_no]
        words = page.get_text("words", clip=clip) #type: ignore

        # 1) Try to find question numbers first (whitelist)
        for x0, y0, x1, y1, w, *_ in words:
            m = QUESTION_TOKEN.match(w)
            if m:
                qnum = int(m.group(1))
                questions.append({
                    "page": page.number, #type: ignore
                    "question_number": qnum,
                    "text": w,
                    "y_top": y0 - padding
                })
                
        # 2) If no numbers found, *then* decide whether to skip due to letters
            if m == None:
                has_letters = any(HAS_LATIN_LETTERS.search(w[4]) for w in words)
                if has_letters:
                    invalid_pages.add(page.number)
                    continue
    
    df = pd.DataFrame(questions)
    valid_df = df.loc[~df["page"].isin(invalid_pages)].reset_index(drop=True)
               
    valid_df["y_bottom"] = valid_df["y_top"].shift(-1, fill_value=H-padding)
    valid_df.loc[(valid_df["y_bottom"] <= valid_df["y_top"])|((valid_df["y_bottom"] - valid_df["y_top"])<1), "y_bottom"] = H - padding
    
    q_path_pdf = []
    q_path_png = []
    
    for idx, row in valid_df.iterrows():
        q_clip = fitz.Rect(0, row["y_top"], W, row["y_bottom"])
        new_h = q_clip.height
        
        out = fitz.open()
        dst = out.new_page(width=W, height=new_h) #type: ignore
        dst.show_pdf_page(
            fitz.Rect(0, 0, W, new_h),      # destination rectangle on new page
            doc,                            # source document
            row["page"],                  # source page number (0-based)
            clip=q_clip                     # clip rectangle on source page
        )
        
        q_out_path_pdf = os.path.join(output_path, f"{pdf_file.split('.')[0]}_Pregunta_{row['question_number']}.pdf")
        q_out_path_png = os.path.join(output_path, f"{pdf_file.split('.')[0]}_Pregunta_{row['question_number']}.png")
        
        q_path_pdf.append(q_out_path_pdf)
        q_path_png.append(q_out_path_png)
        
        out.save(q_out_path_pdf)
        
        dpi = 200
        mat = fitz.Matrix(dpi/72, dpi/72)   # scale from PDF points to pixels
        pix = doc[int(row["page"])].get_pixmap(clip=q_clip, matrix=mat, alpha=False)  # type: ignore
        pix.save(q_out_path_png)
        
        out.close()
    valid_df["pdf_path"] = q_path_pdf
    valid_df["png_path"] = q_path_png
    valid_df["pdf_file"] = pdf_file.split('.')[0]
    valid_df.drop(columns=["text","y_top", "y_bottom"], inplace=True)

    doc.close()
    return valid_df

pdf_file="2024-23-11-29-paes-regular-oficial-matematica1-p2024 (2).pdf"
input_path = "C://Users//mvasq//OneDrive//Documentos//Scrapper_PSU_PAES//input//PAES//"
output_path= "C://Users//mvasq//OneDrive//Documentos//Scrapper_PSU_PAES//output//PAES//"

df = get_questions(pdf_file,input_path, output_path, padding_cm = 1.5 , left_ratio=0.143)

