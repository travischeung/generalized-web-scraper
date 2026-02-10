import { useEffect, useState } from "react";
import type { Product } from "./types";

const API_URL = "http://localhost:8000";

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
      <h1 className="title">Product Catalog</h1>
      <div className="grid">
        {products.map((product) => {
          const rawSrc = product.image_urls?.[0];
          const src = rawSrc
            ? `${API_URL}/image?url=${encodeURIComponent(rawSrc)}`
            : null;
          return (
            <div key={product.id} className="card">
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
          );
        })}
      </div>
    </div>
  );
}
