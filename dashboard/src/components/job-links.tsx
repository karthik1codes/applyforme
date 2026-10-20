import { ExternalLinkIcon } from "lucide-react";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/** Posting + careers / company site links — always show the job URL to the user. */
export function JobLinks({
  url,
  applyUrl,
  careersUrl,
  companyWebsite,
  companyLinkedin,
  className,
}: {
  url: string;
  applyUrl?: string;
  careersUrl?: string;
  companyWebsite?: string;
  companyLinkedin?: string;
  className?: string;
}) {
  const post = applyUrl && applyUrl !== url ? applyUrl : url;
  const items = [
    { href: post, label: "Job posting" },
    careersUrl ? { href: careersUrl, label: "Careers page" } : null,
    companyWebsite ? { href: companyWebsite, label: "Company site" } : null,
    companyLinkedin ? { href: companyLinkedin, label: "LinkedIn" } : null,
  ].filter(Boolean) as { href: string; label: string }[];

  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {items.map((i) => (
        <a
          key={i.label + i.href}
          href={i.href}
          target="_blank"
          rel="noreferrer"
          className={cn(buttonVariants({ variant: i.label === "Job posting" ? "default" : "outline", size: "sm" }), "gap-1.5")}
        >
          <ExternalLinkIcon className="size-3.5" />
          {i.label}
        </a>
      ))}
    </div>
  );
}
