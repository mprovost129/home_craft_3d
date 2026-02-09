import os
from fpdf import FPDF

# -----------------------------
# Config
# -----------------------------

EXTENSIONS = [".py", ".html", ".txt"]

RELEVANT_FOLDERS = [
    "accounts",
    "cart",
    "catalog",
    "config",
    "core",
    "dashboards",
    "legal",
    "orders",
    "payments",
    "products",
    "qa",
    "refunds",
    "reviews",
    "templates",
]

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(ROOT_DIR, "pdf_exports")
os.makedirs(OUTPUT_DIR, exist_ok=True)


# -----------------------------
# Helpers
# -----------------------------

def get_all_files(root_dir, folders, extensions):
    results = []
    for folder in folders:
        abs_folder = os.path.join(root_dir, folder)
        if not os.path.isdir(abs_folder):
            continue

        for root, _, files in os.walk(abs_folder):
            for name in files:
                if any(name.lower().endswith(ext) for ext in extensions):
                    results.append(os.path.join(root, name))

    return sorted(results)


def get_font_path():
    possible_paths = [
        os.path.join(ROOT_DIR, "pdf_exports", "fonts", "DejaVuSans.ttf"),
        os.path.join(ROOT_DIR, "DejaVuSans.ttf"),
        "C:/Windows/Fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            return path
    return None


# -----------------------------
# PDF Export
# -----------------------------

def file_to_pdf(filepath, output_dir):
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=12)
    pdf.add_page()

    font_path = get_font_path()
    if font_path:
        pdf.add_font("DejaVu", "", font_path, uni=True)
        pdf.set_font("DejaVu", size=9)
    else:
        pdf.set_font("Helvetica", size=9)

    # Explicit usable width (robust vs multi_cell(0, ...) edge cases)
    try:
        usable_w = float(pdf.epw)  # fpdf2 effective page width
    except Exception:
        # fallback: total width - left - right margins
        usable_w = float(pdf.w - pdf.l_margin - pdf.r_margin)

    def write_line(txt: str, h: float = 4.5):
        # Always start at left margin to avoid "no horizontal space" errors
        pdf.set_x(pdf.l_margin)
        # Never rely on w=0: explicitly pass usable width
        pdf.multi_cell(usable_w, h, txt)

    # Header
    rel_path = os.path.relpath(filepath, ROOT_DIR)
    pdf.set_font_size(11)
    write_line(rel_path, h=6)
    pdf.ln(2)
    pdf.set_font_size(9)

    # Body
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                # Preserve indentation better by replacing tabs with spaces
                safe = line.rstrip("\n").replace("\t", "    ")
                # Avoid fpdf2 choking on completely empty strings in some edge cases
                if safe == "":
                    write_line(" ", h=4.5)
                else:
                    write_line(safe, h=4.5)
    except Exception as e:
        write_line(f"[ERROR READING FILE] {e}", h=5)

    out_name = os.path.splitext(os.path.basename(filepath))[0] + ".pdf"
    out_path = os.path.join(output_dir, out_name)
    pdf.output(out_path)
    print(f"Exported: {rel_path}")


# -----------------------------
# Main
# -----------------------------

def main():
    files = get_all_files(ROOT_DIR, RELEVANT_FOLDERS, EXTENSIONS)

    if not files:
        print("No files found.")
        return

    for file in files:
        file_to_pdf(file, OUTPUT_DIR)

    print(f"\nAll files exported to:\n{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
