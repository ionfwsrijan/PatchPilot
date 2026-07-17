import { ArrowRight, FileSearch, ShieldCheck, Wrench } from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/button";
import { SplitText } from "../components/split-text";

export function Landing() {
  return (
    <main className="min-h-screen bg-background text-foreground">
      <section className="mx-auto flex min-h-screen w-full max-w-6xl flex-col items-center justify-center px-4 py-16 text-center sm:px-6 lg:px-8">
        <div className="mb-8 inline-flex items-center rounded-full border border-border bg-muted px-4 py-2 text-sm font-medium text-muted-foreground">
          Security scans, fixes, and evidence in one focused workspace
        </div>

        <h1 className="max-w-5xl text-4xl font-bold tracking-tight sm:text-6xl lg:text-7xl">
          <SplitText text="Welcome to PatchPilot!" />
        </h1>

        <p className="mt-6 max-w-2xl text-base leading-7 text-muted-foreground sm:text-lg">
          PatchPilot scans your codebase for vulnerable dependencies, exposed
          secrets, and risky patterns, then helps you review findings, generate
          fix suggestions, verify changes, and export audit-ready evidence.
        </p>

        <div className="mt-8 flex flex-col items-center gap-3 sm:flex-row">
          <Link to="/dashboard">
            <Button size="lg" className="h-11 px-6">
              Start a scan &gt;
            </Button>
          </Link>
        </div>

        <div className="mt-14 grid w-full grid-cols-1 gap-4 text-left md:grid-cols-3">
          <div className="rounded-lg border border-border bg-card p-5">
            <FileSearch className="mb-4 h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold">Scan</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Upload a ZIP or import a repository URL to run Semgrep, OSV, and
              secrets checks.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-5">
            <Wrench className="mb-4 h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold">Patch</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Review prioritized findings and prepare targeted remediation steps
              for high-impact issues.
            </p>
          </div>
          <div className="rounded-lg border border-border bg-card p-5">
            <ShieldCheck className="mb-4 h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold">Verify</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">
              Validate the work in a sandbox and export evidence for audit and
              compliance review.
            </p>
          </div>
        </div>
      </section>
    </main>
  );
}
