/* ──────────────────────────────────────────────────────────
 * cn() — Tailwind class merge utility
 * ────────────────────────────────────────────────────────── */
import { type ClassValue, clsx } from "clsx";

export function cn(...inputs: ClassValue[]): string {
  // Simple merge — we avoid tailwind-merge to reduce bundle.
  return clsx(inputs);
}
