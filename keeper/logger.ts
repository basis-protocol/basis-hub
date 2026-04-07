export type LogLevel = "info" | "warn" | "error" | "debug";

export interface LogEntry {
  level: LogLevel;
  message: string;
  timestamp: string;
  [key: string]: unknown;
}

class Logger {
  private pretty: boolean;

  constructor() {
    this.pretty = process.env["LOG_PRETTY"] === "true";
  }

  private log(level: LogLevel, message: string, fields?: Record<string, unknown>): void {
    const entry: LogEntry = {
      level,
      message,
      timestamp: new Date().toISOString(),
      ...fields,
    };

    if (this.pretty) {
      const prefix = level.toUpperCase().padEnd(5);
      const fieldStr = fields ? " " + JSON.stringify(fields) : "";
      console.log(`[${entry.timestamp}] ${prefix} ${message}${fieldStr}`);
    } else {
      process.stdout.write(JSON.stringify(entry) + "\n");
    }
  }

  info(message: string, fields?: Record<string, unknown>): void {
    this.log("info", message, fields);
  }

  warn(message: string, fields?: Record<string, unknown>): void {
    this.log("warn", message, fields);
  }

  error(message: string, fields?: Record<string, unknown>): void {
    this.log("error", message, fields);
  }

  debug(message: string, fields?: Record<string, unknown>): void {
    if (process.env["LOG_LEVEL"] === "debug") {
      this.log("debug", message, fields);
    }
  }
}

export const logger = new Logger();
