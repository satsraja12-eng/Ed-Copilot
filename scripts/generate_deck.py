"""Generate Ed-Copilot Architecture deck as a .pptx file.

Run: python scripts/generate_deck.py
Output: exports/EdCopilot_Architecture.pptx
"""
from __future__ import annotations

import os
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

# ── Palette ──────────────────────────────────────────────────────────────────
BG_LIGHT   = RGBColor(0xF8, 0xF7, 0xF4)   # warm off-white
BG_DARK    = RGBColor(0x1B, 0x43, 0x32)   # forest green (title / divider)
ACCENT     = RGBColor(0x1B, 0x43, 0x32)   # forest green
ACCENT_LT  = RGBColor(0xD1, 0xFA, 0xE5)   # mint tint for table highlights
TEXT_DARK  = RGBColor(0x0F, 0x1A, 0x13)   # near-black
TEXT_LIGHT = RGBColor(0xF8, 0xF7, 0xF4)   # off-white (on dark BG)
TEXT_MUTED = RGBColor(0x6B, 0x72, 0x80)   # gray
RULE_COLOR = RGBColor(0x1B, 0x43, 0x32)   # accent rule under titles
CODE_BG    = RGBColor(0xEC, 0xFD, 0xF5)   # very light mint for code blocks
BORDER     = RGBColor(0xBB, 0xF7, 0xD0)   # light green for code block border

FONT_BODY  = "Calibri"
FONT_CODE  = "Courier New"

# ── Slide dimensions (widescreen 16:9) ───────────────────────────────────────
W = Inches(13.33)
H = Inches(7.5)

MARGIN_L = Inches(0.7)
MARGIN_T = Inches(0.6)
MARGIN_R = Inches(0.7)
CONTENT_W = W - MARGIN_L - MARGIN_R

FOOTER_Y  = Inches(6.95)
FOOTER_H  = Inches(0.35)

TITLE_H   = Inches(1.05)
RULE_Y    = Inches(1.55)     # horizontal rule below title
RULE_H    = Pt(2)
BODY_Y    = Inches(1.72)
BODY_H    = Inches(5.0)

TOTAL_SLIDES = 10   # used in footer "N / 10"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _rgb(r, g, b):
    return RGBColor(r, g, b)


def _set_bg(slide, color: RGBColor):
    from pptx.oxml.ns import qn
    from lxml import etree
    bg = slide.background
    fill = bg.fill
    fill.solid()
    fill.fore_color.rgb = color


def _add_rect(slide, x, y, w, h, fill: RGBColor = None, line: RGBColor = None, line_w_pt=0):
    shape = slide.shapes.add_shape(
        1,  # MSO_SHAPE_TYPE.RECTANGLE
        x, y, w, h
    )
    shape.line.fill.background()
    if fill:
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill
    else:
        shape.fill.background()
    if line:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_w_pt)
    else:
        shape.line.fill.background()
    return shape


def _add_textbox(slide, x, y, w, h, text, font_name=FONT_BODY, size_pt=18,
                 bold=False, color: RGBColor = TEXT_DARK,
                 align=PP_ALIGN.LEFT, wrap=True, italic=False):
    txb = slide.shapes.add_textbox(x, y, w, h)
    tf = txb.text_frame
    tf.word_wrap = wrap
    p = tf.paragraphs[0]
    p.alignment = align
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = Pt(size_pt)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return txb


def _add_title(slide, text, dark_bg=False):
    """Add the action-title bar + accent rule."""
    fg = TEXT_LIGHT if dark_bg else TEXT_DARK
    txb = _add_textbox(slide, MARGIN_L, MARGIN_T, CONTENT_W, TITLE_H,
                       text, size_pt=24, bold=True, color=fg)
    txb.text_frame.word_wrap = True
    # Accent rule
    rule_color = TEXT_LIGHT if dark_bg else RULE_COLOR
    _add_rect(slide, MARGIN_L, RULE_Y, CONTENT_W, Pt(2), fill=rule_color)
    return txb


def _add_footer(slide, slide_num: int, dark_bg=False):
    fg = RGBColor(0xA0, 0xB0, 0xA8) if dark_bg else TEXT_MUTED
    _add_textbox(slide, MARGIN_L, FOOTER_Y, Inches(6), FOOTER_H,
                 "Ed-Copilot Architecture", size_pt=11, color=fg)
    _add_textbox(slide, W - Inches(1.5), FOOTER_Y, Inches(1.1), FOOTER_H,
                 f"{slide_num} / {TOTAL_SLIDES}", size_pt=11, color=fg,
                 align=PP_ALIGN.RIGHT)


def _bullet_frame(slide, x, y, w, h):
    txb = slide.shapes.add_textbox(x, y, w, h)
    tf = txb.text_frame
    tf.word_wrap = True
    return tf


def _add_para(tf, text, indent=0, size_pt=20, bold=False,
              color: RGBColor = TEXT_DARK, font_name=FONT_BODY,
              space_before_pt=0, italic=False):
    from pptx.util import Pt as _Pt
    p = tf.add_paragraph()
    p.alignment = PP_ALIGN.LEFT
    p.space_before = _Pt(space_before_pt)
    p.level = indent
    run = p.add_run()
    run.text = text
    run.font.name = font_name
    run.font.size = _Pt(size_pt)
    run.font.bold = bold
    run.font.italic = italic
    run.font.color.rgb = color
    return p


def _add_code_block(slide, x, y, w, text_lines: list[str], size_pt=14):
    """Render a monospace code-block with a tinted background."""
    line_h = Pt(size_pt) * 1.55
    block_h = int(line_h * (len(text_lines) + 1.2))
    _add_rect(slide, x, y, w, block_h, fill=CODE_BG, line=BORDER, line_w_pt=0.75)
    txb = slide.shapes.add_textbox(x + Inches(0.18), y + Inches(0.12),
                                   w - Inches(0.36), block_h)
    tf = txb.text_frame
    tf.word_wrap = False
    for i, line in enumerate(text_lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = PP_ALIGN.LEFT
        run = p.add_run()
        run.text = line
        run.font.name = FONT_CODE
        run.font.size = Pt(size_pt)
        run.font.color.rgb = TEXT_DARK
    return block_h


def _add_table(slide, x, y, w, rows, col_widths, header_row=True, accent=ACCENT):
    """Add a simple styled table. rows = list of list of str."""
    from pptx.util import Pt as _Pt
    n_rows = len(rows)
    n_cols = len(rows[0])
    row_h  = Inches(0.42)
    tbl = slide.shapes.add_table(n_rows, n_cols, x, y, w, row_h * n_rows).table
    # Column widths
    total = sum(col_widths)
    for ci, cw in enumerate(col_widths):
        tbl.columns[ci].width = int(w * cw / total)
    # Row heights
    for ri in range(n_rows):
        tbl.rows[ri].height = row_h

    for ri, row in enumerate(rows):
        for ci, cell_text in enumerate(row):
            cell = tbl.cell(ri, ci)
            cell.text = cell_text
            tf = cell.text_frame
            tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT
            run = p.runs[0] if p.runs else p.add_run()
            run.text = cell_text
            run.font.name = FONT_BODY
            run.font.size = _Pt(15)
            run.font.bold = (ri == 0 and header_row)
            if ri == 0 and header_row:
                run.font.color.rgb = TEXT_LIGHT
                _set_cell_bg(cell, accent)
            elif cell_text.startswith("[Complete]") or "Complete" in cell_text:
                run.font.color.rgb = ACCENT
                run.font.bold = True
            elif cell_text.startswith("[Pending]") or "Pending" in cell_text:
                run.font.color.rgb = TEXT_MUTED
            else:
                run.font.color.rgb = TEXT_DARK
                if ri % 2 == 0:
                    _set_cell_bg(cell, RGBColor(0xF3, 0xF4, 0xF6))
    return tbl


def _set_cell_bg(cell, color: RGBColor):
    from pptx.oxml.ns import qn
    from lxml import etree
    tc = cell._tc
    tcPr = tc.get_or_add_tcPr()
    solidFill = etree.SubElement(tcPr, qn("a:solidFill"))
    srgbClr = etree.SubElement(solidFill, qn("a:srgbClr"))
    srgbClr.set("val", f"{color[0]:02X}{color[1]:02X}{color[2]:02X}")


# ── Slide builders ────────────────────────────────────────────────────────────

def slide_01_title(prs):
    layout = prs.slide_layouts[6]  # blank
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_DARK)

    # Eyebrow
    _add_textbox(slide, MARGIN_L, Inches(1.8), CONTENT_W, Inches(0.4),
                 "ARCHITECTURE OVERVIEW", size_pt=13, bold=True,
                 color=RGBColor(0x6E, 0xE7, 0xB7), font_name=FONT_BODY)

    # Main title
    txb = slide.shapes.add_textbox(MARGIN_L, Inches(2.2), CONTENT_W, Inches(1.8))
    tf = txb.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    run = p.add_run()
    run.text = "Ed-Copilot"
    run.font.name = FONT_BODY
    run.font.size = Pt(52)
    run.font.bold = True
    run.font.color.rgb = TEXT_LIGHT

    p2 = tf.add_paragraph()
    r2 = p2.add_run()
    r2.text = "Multi-District K-12 Family Assistant"
    r2.font.name = FONT_BODY
    r2.font.size = Pt(28)
    r2.font.bold = False
    r2.font.color.rgb = RGBColor(0xA7, 0xF3, 0xD0)

    # Rule
    _add_rect(slide, MARGIN_L, Inches(4.25), Inches(4.5), Pt(2),
              fill=RGBColor(0x6E, 0xE7, 0xB7))

    # Meta line
    _add_textbox(slide, MARGIN_L, Inches(4.5), CONTENT_W, Inches(0.4),
                 "Phase 2  ·  June 2026  ·  Engineering & Product",
                 size_pt=14, color=RGBColor(0xA7, 0xF3, 0xD0))


def slide_02_plugin(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "Any school district can plug into Ed-Copilot by adding exactly 2 files")

    tf = _bullet_frame(slide, MARGIN_L, BODY_Y, CONTENT_W, BODY_H)
    _add_para(tf, "The 2-file contract:", size_pt=18, bold=True, color=ACCENT,
              space_before_pt=0)
    _add_para(tf, "  config/tenants/<district-id>.yaml  —  declare the district",
              size_pt=19, font_name=FONT_CODE, space_before_pt=6)
    _add_para(tf, "  src/agents/<district_id>_agent.py  —  implement the agent",
              size_pt=19, font_name=FONT_CODE, space_before_pt=4)

    _add_para(tf, "What this means in practice:", size_pt=18, bold=True,
              color=ACCENT, space_before_pt=18)
    items = [
        "A YAML manifest declares the district: ID, display name, grade levels, doc types",
        "A Python agent class implements three hooks: retrieve(), synthesize(), handle()",
        "The orchestrator and app update automatically — zero changes to core code",
        "Current deployment: 3 districts active (Wake County NC, Frisco ISD TX, Plano ISD TX)",
    ]
    for item in items:
        _add_para(tf, f"  \u2022  {item}", size_pt=19, space_before_pt=5)

    _add_footer(slide, 2)


def slide_03_registry(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "DistrictRegistry scans YAML configs at startup and wires each agent automatically")

    tf = _bullet_frame(slide, MARGIN_L, BODY_Y, CONTENT_W, BODY_H)
    _add_para(tf, "Startup sequence (src/district_registry.py):", size_pt=18,
              bold=True, color=ACCENT, space_before_pt=0)

    steps = [
        ("1.", "Scans config/tenants/*.yaml on first import"),
        ("2.", "Reads agent_module path from each YAML"),
        ("3.", "Imports the module and reads the module-level  agent  variable"),
        ("4.", "Registers  {district_id: DistrictAgent instance}  in an internal map"),
        ("5.", "Orchestrator queries the registry to build LangGraph nodes"),
    ]
    for num, step in steps:
        _add_para(tf, f"  {num}  {step}", size_pt=19, space_before_pt=7)

    _add_para(tf, "Result: no hardcoded district names anywhere in orchestrator.py or app.py",
              size_pt=18, bold=True, color=ACCENT, space_before_pt=18,
              italic=True)

    _add_footer(slide, 3)


def slide_04_isolation(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "Each district agent is isolated: shared interface, zero shared state")

    col_w = (CONTENT_W - Inches(0.3)) / 2
    left_x  = MARGIN_L
    right_x = MARGIN_L + col_w + Inches(0.3)

    # Left column header
    _add_rect(slide, left_x, BODY_Y, col_w, Inches(0.38), fill=ACCENT)
    _add_textbox(slide, left_x + Inches(0.15), BODY_Y + Inches(0.06),
                 col_w - Inches(0.3), Inches(0.3),
                 "DistrictAgent hooks (base class)", size_pt=15, bold=True,
                 color=TEXT_LIGHT)

    tf_l = _bullet_frame(slide, left_x, BODY_Y + Inches(0.45),
                         col_w, Inches(4.2))
    hooks = [
        "retrieve(query, intent, persona)",
        "  → List[Document]",
        "",
        "synthesize(query, docs, intent, persona)",
        "  → str",
        "",
        "handle(state)",
        "  → state  (full pipeline override)",
    ]
    for h in hooks:
        empty = h.strip() == ""
        _add_para(tf_l, h, size_pt=16 if not empty else 8,
                  font_name=FONT_CODE if h.strip() else FONT_BODY,
                  color=TEXT_DARK, space_before_pt=2)

    # Right column header
    _add_rect(slide, right_x, BODY_Y, col_w, Inches(0.38), fill=ACCENT)
    _add_textbox(slide, right_x + Inches(0.15), BODY_Y + Inches(0.06),
                 col_w - Inches(0.3), Inches(0.3),
                 "Isolation guarantees", size_pt=15, bold=True,
                 color=TEXT_LIGHT)

    tf_r = _bullet_frame(slide, right_x, BODY_Y + Inches(0.45),
                         col_w, Inches(4.2))
    guarantees = [
        ("Frisco ISD data never appears in a Plano ISD response", False),
        ("Agents can use different vector stores, embeddings, or LLM models", False),
        ("A crash in one agent does not affect others", False),
        ("Each agent carries its own ChromaDB client, initialized lazily", False),
    ]
    for g, _ in guarantees:
        _add_para(tf_r, f"  \u2022  {g}", size_pt=18, space_before_pt=10)

    _add_footer(slide, 4)


def slide_05_yaml(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "The YAML manifest is the only contract between a district and the platform")

    # Intro line
    _add_textbox(slide, MARGIN_L, BODY_Y, CONTENT_W, Inches(0.4),
                 "config/tenants/frisco_isd_tx.yaml  —  complete example:",
                 size_pt=17, bold=True, color=ACCENT)

    yaml_lines = [
        "district_id:   frisco_isd_tx",
        "display_name:  Frisco ISD",
        "state:         TX",
        "grade_levels:  K-12",
        "doc_types:",
        "  - course_catalog",
        "  - admin_policy",
        "agent_module:  src.agents.frisco_isd_tx_agent",
    ]
    block_h = _add_code_block(slide, MARGIN_L, BODY_Y + Inches(0.48),
                              Inches(7.2), yaml_lines, size_pt=16)

    note_y = BODY_Y + Inches(0.48) + block_h + Inches(0.25)
    tf = _bullet_frame(slide, MARGIN_L, note_y, CONTENT_W, Inches(2.0))
    _add_para(tf, "All platform behaviour derives from these 8 fields:", size_pt=18,
              bold=True, color=ACCENT, space_before_pt=0)
    derivations = [
        "district_id     →   ChromaDB collection names  (frisco_isd_tx__course_catalog)",
        "display_name    →   Sidebar dropdown label in app.py",
        "agent_module    →   Python import path — DistrictRegistry loads the agent",
        "doc_types       →   Intent classifier scope for this district",
    ]
    for d in derivations:
        _add_para(tf, f"  \u2022  {d}", size_pt=17, font_name=FONT_CODE,
                  space_before_pt=5)

    _add_footer(slide, 5)


def slide_06_langgraph(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "LangGraph routes each query to exactly one district node via intent classification")

    tf = _bullet_frame(slide, MARGIN_L, BODY_Y, CONTENT_W, BODY_H)
    _add_para(tf, "Graph execution path:", size_pt=18, bold=True, color=ACCENT)

    steps = [
        ("1.", "classify_intent node",
         "LLM classifies intent (course_catalog | admin_policy | out_of_scope) and reads district from user context"),
        ("2.", "Conditional edge",
         "Routes to matching district node: agent_frisco_isd_tx, agent_plano_isd_tx, or agent_wake_county_nc"),
        ("3.", "District node",
         "Calls handle() → retrieve() → synthesize() — each fully implemented by the district agent"),
        ("4.", "Response",
         "Returns with context_docs and intent_badge for citation display in the Streamlit UI"),
    ]
    for num, label, desc in steps:
        _add_para(tf, f"  {num}  {label}", size_pt=19, bold=True, space_before_pt=10,
                  color=ACCENT)
        _add_para(tf, f"       {desc}", size_pt=18, space_before_pt=2)

    _add_para(tf, "Out-of-scope queries short-circuit before reaching any agent",
              size_pt=17, italic=True, color=TEXT_MUTED, space_before_pt=14)

    _add_footer(slide, 6)


def slide_07_chromadb(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "Frisco and Plano agents retrieve from district-isolated ChromaDB collections")

    _add_textbox(slide, MARGIN_L, BODY_Y, CONTENT_W, Inches(0.38),
                 "Collection naming convention:   {district_id}__{doc_type}",
                 size_pt=17, bold=True, color=ACCENT)

    rows = [
        ["Collection", "Chunks", "District", "Content"],
        ["frisco_isd_tx__course_catalog",   "7",     "Frisco ISD TX",   "AP Calc AB/BC, Geometry, Algebra I/II, Precalculus, AP Stats"],
        ["plano_isd_tx__course_catalog",    "5",     "Plano ISD TX",    "Algebra I through AP Calculus AB"],
        ["langchain",                        "1,158", "Wake County NC",  "NC Math 1, 2, 3 curriculum + standards"],
        ["frisco_isd_tx__admin_policy",     "0",     "Frisco ISD TX",   "Admin PDFs — ingestion pending (Phase 3)"],
        ["plano_isd_tx__admin_policy",      "0",     "Plano ISD TX",    "Admin PDFs — ingestion pending (Phase 3)"],
    ]
    _add_table(slide, MARGIN_L, BODY_Y + Inches(0.48),
               CONTENT_W, rows, col_widths=[4, 1, 2.2, 5.5])

    footer_y = BODY_Y + Inches(0.48) + Inches(0.42 * len(rows)) + Inches(0.2)
    _add_textbox(slide, MARGIN_L, footer_y, CONTENT_W, Inches(0.35),
                 "Embeddings: BAAI/bge-small-en-v1.5 (HuggingFace) — consistent across all districts.",
                 size_pt=13, color=TEXT_MUTED)

    _add_footer(slide, 7)


def slide_08_guardrails(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "Groundedness guardrails prevent hallucinated and unsafe responses before delivery")

    tf = _bullet_frame(slide, MARGIN_L, BODY_Y, CONTENT_W, BODY_H)
    _add_para(tf, "Two-layer guard — executed on every TX district response:", size_pt=18,
              bold=True, color=ACCENT)

    _add_para(tf, "  Layer 1  —  Safety pre-check  (input_is_safe)", size_pt=19,
              bold=True, space_before_pt=14)
    _add_para(tf, "       Blocks PII-elicitation and student-privacy probes before any retrieval occurs",
              size_pt=18, space_before_pt=3)
    _add_para(tf, "       Runs synchronously on the raw user message — zero latency cost",
              size_pt=18, space_before_pt=3)

    _add_para(tf, "  Layer 2  —  Groundedness score  (post-synthesis)", size_pt=19,
              bold=True, space_before_pt=14)
    _add_para(tf, "       Lexical overlap between answer tokens and retrieved context",
              size_pt=18, space_before_pt=3)
    _add_para(tf, "       Score < 0.25: warning logged, response flagged for review",
              size_pt=18, space_before_pt=3)
    _add_para(tf, "       Upgrade path: NLI entailment model or LLM-as-judge for production",
              size_pt=18, space_before_pt=3, color=TEXT_MUTED, italic=True)

    _add_para(tf, "Wake County NC uses LangSmith Faithfulness + Relevance eval (LLM-as-judge)",
              size_pt=17, bold=True, color=ACCENT, space_before_pt=18)

    _add_footer(slide, 8)


def slide_09_onboard(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "Adding a 4th district requires one YAML file, one Python class, and an ingestion run")

    _add_textbox(slide, MARGIN_L, BODY_Y, CONTENT_W, Inches(0.38),
                 "Example: onboarding Richardson ISD TX",
                 size_pt=18, bold=True, color=ACCENT)

    steps = [
        ("Step 1", "config/tenants/richardson_isd_tx.yaml",
         "8 fields — district_id, display_name, state, grade_levels, doc_types, agent_module"),
        ("Step 2", "src/agents/richardson_isd_tx_agent.py",
         "Subclass DistrictAgent, implement retrieve() + synthesize() — copy Frisco agent as template"),
        ("Step 3", "python src/ingestion/richardson_ingestion.py",
         "Populate ChromaDB — seed JSON offline, --crawl flag for live district website"),
        ("Step 4", "Restart app",
         "Richardson ISD appears in the district dropdown automatically — no other changes"),
    ]

    step_y = BODY_Y + Inches(0.48)
    step_h = Inches(1.1)
    for i, (label, code, desc) in enumerate(steps):
        box_y = step_y + i * (step_h + Inches(0.08))
        # Number badge
        _add_rect(slide, MARGIN_L, box_y, Inches(0.45), step_h, fill=ACCENT)
        _add_textbox(slide, MARGIN_L + Inches(0.05), box_y + Inches(0.28),
                     Inches(0.35), Inches(0.45),
                     str(i + 1), size_pt=22, bold=True, color=TEXT_LIGHT,
                     align=PP_ALIGN.CENTER)
        # Content
        _add_textbox(slide, MARGIN_L + Inches(0.6), box_y + Inches(0.08),
                     CONTENT_W - Inches(0.65), Inches(0.42),
                     code, size_pt=17, bold=True, color=TEXT_DARK,
                     font_name=FONT_CODE)
        _add_textbox(slide, MARGIN_L + Inches(0.6), box_y + Inches(0.52),
                     CONTENT_W - Inches(0.65), Inches(0.48),
                     desc, size_pt=17, color=TEXT_DARK)

    # Footer note
    note_y = step_y + 4 * (step_h + Inches(0.08)) + Inches(0.05)
    _add_textbox(slide, MARGIN_L, note_y, CONTENT_W, Inches(0.38),
                 "No changes to: orchestrator.py  ·  app.py  ·  district_registry.py  ·  any other district's code",
                 size_pt=15, color=TEXT_MUTED, italic=True)

    _add_footer(slide, 9)


def slide_10_roadmap(prs):
    layout = prs.slide_layouts[6]
    slide = prs.slides.add_slide(layout)
    _set_bg(slide, BG_LIGHT)
    _add_title(slide, "Phases 1 and 2 are complete; Phases 3-5 deliver user profiles, evals, and citations")

    rows = [
        ["Phase", "Deliverable", "Status"],
        ["Phase 1", "Plugin hook system — DistrictAgent base class, DistrictRegistry, YAML auto-discovery", "Complete"],
        ["Phase 2", "TX ingestion & live retrieval — crawlers, pipeline, groundedness, Frisco + Plano agents", "Complete"],
        ["Phase 3", "User profiles — SQLite session registry, auto-routing from saved district + role", "Pending"],
        ["Phase 4", "Evaluation — Frisco/Plano LangSmith gold Q&A pairs, Faithfulness + Relevance scores", "Pending"],
        ["Phase 5", "Citations — source URLs surfaced inline in every response", "Pending"],
    ]

    _add_table(slide, MARGIN_L, BODY_Y,
               CONTENT_W, rows, col_widths=[1.5, 8.5, 2],
               header_row=True)

    _add_footer(slide, 10)


# ── Main ──────────────────────────────────────────────────────────────────────

def build():
    prs = Presentation()
    prs.slide_width  = W
    prs.slide_height = H

    slide_01_title(prs)
    slide_02_plugin(prs)
    slide_03_registry(prs)
    slide_04_isolation(prs)
    slide_05_yaml(prs)
    slide_06_langgraph(prs)
    slide_07_chromadb(prs)
    slide_08_guardrails(prs)
    slide_09_onboard(prs)
    slide_10_roadmap(prs)

    os.makedirs("exports", exist_ok=True)
    out = "exports/EdCopilot_Architecture.pptx"
    prs.save(out)
    print(f"Saved: {out}")
    return out


if __name__ == "__main__":
    build()
