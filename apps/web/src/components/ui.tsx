import { cva, type VariantProps } from "class-variance-authority";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";
import { cn } from "../lib/utils";

const buttonVariants = cva(
  "inline-flex min-h-10 items-center justify-center gap-2 rounded-md px-3.5 py-2 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-cyan-400 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-zinc-950 text-white hover:bg-zinc-800",
        secondary: "bg-zinc-100 text-zinc-950 hover:bg-zinc-200",
        outline: "border border-zinc-200 bg-white text-zinc-950 hover:bg-zinc-50",
        ghost: "text-zinc-600 hover:bg-zinc-100 hover:text-zinc-950",
        accent: "bg-cyan-500 text-zinc-950 hover:bg-cyan-400",
      },
      size: {
        sm: "min-h-8 px-2.5 text-xs",
        md: "min-h-10",
        lg: "min-h-11 px-5",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "md",
    },
  },
);

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return <button className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return <article className={cn("rounded-lg border border-zinc-200 bg-white p-5 shadow-sm", className)} {...props} />;
}

export function Badge({ children, tone = "muted" }: { children: ReactNode; tone?: "ok" | "warn" | "danger" | "muted" }) {
  const tones = {
    ok: "border-emerald-200 bg-emerald-50 text-emerald-700",
    warn: "border-amber-200 bg-amber-50 text-amber-700",
    danger: "border-red-200 bg-red-50 text-red-700",
    muted: "border-zinc-200 bg-zinc-50 text-zinc-600",
  };
  return <span className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium", tones[tone])}>{children}</span>;
}

export function SectionTitle({ eyebrow, title, children }: { eyebrow?: string; title: string; children?: ReactNode }) {
  return (
    <div className="mb-4">
      {eyebrow ? <p className="mb-1 text-xs font-semibold uppercase tracking-[0.16em] text-cyan-700">{eyebrow}</p> : null}
      <h2 className="text-xl font-semibold tracking-tight text-zinc-950">{title}</h2>
      {children ? <p className="mt-1 max-w-3xl text-sm leading-6 text-zinc-500">{children}</p> : null}
    </div>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50 p-8 text-center">
      <p className="font-medium text-zinc-900">{title}</p>
      {children ? <p className="mt-2 text-sm text-zinc-500">{children}</p> : null}
    </div>
  );
}
