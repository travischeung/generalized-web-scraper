export interface Price {
  price: number;
  currency: string;
  compare_at_price: number | null;
}

export interface Category {
  name: string;
}

export interface ProductVariant {
  sku?: string | null;
  color?: string | null;
  size?: string | null;
  price?: number | null;
  image_url?: string | null;
}

export interface Product {
  id: number;
  name: string;
  price: Price;
  description: string;
  key_features: string[];
  image_urls: string[];
  video_url: string | null;
  category: Category;
  brand: string;
  colors: string[];
  variants: ProductVariant[];
  [key: string]: unknown;
}
