/**
 * API Service Configuration
 * Central point for API URL configuration and common request functions
 */

// Determine if we should use absolute URLs or relative URLs
// In production on Netlify, we want to use relative URLs to leverage the proxy
const isProduction = import.meta.env.PROD;
const shouldUseRelativeUrls = isProduction;

// Use environment variables for API URLs, but in production use relative URLs
const API_BASE_URL = shouldUseRelativeUrls 
  ? '' // Empty string for relative URLs in production
  : (import.meta.env.VITE_API_URL || 'https://slimthicc-yt-api-latest.onrender.com');

// Ensure API_BASE_URL always uses HTTPS if it's an absolute URL
const secureApiBaseUrl = API_BASE_URL 
  ? API_BASE_URL.replace(/^http:\/\//i, 'https://') 
  : API_BASE_URL;

const API_V1_PATH = '/api/v1';

// Full API URL with version
export const API_URL = `${secureApiBaseUrl}${API_V1_PATH}`;

// API endpoints with constructed URLs
export const ENDPOINTS = {
  DOWNLOADS: `${API_URL}/downloads`,
  DOWNLOAD: (taskId: string) => `${API_URL}/downloads/${taskId}`,
  DOWNLOAD_FILE: (taskId: string) => `${API_URL}/downloads/${taskId}/file`,
};

// WebSocket URL - IMPORTANT: always use absolute URL for WebSockets
// WebSockets cannot go through Netlify proxies, so they must connect directly to backend
// Ensure WebSocket URL always uses WSS (secure WebSockets)
const WS_DIRECT_URL = 'wss://slimthicc-yt-api-latest.onrender.com';
export const WS_URL = `${WS_DIRECT_URL}${API_V1_PATH}`;

// Log the configured URLs on startup
console.log('[API Service] Configured with:');
console.log(`  API URL: ${API_URL}`);
console.log(`  WebSocket URL: ${WS_URL}`);
console.log(`  Using relative URLs for API calls: ${shouldUseRelativeUrls}`);

/**
 * Make an API request with proper error handling
 */
export async function makeRequest(url: string, options: RequestInit = {}) {
  try {
    // Ensure URL is using HTTPS
    const secureUrl = url.replace(/^http:\/\//i, 'https://');
    
    // Log the request for debugging
    console.log(`Making API request to: ${secureUrl}`);
    
    // For production, always use relative URLs for API requests
    // This ensures requests go through Netlify's proxy
    const finalUrl = isProduction 
      ? secureUrl.replace('https://slimthicc-yt-api-latest.onrender.com', '')
      : secureUrl;
    
    // Make sure URL starts with / for relative paths
    const normalizedUrl = finalUrl.startsWith('/') || finalUrl.startsWith('http') 
      ? finalUrl 
      : `/${finalUrl}`;
    
    console.log(`Using final URL: ${normalizedUrl}`);
    
    // Set up request options with MODE=cors explicitly to help with CORS
    const fetchOptions: RequestInit = {
      ...options,
      mode: 'cors',
      credentials: 'same-origin',  // Don't send cookies for cross-origin requests
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',  // Help identify AJAX requests
        ...options.headers,
      }
    };
    
    console.log('Fetch options:', JSON.stringify(fetchOptions, null, 2));
    
    const response = await fetch(normalizedUrl, fetchOptions);

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

/**
 * Special function for direct file downloads
 * This bypasses JSON parsing and returns the response directly
 */
export async function downloadFile(url: string) {
  try {
    // Ensure URL is using HTTPS
    const secureUrl = url.replace(/^http:\/\//i, 'https://');
    
    // Log the request for debugging
    console.log(`Downloading file from: ${secureUrl}`);
    
    // For production, always use relative URLs for API requests
    // This ensures requests go through Netlify's proxy
    const finalUrl = isProduction 
      ? secureUrl.replace('https://slimthicc-yt-api-latest.onrender.com', '')
      : secureUrl;
    
    // Make sure URL starts with / for relative paths
    const normalizedUrl = finalUrl.startsWith('/') || finalUrl.startsWith('http') 
      ? finalUrl 
      : `/${finalUrl}`;
    
    console.log(`Using final download URL: ${normalizedUrl}`);
    
    // For file downloads, we use different options
    const fetchOptions: RequestInit = {
      method: 'GET',
      mode: 'cors',
      credentials: 'same-origin',
      headers: {
        'X-Requested-With': 'XMLHttpRequest',
      }
    };
    
    const response = await fetch(normalizedUrl, fetchOptions);
    
    // Check for error response
    if (!response.ok) {
      // Try to parse error message if possible
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `Download failed with status ${response.status}`);
    }
    
    return response;
  } catch (error) {
    console.error('File download failed:', error);
    if (error instanceof Error) {
      throw error;
    }
    throw new Error('An unexpected error occurred during file download');
  }
} 