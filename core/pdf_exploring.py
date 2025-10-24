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


in_pdf  = "input/PAES/2023-22-11-30-paes-oficial-matematica1-p2023.pdf"
out_pdf = "PRUEBA_PAES_2023.pdf"

doc = fitz.open(in_pdf)
for page in doc:
    W, H = page.rect.width, page.rect.height
    # Optional: only the left 14.3% strip. Set clip=None to dr+ll page.
    #clip = None
    clip = fitz.Rect(0, 0, 0.143 * W, H)

    boxes = get_all_boxes(page, clip_rect=clip, include_drawings=True)

    # Draw each layer with its own color (RGB in 0..1)
    #draw_rects(page, boxes["blocks"],   color=(1, 0, 0),   width=0.9)  # red       NOT USEFUL
    #draw_rects(page, boxes["lines"],    color=(0, 1, 0),   width=0.7)  # green
    #draw_rects(page, boxes["spans"],    color=(0, 0, 1),   width=0.6)  # blue
    draw_rects(page, boxes["words"],    color=(1, 0, 1),   width=0.5)  # magenta
    #draw_rects(page, boxes["images"],   color=(1, 0.5, 0), width=1.0)  # orange
    #draw_rects(page, boxes["drawings"], color=(0, 1, 1),   width=0.8)  # cyan
    #draw_rects(page, boxes["links"],    color=(1, 1, 0),   width=1.0)  # yellow

doc.save(out_pdf)
doc.close()
 