import type { Metadata } from "next";
import { MarketplaceScreen } from "@/features/marketplace/marketplace-screen";

export const metadata: Metadata = { title: "Marketplace" };

export default function MarketplacePage() {
  return <MarketplaceScreen />;
}
