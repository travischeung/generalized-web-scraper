import json
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from main import run_all_pipelines
from models import Product


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run pipeline on startup and write output/products.json
    sample_files = [str(p) for p in Path("data").glob("*.html")]
    if sample_files:
        results = await run_all_pipelines(sample_files)
        products = [r for r in results if not isinstance(r, BaseException) and isinstance(r, Product)]
        out_path = Path("output/products.json")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for i, p in enumerate(products):
            d = p.model_dump()
            d["id"] = i
            payload.append(d)
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    yield


app = FastAPI(lifespan=lifespan)

# CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/products")
def get_products():
    """Return all extracted products"""
    output_file = Path("output/products.json")
    if output_file.exists():
        return json.loads(output_file.read_text())
    return []


@app.get("/products/{product_id}")
def get_product(product_id: int):
    """Return a single product by index"""
    products = get_products()
    if 0 <= product_id < len(products):
        return products[product_id]
    return {"error": "Product not found"}
