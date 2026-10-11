import './globals.css';
import type { Metadata } from 'next';
import { CustomCursor } from '@/components/CustomCursor';

export const metadata: Metadata = {
  title: 'Aspira – Real-Time Lab Processing Infrastructure',
  description: 'High-throughput, low-latency lab processing with millisecond response times. Built for reliability at scale.',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <CustomCursor />
        {children}
      </body>
    </html>
  );
}
