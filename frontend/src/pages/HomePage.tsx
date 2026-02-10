import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import type { Product } from "../types";

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

export default function HomePage() {
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

  if (loading) return <div className="app-content">Loading…</div>;
  if (error) return <div className="app-content">Error: {error}</div>;

  return (
    <>
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
              <Link to={`/product/${product.id}`} className="card-image-wrap card-link">
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
              </Link>
              <div className="card-body">
                <Link to={`/product/${product.id}`} className="card-title-link">
                  <h2 className="card-title">{String(product.name ?? "Untitled")}</h2>
                </Link>
                {formatPrice(product) && (
                  <p className="card-price">{formatPrice(product)}</p>
                )}
              </div>
            </article>
          );
        })}
      </div>
    </>
  );
}
