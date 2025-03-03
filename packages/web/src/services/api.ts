/**
 * API Service Configuration
 * Central point for API URL configuration and common request functions
 */

// Determine if we should use absolute URLs or relative URLs
// In production on Netlify, we want to use relative URLs to leverage the proxy
const isProduction = import.meta.env.PROD;
// Always use absolute URLs since Netlify proxy isn't working
const shouldUseRelativeUrls = false;

// Use environment variables for API URLs
// FIX: Use the correct Render server URL - this was the main issue!
const API_BASE_URL = 'https://slimthicc-yt.onrender.com';

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
  CORS_TEST: `${API_URL}/cors-test`,
};

// WebSocket URL - IMPORTANT: always use absolute URL for WebSockets
// WebSockets cannot go through Netlify proxies, so they must connect directly to backend
// Ensure WebSocket URL always uses WSS (secure WebSockets)
// FIX: Update WebSocket URL to use the correct domain
const WS_DIRECT_URL = 'wss://slimthicc-yt.onrender.com';
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
    
    // Always use absolute URLs since the Netlify proxy isn't working
    const finalUrl = secureUrl;
    
    console.log(`Using final URL: ${finalUrl}`);
    
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
    
    // Implement timeout for fetch requests to prevent hanging
    const timeoutPromise = new Promise((_, reject) => {
      setTimeout(() => reject(new Error('Request timeout after 30s')), 30000);
    });
    
    // Use Promise.race to implement timeout
    const response = await Promise.race([
      fetch(finalUrl, fetchOptions),
      timeoutPromise
    ]) as Response;

    // Try to parse JSON response
    let data;
    try {
      data = await response.json();
    } catch (jsonError) {
      console.warn('Response was not JSON:', jsonError);
      // For non-JSON responses, return an empty object with status
      data = { 
        status: response.status, 
        statusText: response.statusText,
        isJson: false 
      };
    }
    
    // Check for error response
    if (!response.ok) {
      throw new Error(data.detail || `Request failed with status ${response.status}: ${response.statusText}`);
    }

    return data;
  } catch (error) {
    console.error('API request failed:', error);
    
    // Retry with absolute URL for certain errors that might be proxy-related
    // FIX: Simplify fallback logic to always use direct backend URL
    if (error instanceof Error && 
        (error.message?.includes('Failed to fetch') || 
         error.message?.includes('Request failed with status 404'))) {
      console.log('Attempting fallback to relative URL');
      try {
        // Force HTTPS for the backend URL and construct the complete path
        let directUrl;
        // If url already has the full domain, don't add it again
        if (url.includes('slimthicc-yt.onrender.com')) {
          directUrl = url;
        } else {
          // Extract the path part after /api/v1 if present
          const pathPart = url.includes('/api/v1') 
            ? url.split('/api/v1')[1] 
            : url.startsWith('/') 
              ? url 
              : `/${url}`;
          
          directUrl = `https://slimthicc-yt.onrender.com${API_V1_PATH}${pathPart}`;
        }
        
        console.log(`Making API request to: ${directUrl}`);
        
        const directResponse = await fetch(directUrl, {
          ...options,
          mode: 'cors',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...options.headers,
          }
        });
        
        let data;
        try {
          data = await directResponse.json();
        } catch (jsonError) {
          console.warn('Response was not JSON:', jsonError);
          data = { status: directResponse.status, statusText: directResponse.statusText, isJson: false };
        }
        
        if (!directResponse.ok) {
          throw new Error(data.detail || `Request failed with status ${directResponse.status}: ${directResponse.statusText}`);
        }
        
        return data;
      } catch (directError) {
        console.error('Fallback API request also failed:', directError);
        throw directError;
      }
    }
    
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
      ? secureUrl.replace('https://slimthicc-yt.onrender.com', '')
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

/**
 * Test CORS configuration
 * This function tests if CORS is properly configured between frontend and backend
 */
export async function testCORS() {
  try {
    console.log(`Testing CORS with endpoint: ${ENDPOINTS.CORS_TEST}`);
    
    // First try the main approach
    console.log("CORS Test 1: Using fetch with normal mode: cors");
    try {
      const response = await fetch(ENDPOINTS.CORS_TEST, {
        method: 'GET',
        mode: 'cors',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json'
        }
      });
      
      if (!response.ok) {
        console.error(`CORS test 1 failed with status: ${response.status}`);
      } else {
        const data = await response.json();
        console.log(`CORS test 1 successful:`, data);
        return {
          success: true,
          ...data
        };
      }
    } catch (error) {
      console.error(`CORS test 1 failed with error:`, error);
    }
    
    // Try a different approach with XMLHttpRequest for older browsers
    console.log("CORS Test 2: Using XMLHttpRequest as fallback");
    try {
      const result = await new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('GET', ENDPOINTS.CORS_TEST);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.onload = function() {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText));
            } catch (e) {
              resolve({ raw: xhr.responseText });
            }
          } else {
            reject(new Error(`Status ${xhr.status}: ${xhr.statusText}`));
          }
        };
        xhr.onerror = function() {
          reject(new Error('Network error occurred'));
        };
        xhr.send();
      });
      
      console.log(`CORS test 2 successful:`, result);
      return {
        success: true,
        ...result as Record<string, any>
      };
    } catch (error) {
      console.error(`CORS test 2 failed with error:`, error);
    }
    
    // Try a third approach with no-cors mode (will get opaque response)
    console.log("CORS Test 3: Using fetch with no-cors mode");
    try {
      const response = await fetch(ENDPOINTS.CORS_TEST, {
        method: 'GET',
        mode: 'no-cors',
      });
      
      console.log(`CORS test 3 response type:`, response.type);
      console.log(`CORS test 3 status:`, response.status);
      
      return {
        success: response.type === 'opaque' || response.status === 0,
        message: "Received opaque response with no-cors mode, which means the server exists but CORS headers are not set correctly"
      };
    } catch (error) {
      console.error(`CORS test 3 failed with error:`, error);
    }
    
    return {
      success: false,
      message: "All CORS tests failed, please check server configuration"
    };
  } catch (error) {
    console.error(`CORS test failed with error:`, error);
    return {
      success: false,
      error: String(error)
    };
  }
} 