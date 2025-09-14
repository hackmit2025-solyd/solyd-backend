# Rox Challenge Presentation

This presentation demonstrates how Solyd handles real-world messy medical data for the Rox Challenge.

## Setup

1. Install dependencies:
```bash
npm install
```

2. Build the presentation:
```bash
# HTML output
npm run build --allow-local-files

# PDF output
npm run build-pdf --allow-local-files

# PowerPoint output
npm run build-pptx --allow-local-files
```

3. Development mode with live preview:
```bash
npm run serve
```

This will start a local server and open the presentation in your browser with hot reload.

## Structure

- `presentation.md` - Main presentation content in Marp markdown
- `package.json` - Build scripts and dependencies

## Technologies

- **Marp** - Markdown Presentation Ecosystem
- Supports HTML, PDF, and PPTX output
- Includes mermaid diagrams for architecture visualization