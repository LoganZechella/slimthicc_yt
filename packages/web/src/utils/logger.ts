/**
 * Simple logger utility for client-side logging
 */

// Determine if we should enable verbose logging
const isDev = process.env.NODE_ENV === 'development';

class Logger {
  private prefix: string = '[SpotifyDownloader]';

  /**
   * Log an informational message
   */
  info(message: string, ...args: any[]): void {
    if (isDev) {
      console.info(`${this.prefix} ${message}`, ...args);
    }
  }

  /**
   * Log a warning message
   */
  warn(message: string, ...args: any[]): void {
    console.warn(`${this.prefix} ${message}`, ...args);
  }

  /**
   * Log an error message
   */
  error(message: string, ...args: any[]): void {
    console.error(`${this.prefix} ${message}`, ...args);
  }

  /**
   * Log a debug message (only in development)
   */
  debug(message: string, ...args: any[]): void {
    if (isDev) {
      console.debug(`${this.prefix} ${message}`, ...args);
    }
  }
}

export const logger = new Logger(); 