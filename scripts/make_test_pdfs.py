"""Generate the sample PDFs used to exercise the converter.

Run from the repo root:  python scripts/make_test_pdfs.py
"""

import fitz
import pathlib

pathlib.Path("test-pdfs").mkdir(exist_ok=True)

# --- Text PDF with headings and an embedded image ---
doc = fitz.open()
page = doc.new_page()
page.insert_text((72, 90), "Quarterly Report", fontsize=24, fontname="hebo")
page.insert_text((72, 130), "Revenue Overview", fontsize=16, fontname="hebo")
body = ("This document exists to exercise the conversion pipeline. "
        "It contains body text, a heading hierarchy, an embedded raster "
        "image, and a small decorative icon that should be filtered out.")
page.insert_textbox(fitz.Rect(72, 150, 520, 230), body, fontsize=11)

# A real figure: 400x300 gradient, should survive filtering.
pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300))
for x in range(0, 400, 2):
    for y in range(0, 300, 2):
        pix.set_pixel(x, y, (x % 256, (y * 2) % 256, 128))
page.insert_image(fitz.Rect(72, 250, 372, 475), pixmap=pix)

# Decoration: a 16x16 icon, should be dropped as too small.
icon = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 16, 16))
icon.set_rect(icon.irect, (200, 30, 30))
page.insert_image(fitz.Rect(500, 60, 516, 76), pixmap=icon)

p2 = doc.new_page()
p2.insert_text((72, 90), "Appendix", fontsize=16, fontname="hebo")
p2.insert_textbox(fitz.Rect(72, 110, 520, 200),
                  "Second page content for multi-page checks. " * 6, fontsize=11)
doc.save("test-pdfs/sample-text.pdf")
doc.close()

# --- Scanned-style PDF: an image of text, no text layer ---
doc2 = fitz.open()
tmp = fitz.open()
tp = tmp.new_page()
tp.insert_text((60, 100), "SCANNED INVOICE 4471", fontsize=28, fontname="hebo")
tp.insert_text((60, 150), "Total due: 1,250.00 USD", fontsize=20)
rendered = tp.get_pixmap(dpi=200)
tmp.close()
sp = doc2.new_page()
sp.insert_image(sp.rect, pixmap=rendered)
doc2.save("test-pdfs/sample-scan.pdf")
doc2.close()

doc = fitz.open(); page = doc.new_page()
page.insert_text((72, 80), "Sales Summary", fontsize=20, fontname="hebo")

rows = [["Region","Q1","Q2","Q3"],
        ["North","1,200","1,450","1,610"],
        ["South","980","1,020","1,180"],
        ["East","1,530","1,600","1,720"],
        ["West","760","890","950"]]
x0, y0, cw, rh = 72, 110, 110, 26
# Draw a real ruled grid so the table detector has lines to find.
for i in range(len(rows) + 1):
    page.draw_line(fitz.Point(x0, y0 + i*rh), fitz.Point(x0 + cw*4, y0 + i*rh), width=0.8)
for j in range(5):
    page.draw_line(fitz.Point(x0 + j*cw, y0), fitz.Point(x0 + j*cw, y0 + rh*len(rows)), width=0.8)
for i, row in enumerate(rows):
    for j, cell in enumerate(row):
        page.insert_text((x0 + j*cw + 8, y0 + i*rh + 17), cell,
                         fontsize=10, fontname="hebo" if i == 0 else "helv")
doc.save("test-pdfs/sample-table.pdf"); doc.close(); print("created")
