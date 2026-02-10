import { useEffect, useState } from "react";
import type { Product } from "./types";

const API_URL = "http://localhost:8000";

function formatPrice(product: Product): string {
  const price = product.price?.price;
  const currency = (product.price?.currency?.trim()) || "USD";
  if (price == null) return "";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
  }).format(price);
}

export default function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${API_URL}/products`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))))
      .then((data: Product[]) => {
        setProducts(Array.isArray(data) ? data : []);
      })
      .catch((err) => setError(err.message ?? "Failed to load products"))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="app">Loading…</div>;
  if (error) return <div className="app">Error: {error}</div>;

  return (
    <div className="app">
      <header className="site-header">
        <div className="header-promo">
          <p className="header-promo-text">Final Reduction - 40% off all Seasonal Sale</p>
          <p className="header-promo-links">
            <a href="#menswear">Shop menswear</a>
            <span className="header-promo-sep">|</span>
            <a href="#womenswear">Shop womenswear</a>
          </p>
        </div>
        <div className="header-main">
          <h1 className="header-brand">Travis&apos;s Submission</h1>
        </div>
      </header>
      <h1 className="title">Product Catalog</h1>
      <div className="grid">
        {products.map((product) => {
          const imageUrls = product.image_urls ?? [];
          const firstImg = imageUrls[0];
          const src = firstImg
            ? `${API_URL}/image?url=${encodeURIComponent(firstImg)}`
            : null;

          return (
            <article key={product.id} className="card">
              <div className="card-image-wrap">
                <div className="card-placeholder">
                  {!src && <span className="card-placeholder-label">No image</span>}
                </div>
                {src && (
                  <img
                    src={src}
                    alt=""
                    className="card-image"
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                )}
              </div>
              <div className="card-body">
                <h2 className="card-title">{String(product.name ?? "Untitled")}</h2>
                {formatPrice(product) && (
                  <p className="card-price">{formatPrice(product)}</p>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
