import type { Metadata, Viewport } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const forwardedHost = requestHeaders.get("x-forwarded-host");
  const rawHost = forwardedHost ?? requestHeaders.get("host") ?? "localhost:3000";
  const host = /^[a-z0-9.-]+(?::\d+)?$/i.test(rawHost) ? rawHost : "localhost:3000";
  const forwardedProto = requestHeaders.get("x-forwarded-proto");
  const protocol = forwardedProto === "http" || forwardedProto === "https"
    ? forwardedProto
    : host.startsWith("localhost")
      ? "http"
      : "https";
  const metadataBase = new URL(`${protocol}://${host}`);
  const description = "四種決策機制，同一份證據；看見角色交換如何改變判斷。";

  return {
    metadataBase,
    title: {
      default: "立場交換研究室｜多代理人投資辯論",
      template: "%s｜立場交換研究室",
    },
    description,
    applicationName: "立場交換研究室",
    keywords: ["多代理人", "角色交換", "投資研究", "辯論", "決策支援"],
    openGraph: {
      type: "website",
      locale: "zh_TW",
      siteName: "立場交換研究室",
      title: "立場交換研究室｜多代理人投資辯論",
      description,
      images: [{ url: "/og.png", width: 1733, height: 909, alt: "立場交換研究室社群分享圖" }],
    },
    twitter: {
      card: "summary_large_image",
      title: "立場交換研究室｜多代理人投資辯論",
      description,
      images: ["/og.png"],
    },
  };
}

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: "#f7f4ee",
  colorScheme: "light",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-Hant-TW">
      <body>{children}</body>
    </html>
  );
}
