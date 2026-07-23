import os
import re
import time
import datetime
import wikipediaapi

# Wikipedia articles to download and convert to markdown for RAG
ARTICLES = [
    "Antoni Gaudí",
    "Sagrada Família",
    "Park Güell",
    "Casa Batlló",
]

OUTPUT_DIR = "./knowledge_base"
LANGUAGE = "en"

# discarded sections when converting to markdown
SKIP_SECTIONS = {
    "see also", "references", "external links", "notes",
    "further reading", "bibliography", "gallery", "citations",
}

os.makedirs(OUTPUT_DIR, exist_ok=True)

wiki = wikipediaapi.Wikipedia(
    user_agent="CulturaVivaRAGBot/1.0 (contact@example.com)",
    language=LANGUAGE,
)


def clean_text(text: str) -> str:
    """Clean up text by removing unwanted whitespace and formatting."""
    # remove excessive newlines and trailing whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    return text.strip()


def sections_to_markdown(sections, depth=2) -> str:
    """Convert Wikipedia sections to markdown format recursively."""
    md = []
    for section in sections:
        if section.title.strip().lower() in SKIP_SECTIONS:
            continue
        if section.text.strip():
            md.append(f"{'#' * depth} {section.title}\n\n{clean_text(section.text)}")
        if section.sections:
            md.append(sections_to_markdown(section.sections, depth=min(depth + 1, 6)))
    return "\n\n".join(part for part in md if part)


def slugify(title: str) -> str:
    """Create a filesystem-friendly filename from the article title."""
    filename = title.lower().replace(" ", "_").replace("/", "_")
    return re.sub(r"[^\w\-]", "", filename)


def download_article(title: str) -> None:
    """Download a Wikipedia article and save it as a markdown file."""
    page = wiki.page(title)
    if not page.exists():
        print(f"Page not found: {title}")
        return

    filename = slugify(title) + ".md"
    filepath = os.path.join(OUTPUT_DIR, filename)

    frontmatter = (
        f"---\n"
        f"title: {page.title}\n"
        f"source_url: {page.fullurl}\n"
        f"retrieved: {datetime.date.today().isoformat()}\n"
        f"---\n\n"
    )

    body = f"# {page.title}\n\n{clean_text(page.summary)}\n\n"
    body += sections_to_markdown(page.sections)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(frontmatter + body)

    print(f"Downloaded: {filename}")


def main() -> None:
    """Main function to download specified Wikipedia articles."""
    for title in ARTICLES:
        try:
            download_article(title)
        except Exception as e:
            print(f"Error downloading '{title}': {e}")
        time.sleep(1)  


if __name__ == "__main__":
    main()