import { CookieConsent } from "@/components/cookie-consent";

export default function MarketingLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="landing-skin bg-black text-white">
      {children}
      <CookieConsent />
    </div>
  );
}
