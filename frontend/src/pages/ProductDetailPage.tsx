import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
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

export default function ProductDetailPage() {
  const { productId } = useParams<{ productId: string }>();
  const [product, setProduct] = useState<Product | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedSize, setSelectedSize] = useState<string | null>(null);
  const [selectedColor, setSelectedColor] = useState<string | null>(null);
  const [selectedImageIndex, setSelectedImageIndex] = useState(0);

  useEffect(() => {
    if (productId == null) return;
    fetch(`${API_URL}/products/${productId}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(res.statusText))))
      .then((data: Product) => {
        setProduct(data);
        const variantColors = (data.variants ?? []).map((v) => v.color).filter((c): c is string => Boolean(c));
        const colors = [...new Set([...(data.colors ?? []), ...variantColors])];
        setSelectedColor(colors[0] ?? null);
      })
      .catch((err) => setError(err.message ?? "Failed to load product"))
      .finally(() => setLoading(false));
  }, [productId]);

  if (loading) return <div className="pdp-content">Loading…</div>;
  if (error) return <div className="pdp-content">Error: {error}</div>;
  if (!product) return null;

  const imageUrls = product.image_urls ?? [];
  const variants = product.variants ?? [];
  const sizes = variants.map((v) => v.size).filter((s): s is string => Boolean(s));
  const hasSizes = sizes.length > 0;
  const colorOptions = [...new Set((product.colors ?? []).concat(variants.map((v) => v.color).filter((c): c is string => Boolean(c))))];
  const hasColors = colorOptions.length > 0;
  const selectedVariant = selectedColor ? variants.find((v) => v.color === selectedColor) : null;
  const variantImageUrl = selectedVariant?.image_url ?? null;
  const displayImageUrl = variantImageUrl ?? imageUrls[selectedImageIndex] ?? imageUrls[0];

  return (
    <div className="pdp-content">
      <Link to="/" className="pdp-back">← Back</Link>
      <div className="pdp-layout">
        {/* Left: Product imagery */}
        <div className="pdp-images">
          <div className="pdp-image-main-wrap">
            {(displayImageUrl || imageUrls.length > 0) ? (
              <img
                src={`${API_URL}/image?url=${encodeURIComponent(displayImageUrl ?? imageUrls[0])}`}
                alt=""
                className="pdp-image-main"
                onError={(e) => (e.currentTarget.style.display = "none")}
              />
            ) : (
              <div className="pdp-image-placeholder">No image</div>
            )}
          </div>
          {imageUrls.length > 1 && !variantImageUrl && (
            <div className="pdp-image-thumbs">
              {imageUrls.slice(0, 4).map((url, i) => (
                <button
                  key={i}
                  type="button"
                  className={`pdp-thumb ${selectedImageIndex === i ? "pdp-thumb-active" : ""}`}
                  onClick={() => setSelectedImageIndex(i)}
                >
                  <img
                    src={`${API_URL}/image?url=${encodeURIComponent(url)}`}
                    alt=""
                    onError={(e) => (e.currentTarget.style.display = "none")}
                  />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Right: Product details */}
        <div className="pdp-details">
          <h1 className="pdp-title">{product.name ?? "Untitled"}</h1>

          {hasColors && (
            <div className="pdp-color-section">
              <label className="pdp-color-label">Color:</label>
              <div className="pdp-color-buttons">
                {colorOptions.map((color) => (
                  <button
                    key={color}
                    type="button"
                    className={`pdp-color-btn ${selectedColor === color ? "pdp-color-btn-active" : ""}`}
                    onClick={() => setSelectedColor(color)}
                  >
                    {color}
                  </button>
                ))}
              </div>
            </div>
          )}


          <div className="pdp-price-row">
            <span className="pdp-price">{formatPrice(product)}</span>
          </div>

          {hasSizes && (
            <div className="pdp-size-section">
              <div className="pdp-size-header">
                <label className="pdp-size-label">Size:</label>
                <a href="#size-guide" className="pdp-size-guide">Find your size</a>
              </div>
              <div className="pdp-size-buttons">
                {sizes.map((size) => (
                  <button
                    key={size}
                    type="button"
                    className={`pdp-size-btn ${selectedSize === size ? "pdp-size-btn-active" : ""}`}
                    onClick={() => setSelectedSize(size)}
                  >
                    {size}
                  </button>
                ))}
              </div>
            </div>
          )}

          <button type="button" className="pdp-add-to-cart">
            Add to cart
          </button>

          {product.description && (
            <>
              <h3 className="pdp-block-label">Description</h3>
              <p className="pdp-description">{product.description}</p>
            </>
          )}

          {product.key_features && product.key_features.length > 0 && (
            <>
              <h3 className="pdp-block-label">Key Features</h3>
              <ul className="pdp-features">
              {product.key_features.map((f, i) => (
                <li key={i}>{f}</li>
              ))}
              </ul>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
