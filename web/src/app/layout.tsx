import type { Metadata } from "next";
import type { ReactNode } from "react";

import "@/app/globals.css";
import { AppProviders } from "@/components/app-providers";

export const metadata: Metadata = {
  title: "Photo Manager Developer Dashboard",
  description: "Operational dashboard for ingestion, scan, and asset inspection.",
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en">
      <body>
        <AppProviders>{children}</AppProviders>
      </body>
    </html>
  );
}
