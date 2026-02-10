import { Link } from "react-router-dom";

interface LayoutProps {
  children: React.ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="app">
      <header className="site-header">
        <div className="header-main">
          <Link to="/" className="header-brand-link">
            <h1 className="header-brand">Travis&apos;s Submission</h1>
          </Link>
        </div>
      </header>
      {children}
    </div>
  );
}
