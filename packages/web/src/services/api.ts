/**
 * API Service Configuration
 * Central point for API URL configuration and common request functions
 */

// Use environment variables for API URLs
const API_BASE_URL = import.meta.env.VITE_API_URL || 'https://slimthicc-yt-api-latest.onrender.com';
const API_V1_PATH = '/api/v1';

// Full API URL with version
export const API_URL = `${API_BASE_URL}${API_V1_PATH}`;

// API endpoints with absolute URLs
export const ENDPOINTS = {
  DOWNLOADS: `${API_URL}/downloads`,
  DOWNLOAD: (taskId: string) => `${API_URL}/downloads/${taskId}`,
  DOWNLOAD_FILE: (taskId: string) => `${API_URL}/downloads/${taskId}/file`,
};

// WebSocket URL
export const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'wss://slimthicc-yt-api-latest.onrender.com';
export const WS_URL = `${WS_BASE_URL}${API_V1_PATH}`;

/**
 * Make an API request with proper error handling
 */
export async function makeRequest(url: string, options: RequestInit = {}) {
  try {
    // Log the request for debugging
    console.log(`Making API request to: ${url}`);
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    // Try to parse JSON response
    const data = await response.json().catch(() => ({}));
    
    // Check for error response
    if (!response.ok) {
      throw new Error(data.detail || `Request failed with status ${response.status}`);
    }

    return data;
  } catch (error) {
    console.error('API request failed:', error);
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('An unexpected error occurred');
  }
}

/**
 * Log detailed information about API requests for debugging
 */
export function logApiCall(endpoint: string, method: string, body?: any) {
  console.log(`API ${method} request to ${endpoint}`, body ? { body } : '');
} 