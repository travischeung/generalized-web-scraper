```markdown
# Travis's Submission for Channel3 Take Home Assignment

Product extraction pipeline: HTML → structured Product JSON.

## Setup

### Backend

The backend uses Python 3.12+ and [uv](https://github.com/astral-sh/uv) for dependency management.

```bash
# Install uv if needed: https://docs.astral.sh/uv/getting-started/installation/
uv sync
```

Create a `.env` file in the project root with `OPEN_ROUTER_API_KEY` for AI extraction (OpenRouter/LLM calls).

### API

The API is a FastAPI app served with uvicorn. It runs the extraction pipeline on startup and exposes product data.

```bash
uv run uvicorn api:app --reload
```

The API listens on `http://localhost:8000` by default. See `api.py` for endpoints.

### Frontend

The frontend is a React + Vite + TypeScript app.

```bash
cd frontend
npm install
npm run dev
```

The dev server runs at `http://localhost:5173`. The frontend calls the API at `http://localhost:8000`—ensure the API is running for product data to load.

---

## Architecture Overview

<!-- Fill in the sections below. Use the guiding questions to shape your overview. -->

### High-Level Flow

**User experience:** Open the app → browse product grid → click a product → 
see full detail page (images, variants, features, pricing, description).

**Extraction:** The pipeline runs once on API startup. It processes each HTML 
file in `/data`, extracts product data through a two-stage approach (structured 
extraction + content distillation), calls the LLM to hydrate the Product schema, 
and writes results to `products.json`. After startup, the API just serves this 
cached JSON—no re-extraction per request.

**Data flow:**
1. Raw HTML → Parse structured data (JSON-LD, meta tags) + distill content (Markdown)
2. Extract images → Filter for quality → Deduplicate
3. LLM receives: structured data + distilled content + verified images
4. LLM outputs: Complete Product JSON matching schema
5. API exposes at `/products` and `/products/{id}`
6. React frontend fetches and renders

**Trigger:** Extraction happens automatically when you start the API server 
(`uvicorn api:app`). Takes ~30 seconds for 6 products. Frontend polls the API 
once loaded—if extraction isn't done yet, you'll see a loading state.


### Extraction Pipeline

The pipeline has two stages:

**Stage 1: Deterministic extraction** (html_parser.py)
- BeautifulSoup pulls structured data: JSON-LD, meta tags, embedded JSON
- Trafilatura distills the main content to clean Markdown (Think Readability or Reader Mode on browsers)
- Why both? BeautifulSoup alone gives you noisy HTML (ads, navigation). 
  Trafilatura alone might discard important structured metadata. The 
  combination preserves high-fidelity data while getting clean content.

**Stage 2: LLM hydration** (ai.py)
- Receives: structured data (truth sheet) + distilled content + verified images
- Outputs: Complete Product JSON matching the Pydantic schema
- Why LLM? Product pages are messy and diverse. A single generic prompt 
  handles Nike, Patagonia, L.L.Bean, etc. without site-specific logic.

**Image processing** (image_processor.py) runs in parallel:
- Extracts image URLs from HTML
- Async filters for quality (dimensions, aspect ratio, file type)
- Deduplicates based on e-commerce URL patterns
- Only verified images go to the LLM for final selection

### Data Flow

**Where does input data come from?**
- The input data is a collection of raw HTML product pages, stored in the `/data` directory. There are no live API fetches or third-party scraping; extraction runs locally on these files when the API server starts.

**How does data move between backend, API, and frontend?**
- On server startup, the backend parses and processes each HTML file, runs content extraction and LLM-based schema population, and writes the results to a single `products.json` file. This JSON is then served by the API at `/products` (all products) and `/products/{id}` (single product). The frontend fetches product data by calling these API endpoints, and renders product detail and grids from the cached JSON. There is no per-request extraction or recomputation; everything is precomputed and cached until the API is restarted.

**What is the shape of the Product model and where is it defined?**
- The Product model is a strict Pydantic schema (see `models.py`) with fields for name, brand, price (object with currency and compare-at price), description, key features (list), image URLs, video URL, category (object), colors (list), and variants (list of SKU/color/size/price/image). The LLM is prompted to return outputs that match this schema exactly, which is then validated before being written to `products.json`.

### Component Responsibilities

**html_parser.py**  
- Responsible for extracting structured data from each HTML file.  
- Pulls JSON-LD (schema.org), embedded JSON (like `__NEXT_DATA__`), meta tags, and other high-confidence fields.  
- Also distills the main content to Markdown using Trafilatura, striking a balance between structured metadata (which can be incomplete) and readable page content (which can be noisy).  
- Outputs a “truth sheet” with the best-known answers from machine-readable sources, plus the distilled Markdown for context.

**image_processor.py**  
- Takes raw image URLs from HTML and applies filtering logic.  
- Filters out obvious non-product images (tiny dimensions, ultra-wide banners, bad file types, ad beacons).  
- Prefers candidates that look like e-commerce product URLs (by path, dimensions, etc.).  
- Deduplicates by image identity to avoid repeated content and selects for highest quality (bigger, cleaner images, less likely to be banners or collages).

**api.py**  
- On startup, coordinates the extraction pipeline: parses HTML, processes images, runs the LLM, and writes everything out to `products.json`.  
- API endpoints just read this cached JSON (no live recompute).  
- No per-request scraping; data is only updated when you restart the server (re-extracts everything on boot).


```