import './globals.css';
import TopNav from './components/TopNav';

export const metadata = {
  title: 'Voice AI Platform',
  description: 'Self-hosted voice agents — dashboard',
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-black font-[system-ui] text-white antialiased">
        <TopNav />
        <main className="min-w-0 px-6 py-8 md:px-10 md:py-10">{children}</main>
      </body>
    </html>
  );
}
