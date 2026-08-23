import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Synapse | Decision provenance",
  description: "Evidence-grounded decision audit for government workflows",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return <html lang="en"><body>{children}</body></html>;
}
