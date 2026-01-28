/**
 * Application configuration.
 *
 * Uses Vite environment variables for build-time configuration.
 * Set VITE_API_URL in .env.development or .env.production.
 */

export const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
