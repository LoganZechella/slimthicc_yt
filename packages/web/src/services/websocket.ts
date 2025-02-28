// import { WS_URL } from './api';

export class WebSocketService {
  private connections: Map<string, WebSocket> = new Map()
  private callbacks: Map<string, Function> = new Map()
  private baseUrl: string
  private reconnectTimeouts: Map<string, NodeJS.Timeout> = new Map()
  private maxReconnectAttempts = 10
  private reconnectAttempts: Map<string, number> = new Map()
  private pingIntervals: Map<string, NodeJS.Timeout> = new Map()
  private pingInterval = 20000 // 20 seconds
  private connectionState: Map<string, 'connecting' | 'connected' | 'disconnected'> = new Map()
  private connectionStatusCallbacks: Map<string, Function> = new Map()

  constructor() {
    // IMPORTANT: Always use direct backend WebSocket URL with WSS
    // Netlify doesn't support WebSocket proxying properly
    this.baseUrl = `wss://slimthicc-yt-api-latest.onrender.com/api/v1/downloads`;
    
    console.log('[WebSocketService] Initialized with direct backend URL:', this.baseUrl);
    
    // Add event listener for online/offline status
    window.addEventListener('online', this.handleOnline);
    window.addEventListener('offline', this.handleOffline);
    window.addEventListener('beforeunload', this.cleanup);
  }
  
  // Check if a task is already subscribed
  isSubscribed(taskId: string): boolean {
    return this.callbacks.has(taskId);
  }
  
  private handleOnline = () => {
    console.log('[WebSocketService] Network is online, reconnecting WebSockets');
    // Reconnect all existing tasks
    this.callbacks.forEach((callback, taskId) => {
      const state = this.connectionState.get(taskId);
      if (state === 'disconnected') {
        console.log(`[WebSocketService] Reconnecting WebSocket for task ${taskId} after network restored`);
        this.subscribeToTask(taskId, callback, this.connectionStatusCallbacks.get(taskId));
      }
    });
  }
  
  private handleOffline = () => {
    console.log('[WebSocketService] Network is offline, marking connections as disconnected');
    this.connections.forEach((_, taskId) => {
      this.connectionState.set(taskId, 'disconnected');
      // Notify status callbacks
      if (this.connectionStatusCallbacks.has(taskId)) {
        const statusCallback = this.connectionStatusCallbacks.get(taskId);
        if (statusCallback) {
          statusCallback('disconnected');
        }
      }
    });
  }
  
  private cleanup = () => {
    // Clean up all connections when page unloads
    this.disconnect();
    
    // Remove event listeners
    window.removeEventListener('online', this.handleOnline);
    window.removeEventListener('offline', this.handleOffline);
    window.removeEventListener('beforeunload', this.cleanup);
  }

  subscribeToTask(taskId: string, callback: Function, connectionStatusCallback?: Function): Promise<void> {
    // If already subscribed, just update the callback
    if (this.callbacks.has(taskId)) {
      console.log(`[WebSocketService] Updating existing callback for task ${taskId}`)
      this.callbacks.set(taskId, callback)
      if (connectionStatusCallback) {
        this.connectionStatusCallbacks.set(taskId, connectionStatusCallback);
      }
      return Promise.resolve()
    }

    // Try multiple endpoint patterns in sequence if needed
    // This increases resilience if the server API changes
    const wsUrl = `${this.baseUrl}/${taskId}/ws`;
    console.log(`[WebSocketService] Connecting to WebSocket: ${wsUrl}`)

    // Store the callbacks
    this.callbacks.set(taskId, callback)
    if (connectionStatusCallback) {
      this.connectionStatusCallbacks.set(taskId, connectionStatusCallback);
    }
    
    // Set initial connection state
    this.connectionState.set(taskId, 'connecting');
    
    // Update connection status callback if provided
    if (connectionStatusCallback) {
      connectionStatusCallback('connecting');
    }
    
    // Reset reconnect attempts
    this.reconnectAttempts.set(taskId, 0);

    // Create a new WebSocket connection
    return new Promise((resolve, reject) => {
      try {
        console.log(`[WebSocketService] Creating new WebSocket connection to ${wsUrl}`);
        
        // Direct connection to backend WebSocket URL
        const ws = new WebSocket(wsUrl);
        
        // Add a timeout for the initial connection
        const connectionTimeout = setTimeout(() => {
          console.error(`[WebSocketService] Connection timeout for task ${taskId}`);
          // Only reject if the connection is still pending
          if (this.connectionState.get(taskId) === 'connecting') {
            ws.close();
            reject(new Error(`WebSocket connection timed out for task ${taskId}`));
          }
        }, 15000); // 15 second timeout for initial connection
        
        ws.onopen = () => {
          console.log(`[WebSocketService] WebSocket connection opened for task ${taskId}`);
          
          // Clear the connection timeout
          clearTimeout(connectionTimeout);
          
          this.connections.set(taskId, ws);
          this.connectionState.set(taskId, 'connected');
          
          // Notify status callback
          if (this.connectionStatusCallbacks.has(taskId)) {
            const statusCallback = this.connectionStatusCallbacks.get(taskId);
            if (statusCallback) {
              statusCallback('connected');
            }
          }
          
          // Clear any existing reconnect timeout
          if (this.reconnectTimeouts.has(taskId)) {
            clearTimeout(this.reconnectTimeouts.get(taskId));
            this.reconnectTimeouts.delete(taskId);
          }
          
          // Reset reconnect attempts on successful connection
          this.reconnectAttempts.set(taskId, 0);
          
          // Set up ping interval to keep connection alive
          this.setupPingInterval(taskId, ws);
          
          // Wait a short time before sending hello message to ensure connection is stable
          setTimeout(() => {
            try {
              // Send an initial "hello" message to the server to request current status
              // Format expected by server: { type: "hello", task_id: "..." }
              ws.send(JSON.stringify({ 
                type: 'hello',
                task_id: taskId, // Ensure we use task_id key as expected by server
                timestamp: Date.now()
              }));
              console.log(`[WebSocketService] Sent initial hello message for task ${taskId}`);
            } catch (error) {
              console.error(`[WebSocketService] Error sending hello message for task ${taskId}:`, error);
            }
          }, 500); // Wait 500ms
          
          resolve();
        }
        
        ws.onmessage = (event) => {
          try {
            const data = JSON.parse(event.data)
            
            // Handle pong messages separately
            if (data.type === 'pong') {
              console.log(`[WebSocketService] Received pong from server for task ${taskId}`)
              return
            }
            
            // Handle connection status messages
            if (data.type === 'connection_status') {
              console.log(`[WebSocketService] Connection status for task ${taskId}: ${data.status}`)
              
              // Notify status callback
              if (this.connectionStatusCallbacks.has(taskId)) {
                const statusCallback = this.connectionStatusCallbacks.get(taskId);
                if (statusCallback) {
                  statusCallback(data.status);
                }
              }
              
              return
            }
            
            // Handle ping messages from server
            if (data.type === 'ping') {
              // Send pong response
              ws.send(JSON.stringify({ 
                type: 'pong', 
                timestamp: data.timestamp,
                client_timestamp: Date.now()
              }))
              console.log(`[WebSocketService] Responded to server ping for task ${taskId}`)
              return
            }
            
            // For all other messages, invoke the callback
            if (this.callbacks.has(taskId)) {
              const callback = this.callbacks.get(taskId)
              if (callback) {
                console.log(`[WebSocketService] Received data for task ${taskId}:`, 
                  data.type || 'status update')
                callback(data)
              }
            }
          } catch (error) {
            console.error(`[WebSocketService] Error parsing WebSocket message for task ${taskId}:`, error)
            console.log('Raw message data:', event.data)
          }
        }
        
        ws.onerror = (error) => {
          console.error(`[WebSocketService] WebSocket error for task ${taskId}:`, error)
          this.connectionState.set(taskId, 'disconnected');
          
          // Notify status callback
          if (this.connectionStatusCallbacks.has(taskId)) {
            const statusCallback = this.connectionStatusCallbacks.get(taskId);
            if (statusCallback) {
              statusCallback('disconnected');
            }
          }
          
          // Attempt to reconnect
          this.attemptReconnect(taskId, callback, connectionStatusCallback);
          
          // If this is the initial connection, reject the promise
          if (!this.connections.has(taskId)) {
            reject(new Error(`WebSocket connection failed for task ${taskId}`))
          }
        }
        
        ws.onclose = (event) => {
          console.log(`[WebSocketService] WebSocket connection closed for task ${taskId}:`, 
            event.code, event.reason)
          this.connectionState.set(taskId, 'disconnected');
          
          // Notify status callback
          if (this.connectionStatusCallbacks.has(taskId)) {
            const statusCallback = this.connectionStatusCallbacks.get(taskId);
            if (statusCallback) {
              statusCallback('disconnected');
            }
          }
          
          // Clear ping interval
          this.clearPingInterval(taskId);
          
          // If connection was closed abnormally and we still care about this task
          if ((event.code !== 1000 && event.code !== 1001) && this.callbacks.has(taskId)) {
            console.log(`[WebSocketService] Attempting to reconnect WebSocket for task ${taskId}`)
            
            // Attempt to reconnect
            this.attemptReconnect(taskId, callback, connectionStatusCallback);
          } else {
            // Clean up if closed normally
            this.connections.delete(taskId)
            
            // Also remove reconnect attempts counter if closed normally
            this.reconnectAttempts.delete(taskId);
          }
        }
      } catch (error) {
        console.error(`[WebSocketService] Error creating WebSocket for task ${taskId}:`, error)
        this.connectionState.set(taskId, 'disconnected');
        
        // Notify status callback
        if (connectionStatusCallback) {
          connectionStatusCallback('disconnected');
        }
        
        reject(error)
      }
    })
  }
  
  private setupPingInterval(taskId: string, ws: WebSocket) {
    // Clear any existing interval
    this.clearPingInterval(taskId);
    
    // Set up new interval
    const intervalId = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ 
            type: 'ping', 
            timestamp: Date.now() 
          }));
          console.log(`[WebSocketService] Sent ping to server for task ${taskId}`);
        } catch (error) {
          console.error(`[WebSocketService] Error sending ping for task ${taskId}:`, error);
          // If error sending ping, close and reconnect
          this.clearPingInterval(taskId);
          if (ws.readyState === WebSocket.OPEN) {
            ws.close();
          }
        }
      } else {
        // WebSocket not open, clear interval
        this.clearPingInterval(taskId);
      }
    }, this.pingInterval);
    
    this.pingIntervals.set(taskId, intervalId);
  }
  
  private clearPingInterval(taskId: string) {
    if (this.pingIntervals.has(taskId)) {
      clearInterval(this.pingIntervals.get(taskId));
      this.pingIntervals.delete(taskId);
    }
  }
  
  private attemptReconnect(taskId: string, callback: Function, connectionStatusCallback?: Function) {
    // Clear any existing reconnect timeout
    if (this.reconnectTimeouts.has(taskId)) {
      clearTimeout(this.reconnectTimeouts.get(taskId));
    }
    
    // Get current attempt count
    const attempts = this.reconnectAttempts.get(taskId) || 0;
    
    // Check if max attempts exceeded
    if (attempts >= this.maxReconnectAttempts) {
      console.log(`[WebSocketService] Max reconnect attempts (${this.maxReconnectAttempts}) reached for task ${taskId}`);
      
      // Notify callback about permanent disconnection
      if (this.callbacks.has(taskId) && callback) {
        try {
          callback({
            type: 'connection_error',
            status: 'error',
            error: `Failed to reconnect after ${this.maxReconnectAttempts} attempts.`,
            details: { permanent: true }
          });
        } catch (err) {
          console.error(`[WebSocketService] Error notifying callback about permanent disconnection:`, err);
        }
      }
      
      return;
    }
    
    // Increment attempt counter
    this.reconnectAttempts.set(taskId, attempts + 1);
    
    // Calculate backoff delay: 1s, 2s, 4s, 8s, etc. up to 30s max
    const delay = Math.min(Math.pow(2, attempts) * 1000, 30000);
    
    console.log(`[WebSocketService] Scheduling reconnect for task ${taskId} in ${delay}ms (attempt ${attempts + 1}/${this.maxReconnectAttempts})`);
    
    // Schedule reconnect
    const timeout = setTimeout(() => {
      // Only reconnect if still disconnected and callback still exists
      if (this.connectionState.get(taskId) === 'disconnected' && this.callbacks.has(taskId)) {
        console.log(`[WebSocketService] Executing reconnect for task ${taskId} (attempt ${attempts + 1}/${this.maxReconnectAttempts})`);
        
        // Make sure we clean up any existing connection first
        if (this.connections.has(taskId)) {
          const oldWs = this.connections.get(taskId);
          try {
            if (oldWs && oldWs.readyState !== WebSocket.CLOSED) {
              oldWs.close(1000, "Reconnecting");
            }
          } catch (err) {
            console.error(`[WebSocketService] Error closing old connection for task ${taskId}:`, err);
          }
          this.connections.delete(taskId);
        }
        
        // Now attempt to reconnect
        this.subscribeToTask(taskId, callback, connectionStatusCallback)
          .catch(err => {
            console.error(`[WebSocketService] Failed to reconnect WebSocket for task ${taskId}:`, err);
            
            // If this is the last attempt, notify the callback about permanent failure
            if (attempts + 1 >= this.maxReconnectAttempts) {
              if (this.callbacks.has(taskId) && callback) {
                try {
                  callback({
                    type: 'connection_error',
                    status: 'error',
                    error: `Failed to reconnect after ${this.maxReconnectAttempts} attempts.`,
                    details: { permanent: true }
                  });
                } catch (callbackErr) {
                  console.error(`[WebSocketService] Error notifying callback about permanent disconnection:`, callbackErr);
                }
              }
            }
          });
      }
    }, delay);
    
    this.reconnectTimeouts.set(taskId, timeout);
  }

  unsubscribeFromTask(taskId: string): void {
    console.log(`[WebSocketService] Unsubscribing from task ${taskId}`);
    
    // Clear callbacks
    this.callbacks.delete(taskId);
    this.connectionStatusCallbacks.delete(taskId);
    
    // Clear reconnect timeout if any
    if (this.reconnectTimeouts.has(taskId)) {
      clearTimeout(this.reconnectTimeouts.get(taskId));
      this.reconnectTimeouts.delete(taskId);
    }
    
    // Clear ping interval if any
    this.clearPingInterval(taskId);
    
    // Close and remove connection
    if (this.connections.has(taskId)) {
      const ws = this.connections.get(taskId);
      try {
        if (ws && ws.readyState === WebSocket.OPEN) {
          ws.close(1000, "Client unsubscribed");
        }
      } catch (error) {
        console.error(`[WebSocketService] Error closing WebSocket for task ${taskId}:`, error);
      }
      this.connections.delete(taskId);
    }
    
    // Clean up other state
    this.reconnectAttempts.delete(taskId);
    this.connectionState.delete(taskId);
  }

  disconnect(): void {
    console.log('[WebSocketService] Disconnecting all WebSockets');
    
    // Close all connections
    this.connections.forEach((_, taskId) => {
      this.unsubscribeFromTask(taskId);
    });
    
    // Clear all maps
    this.connections.clear();
    this.callbacks.clear();
    this.connectionStatusCallbacks.clear();
    this.reconnectTimeouts.clear();
    this.reconnectAttempts.clear();
    this.pingIntervals.clear();
    this.connectionState.clear();
  }

  getConnectionState(taskId: string): 'connecting' | 'connected' | 'disconnected' {
    return this.connectionState.get(taskId) || 'disconnected';
  }
}

// Create singleton instance
const websocketService = new WebSocketService();
export default websocketService; 