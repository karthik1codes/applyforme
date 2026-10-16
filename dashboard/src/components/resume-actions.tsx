import { Button, buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * "Open in Overleaf": a plain HTML form POST to Overleaf's documented endpoint
 * (https://www.overleaf.com/devs). The LaTeX travels in the form body, so nothing needs to be hosted publicly.
 */
export function OverleafButton({ tex, name }: { tex: string; name: string }) {
  return (
    <form action="https://www.overleaf.com/docs" method="post" target="_blank">
      <input type="hidden" name="encoded_snip" value={encodeURIComponent(tex)} />
      <input type="hidden" name="snip_name" value={name} />
      <input type="hidden" name="engine" value="pdflatex" />
      <Button type="submit" size="sm">
        Open in Overleaf
      </Button>
    </form>
  );
}

export function ResumeLinks({ pdf, tex }: { pdf: string | null; tex: string | null }) {
  const cls = buttonVariants({ variant: "outline", size: "sm" });
  return (
    <>
      {pdf && (
        <a className={cls} href={`/api/files/${encodeURIComponent(pdf)}`} target="_blank" rel="noreferrer">
          View PDF
        </a>
      )}
      {tex && (
        <a className={cn(cls)} href={`/api/files/${encodeURIComponent(tex)}?download`}>
          Download .tex
        </a>
      )}
    </>
  );
}
