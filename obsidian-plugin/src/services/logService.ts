export type LogLevel = "info" | "warn" | "error" | "debug";

export interface LogEntry {
  ts: string;
  level: LogLevel;
  message: string;
  data?: Record<string, string | number | boolean | null>;
}

const MAX = 500;

export class LogService {
  private entries: LogEntry[] = [];
  private listeners = new Set<() => void>();

  subscribe(fn: () => void): () => void {
    this.listeners.add(fn);
    return () => this.listeners.delete(fn);
  }

  private push(level: LogLevel, message: string, data?: LogEntry["data"]): void {
    // never log secrets
    const safe = { ...(data || {}) };
    for (const k of Object.keys(safe)) {
      if (/token|password|secret|key/i.test(k)) {
        safe[k] = "[redacted]";
      }
    }
    this.entries.push({
      ts: new Date().toISOString(),
      level,
      message,
      data: safe,
    });
    if (this.entries.length > MAX) {
      this.entries = this.entries.slice(-MAX);
    }
    for (const fn of this.listeners) fn();
  }

  info(message: string, data?: LogEntry["data"]): void {
    this.push("info", message, data);
  }
  warn(message: string, data?: LogEntry["data"]): void {
    this.push("warn", message, data);
  }
  error(message: string, data?: LogEntry["data"]): void {
    this.push("error", message, data);
  }
  debug(message: string, data?: LogEntry["data"]): void {
    this.push("debug", message, data);
  }

  getEntries(): LogEntry[] {
    return this.entries.slice();
  }

  clear(): void {
    this.entries = [];
    for (const fn of this.listeners) fn();
  }
}
