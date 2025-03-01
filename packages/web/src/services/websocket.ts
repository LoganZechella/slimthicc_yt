// import { WS_URL } from './api';
import { WS_URL } from './api';

export class WebSocketService {
  private connections: Map<string, WebSocket> = new Map()
  private callbacks: Map<string, Function> = new Map()
  private baseUrl: string
  private reconnectTimeouts: Map<string, NodeJS.Timeout> = new Map()
  private maxReconnectAttempts = 15 // Increase max reconnect attempts
  private reconnectAttempts: Map<string, number> = new Map()
  private pingIntervals: Map<string, NodeJS.Timeout> = new Map()
  private pingInterval = 10000 // 10 seconds - more frequent pings
  private connectionState: Map<string, 'connecting' | 'connected' | 'disconnected'> = new Map()
  private connectionStatusCallbacks: Map<string, Function> = new Map()
  private lastHeartbeatReceived: Map<string, number> = new Map() // Track last heartbeat time
  private heartbeatCheckIntervals: Map<string, NodeJS.Timeout> = new Map() // For checking heartbeat timeouts
  private heartbeatTimeout = 25000 // Consider connection stale after 25 seconds without heartbeat

  constructor() {
    // Use the centralized WS_URL from api.ts instead of hardcoding the URL
    this.baseUrl = WS_URL + '/downloads';
    
    console.log('[WebSocketService] Initialized with WebSocket URL:', this.baseUrl);
    
    // Add event listener for online/offline status
    window.addEventListener('online', this.handleOnline);
    window.addEventListener('offline', this.handleOffline);
    window.addEventListener('beforeunload', this.cleanup);
    // Also reconnect websockets when tab becomes visible
    document.addEventListener('visibilitychange', this.handleVisibilityChange);
  }
  
  // Check if a task is already subscribed
  isSubscribed(taskId: string): boolean {
    return this.callbacks.has(taskId);
  }
  
  private handleVisibilityChange = () => {
    if (document.visibilityState === 'visible') {
      console.log('[WebSocketService] Tab became visible, checking connections');
      // Check all connections and reconnect if needed
      this.callbacks.forEach((_, taskId) => {
        const state = this.connectionState.get(taskId);
        if (state !== 'connected') {
          console.log(`[WebSocketService] Tab visible: Reconnecting WebSocket for task ${taskId}`);
          this.reconnect(taskId).catch(err => {
            console.error(`[WebSocketService] Failed to reconnect on visibility change:`, err);
          });
        } else {
          // Even if connected, send a ping to verify connection is still alive
          this.sendPing(taskId);
        }
      });
    }
  }
  
  private handleOnline = () => {
    console.log('[WebSocketService] Network is online, reconnecting WebSockets');
    // Reconnect all existing tasks
    this.callbacks.forEach((callback, taskId) => {
      const state = this.connectionState.get(taskId);
      if (state !== 'connected') {
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
    document.removeEventListener('visibilitychange', this.handleVisibilityChange);
  }

  subscribeToTask(taskId: string, callback: Function, connectionStatusCallback?: Function): Promise<void> {
    console.log(`[WebSocketService] Subscribing to task ${taskId}...`);
    
    // If already subscribed, clean up the existing connection first
    if (this.connections.has(taskId)) {
      console.log(`[WebSocketService] Cleaning up existing connection for task ${taskId} before resubscribing`)
      this.unsubscribeFromTask(taskId);
    }

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

    // Construct the WebSocket URL for this task
    const wsUrl = `${this.baseUrl}/${taskId}/ws`;
    console.log(`[WebSocketService] Connecting to WebSocket: ${wsUrl}`)

    // Create a new WebSocket connection
    return new Promise((resolve, reject) => {
      try {
        console.log(`[WebSocketService] Creating new WebSocket connection to ${wsUrl}`);
        
        // Check if network is available
        if (!navigator.onLine) {
          console.warn(`[WebSocketService] Network appears offline, but attempting connection anyway`);
        }
        
        // Create the WebSocket connection
        const ws = new WebSocket(wsUrl);
        
        // Store the connection immediately to prevent race conditions
        this.connections.set(taskId, ws);
        
        // Add a timeout for the initial connection
        const connectionTimeout = setTimeout(() => {
          console.error(`[WebSocketService] Connection timeout for task ${taskId}`);
          // Only reject if the connection is still pending
          if (this.connectionState.get(taskId) === 'connecting') {
            ws.close();
            this.connectionState.set(taskId, 'disconnected');
            // Notify status callback
            if (connectionStatusCallback) {
              connectionStatusCallback('disconnected');
            }
            reject(new Error(`WebSocket connection timed out for task ${taskId}`));
          }
        }, 15000); // 15 second timeout for initial connection
        
        ws.onopen = () => {
          console.log(`[WebSocketService] WebSocket connection opened for task ${taskId}`);
          
          // Clear the connection timeout
          clearTimeout(connectionTimeout);
          
          this.connectionState.set(taskId, 'connected');
          this.lastHeartbeatReceived.set(taskId, Date.now());
          
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
          
          // Set up heartbeat checker
          this.setupHeartbeatChecker(taskId);
          
          // Wait a short time before sending hello message to ensure connection is stable
          setTimeout(() => {
            try {
              if (ws.readyState === WebSocket.OPEN) {
                // Send an initial "hello" message to the server to request current status
                // Make sure the format matches what the server expects
                const timestamp = Date.now();
                const helloMessage = { 
                  type: 'hello',
                  task_id: taskId,  // Server expects task_id in this format
                  timestamp
                };
                console.log(`[WebSocketService] Sending hello message:`, helloMessage);
                ws.send(JSON.stringify(helloMessage));
                console.log(`[WebSocketService] Sent initial hello message for task ${taskId}`);
                
                // Set a timeout to detect if we don't get a hello_ack
                const helloAckTimeout = setTimeout(() => {
                  if (this.connectionState.get(taskId) === 'connected') {
                    console.warn(`[WebSocketService] Did not receive hello_ack for task ${taskId} within timeout period`);
                    // We can continue anyway since we're marked as connected
                  }
                }, 5000); // Wait 5 seconds for hello_ack
                
                // Store the timeout ID so we can clear it if we get a hello_ack
                this.reconnectTimeouts.set(`hello_ack_${taskId}`, helloAckTimeout);
              } else {
                console.warn(`[WebSocketService] Could not send hello message, WebSocket not open. State: ${ws.readyState}`);
              }
            } catch (error) {
              console.error(`[WebSocketService] Error sending hello message for task ${taskId}:`, error);
            }
          }, 500); // Wait 500ms
          
          resolve();
        }
        
        ws.onmessage = (event) => {
          try {
            // Update last heartbeat time for any message received
            this.lastHeartbeatReceived.set(taskId, Date.now());
            
            // Check if we're still connected according to our state
            if (this.connectionState.get(taskId) !== 'connected') {
              console.log(`[WebSocketService] Message received but connection state is ${this.connectionState.get(taskId)}. Updating to connected.`);
              this.connectionState.set(taskId, 'connected');
              
              // Notify status callback
              if (this.connectionStatusCallbacks.has(taskId)) {
                const statusCallback = this.connectionStatusCallbacks.get(taskId);
                if (statusCallback) {
                  statusCallback('connected');
                }
              }
            }
            
            // Parse message data
            let data;
            try {
              data = JSON.parse(event.data);
              console.log(`[WebSocketService] Received message type: ${data.type || 'unknown'} for task ${taskId}`);
            } catch (parseError) {
              console.error(`[WebSocketService] Failed to parse WebSocket message:`, event.data);
              console.error(parseError);
              return;
            }
            
            // Handle pong messages separately
            if (data.type === 'pong') {
              console.log(`[WebSocketService] Received pong from server for task ${taskId}`)
              return
            }
            
            // Handle hello_ack messages
            if (data.type === 'hello_ack') {
              console.log(`[WebSocketService] Received hello acknowledgement from server for task ${taskId}`);
              
              // Clear the hello ack timeout if it exists
              const helloAckTimeoutKey = `hello_ack_${taskId}`;
              if (this.reconnectTimeouts.has(helloAckTimeoutKey)) {
                clearTimeout(this.reconnectTimeouts.get(helloAckTimeoutKey));
                this.reconnectTimeouts.delete(helloAckTimeoutKey);
              }
              
              return;
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
              if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ 
                  type: 'pong', 
                  timestamp: data.timestamp,
                  task_id: taskId, // Add task_id to pong
                  client_timestamp: Date.now()
                }));
                console.log(`[WebSocketService] Responded to server ping for task ${taskId}`);
              } else {
                console.warn(`[WebSocketService] Cannot respond to ping, WebSocket not open. State: ${ws.readyState}`);
              }
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
            console.error(`[WebSocketService] Error processing WebSocket message for task ${taskId}:`, error)
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
          
          // Clear the initial connection timeout if it exists
          clearTimeout(connectionTimeout);
          
          // Clear heartbeat checker
          this.clearHeartbeatChecker(taskId);
          
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
          
          // Only change state if we're not already disconnected
          if (this.connectionState.get(taskId) !== 'disconnected') {
            this.connectionState.set(taskId, 'disconnected');
            
            // Notify status callback
            if (this.connectionStatusCallbacks.has(taskId)) {
              const statusCallback = this.connectionStatusCallbacks.get(taskId);
              if (statusCallback) {
                statusCallback('disconnected');
              }
            }
            
            // Clear the ping interval
            this.clearPingInterval(taskId);
            
            // Clear heartbeat checker
            this.clearHeartbeatChecker(taskId);
            
            // Only attempt to reconnect if this wasn't an intentional close (code 1000)
            // and we still have the callback (meaning we haven't unsubscribed)
            if (event.code !== 1000 && this.callbacks.has(taskId)) {
              console.log(`[WebSocketService] Attempting to reconnect for task ${taskId}`);
              const storedCallback = this.callbacks.get(taskId);
              const storedStatusCallback = this.connectionStatusCallbacks.get(taskId);
              if (storedCallback) {
                this.attemptReconnect(taskId, storedCallback, storedStatusCallback || undefined);
              }
            }
          }
        }
      } catch (error) {
        console.error(`[WebSocketService] Error setting up WebSocket for task ${taskId}:`, error);
        this.connectionState.set(taskId, 'disconnected');
        
        // Notify status callback
        if (connectionStatusCallback) {
          connectionStatusCallback('disconnected');
        }
        
        reject(error);
      }
    });
  }
  
  // Setup heartbeat checker to detect stale connections
  private setupHeartbeatChecker(taskId: string) {
    // Clear any existing interval
    this.clearHeartbeatChecker(taskId);
    
    // Set current time as last heartbeat
    this.lastHeartbeatReceived.set(taskId, Date.now());
    
    // Check every 15 seconds if we've received any messages (more frequent checks)
    const intervalId = setInterval(() => {
      const lastHeartbeat = this.lastHeartbeatReceived.get(taskId) || 0;
      const now = Date.now();
      const timeSinceLastHeartbeat = now - lastHeartbeat;
      
      // If no messages for heartbeatTimeout, connection may be stale
      if (timeSinceLastHeartbeat > this.heartbeatTimeout) {
        console.warn(`[WebSocketService] No heartbeat received for ${timeSinceLastHeartbeat}ms for task ${taskId}, connection may be stale`);
        
        // If frontend shows connected but server may have lost track, force reconnect
        if (this.connectionState.get(taskId) === 'connected') {
          console.log(`[WebSocketService] Frontend shows connected state but no heartbeat, attempting reconnect for task ${taskId}`);
          this.reconnect(taskId).catch(err => {
            console.error(`[WebSocketService] Failed to force reconnect for potentially stale connection:`, err);
          });
          return;
        }
        
        // If we have a connection, check its state
        if (this.connections.has(taskId)) {
          const ws = this.connections.get(taskId);
          
          if (ws && ws.readyState === WebSocket.OPEN) {
            // Try sending a ping to see if connection is alive
            try {
              this.sendPing(taskId);
              
              // Give it a little time to get a response
              setTimeout(() => {
                const newTimeSinceHeartbeat = Date.now() - (this.lastHeartbeatReceived.get(taskId) || 0);
                
                // If still no heartbeat after ping, force reconnect
                if (newTimeSinceHeartbeat > this.heartbeatTimeout) {
                  console.log(`[WebSocketService] Still no heartbeat after ping attempt, forcing reconnect for task ${taskId}`);
                  this.reconnect(taskId).catch(err => {
                    console.error(`[WebSocketService] Failed to force reconnect for stale connection:`, err);
                  });
                }
              }, 5000); // Wait 5 seconds for ping response
            } catch (err) {
              console.error(`[WebSocketService] Error sending test ping:`, err);
              // If error sending ping, force reconnect
              this.reconnect(taskId).catch(reconnectErr => {
                console.error(`[WebSocketService] Failed to force reconnect after ping error:`, reconnectErr);
              });
            }
          } else if (ws) {
            // Connection is in a non-open state but we still have it
            console.log(`[WebSocketService] WebSocket is in ${this.getReadyStateText(ws.readyState)} state for task ${taskId}, forcing reconnect`);
            this.reconnect(taskId).catch(err => {
              console.error(`[WebSocketService] Failed to force reconnect for non-open connection:`, err);
            });
          }
        } else {
          // No connection at all
          console.log(`[WebSocketService] No WebSocket connection found for task ${taskId}, forcing reconnect`);
          // Only reconnect if we still have the callback (meaning we haven't unsubscribed)
          if (this.callbacks.has(taskId)) {
            const callback = this.callbacks.get(taskId);
            if (callback) {
              // Call reconnect with existing callback
              this.reconnect(taskId).catch(err => {
                console.error(`[WebSocketService] Failed to force reconnect for missing connection:`, err);
              });
            }
          }
        }
      }
    }, 15000); // Check every 15 seconds
    
    this.heartbeatCheckIntervals.set(taskId, intervalId);
  }
  
  // Clear heartbeat checker
  private clearHeartbeatChecker(taskId: string) {
    if (this.heartbeatCheckIntervals.has(taskId)) {
      clearInterval(this.heartbeatCheckIntervals.get(taskId));
      this.heartbeatCheckIntervals.delete(taskId);
    }
  }
  
  // Setup ping interval to keep connection alive
  private setupPingInterval(taskId: string, ws: WebSocket) {
    // Clear any existing interval
    this.clearPingInterval(taskId);
    
    // Set up new interval
    const intervalId = setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) {
        try {
          ws.send(JSON.stringify({ 
            type: 'ping', 
            timestamp: Date.now(),
            task_id: taskId // Add task_id to ping for server identification
          }));
          console.log(`[WebSocketService] Sent ping to server for task ${taskId}`);
        } catch (error) {
          console.error(`[WebSocketService] Error sending ping for task ${taskId}:`, error);
          // If error sending ping, close and reconnect
          this.clearPingInterval(taskId);
          if (ws.readyState === WebSocket.OPEN) {
            ws.close(1001, "Ping failure");
          }
        }
      } else {
        // WebSocket not open, clear interval
        this.clearPingInterval(taskId);
      }
    }, this.pingInterval);
    
    this.pingIntervals.set(taskId, intervalId);
  }
  
  // Clear ping interval
  private clearPingInterval(taskId: string) {
    if (this.pingIntervals.has(taskId)) {
      clearInterval(this.pingIntervals.get(taskId));
      this.pingIntervals.delete(taskId);
    }
  }

  // Send a ping message to the server
  private sendPing(taskId: string): boolean {
    if (!this.connections.has(taskId)) {
      console.warn(`[WebSocketService] Cannot send ping, no connection for task ${taskId}`);
      return false;
    }
    
    const ws = this.connections.get(taskId);
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.warn(`[WebSocketService] Cannot send ping, WebSocket not open for task ${taskId}. State: ${ws ? this.getReadyStateText(ws.readyState) : 'undefined'}`);
      return false;
    }
    
    try {
      ws.send(JSON.stringify({ 
        type: 'ping', 
        timestamp: Date.now(),
        task_id: taskId // Include task_id in ping
      }));
      console.log(`[WebSocketService] Sent manual ping to server for task ${taskId}`);
      return true;
    } catch (error) {
      console.error(`[WebSocketService] Error sending manual ping for task ${taskId}:`, error);
      return false;
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
    
    // Schedule reconnect with exponential backoff
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
            
            // Schedule another reconnect attempt if we're not at the limit
            if (attempts + 1 < this.maxReconnectAttempts) {
              // Manually trigger reconnect without waiting
              setTimeout(() => {
                this.attemptReconnect(taskId, callback, connectionStatusCallback);
              }, 100);
            } else {
              // If this is the last attempt, notify the callback about permanent failure
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
    
    // Clear heartbeat checker
    this.clearHeartbeatChecker(taskId);
    
    // Close and remove connection
    if (this.connections.has(taskId)) {
      const ws = this.connections.get(taskId);
      try {
        if (ws) {
          // Force close regardless of state to ensure cleanup
          try {
            ws.close(1000, "Client unsubscribed");
          } catch (closeError) {
            console.error(`[WebSocketService] Error closing WebSocket for task ${taskId}:`, closeError);
          }
          
          // Set onclose handler to null to prevent reconnection attempts during cleanup
          ws.onclose = null;
          ws.onerror = null;
        }
      } catch (error) {
        console.error(`[WebSocketService] Error cleaning up WebSocket for task ${taskId}:`, error);
      }
      this.connections.delete(taskId);
    }
    
    // Clean up other state
    this.reconnectAttempts.delete(taskId);
    this.connectionState.delete(taskId);
    this.lastHeartbeatReceived.delete(taskId);
    
    console.log(`[WebSocketService] Unsubscribed and cleaned up resources for task ${taskId}`);
  }

  disconnect(): void {
    console.log('[WebSocketService] Disconnecting all WebSockets');
    
    // Close all connections
    this.connections.forEach((ws, _) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.close(1000, "Client disconnected");
      }
    });
    
    // Clear all maps
    this.connections.clear();
    this.callbacks.clear();
    this.connectionStatusCallbacks.clear();
    
    // Clear all timeouts and intervals
    this.reconnectTimeouts.forEach(timeout => clearTimeout(timeout));
    this.reconnectTimeouts.clear();
    
    this.pingIntervals.forEach(interval => clearInterval(interval));
    this.pingIntervals.clear();
    
    this.heartbeatCheckIntervals.forEach(interval => clearInterval(interval));
    this.heartbeatCheckIntervals.clear();
    
    this.reconnectAttempts.clear();
    this.connectionState.clear();
    this.lastHeartbeatReceived.clear();
  }

  getConnectionState(taskId: string): 'connecting' | 'connected' | 'disconnected' {
    return this.connectionState.get(taskId) || 'disconnected';
  }
  
  // Force a reconnection attempt for a specific task
  reconnect(taskId: string): Promise<void> {
    console.log(`[WebSocketService] Manually reconnecting WebSocket for task ${taskId}`);
    
    // Get the existing callback and status callback
    const callback = this.callbacks.get(taskId);
    const statusCallback = this.connectionStatusCallbacks.get(taskId);
    
    if (!callback) {
      return Promise.reject(new Error(`No callback registered for task ${taskId}`));
    }
    
    // Close existing connection if any
    if (this.connections.has(taskId)) {
      const ws = this.connections.get(taskId);
      try {
        if (ws && ws.readyState !== WebSocket.CLOSED) {
          // Use code 1000 (Normal Closure) and reason for normal close
          ws.close(1000, "Manual reconnect");
        }
      } catch (err) {
        console.error(`[WebSocketService] Error closing existing connection for task ${taskId}:`, err);
      }
      this.connections.delete(taskId);
    }
    
    // Clear any existing ping interval
    this.clearPingInterval(taskId);
    
    // Clear heartbeat checker
    this.clearHeartbeatChecker(taskId);
    
    // Reset reconnect attempts for manual reconnect
    this.reconnectAttempts.set(taskId, 0);
    
    // Clear any existing reconnect timeout
    if (this.reconnectTimeouts.has(taskId)) {
      clearTimeout(this.reconnectTimeouts.get(taskId));
      this.reconnectTimeouts.delete(taskId);
    }
    
    // Reset connection state to connecting
    this.connectionState.set(taskId, 'connecting');
    
    // Notify status callback if available
    if (statusCallback) {
      statusCallback('connecting');
    }
    
    // Resubscribe
    return this.subscribeToTask(taskId, callback, statusCallback);
  }
  
  // Diagnostic method to help debug WebSocket issues
  async diagnoseConnection(taskId: string): Promise<Record<string, any>> {
    console.log(`[WebSocketService] Running connection diagnostics for task ${taskId}`);
    
    const diagnostics: Record<string, any> = {
      timestamp: new Date().toISOString(),
      taskId,
      connectionExists: this.connections.has(taskId),
      callbackExists: this.callbacks.has(taskId),
      connectionState: this.getConnectionState(taskId),
      reconnectAttempts: this.reconnectAttempts.get(taskId) || 0,
      baseUrl: this.baseUrl,
      fullUrl: `${this.baseUrl}/${taskId}/ws`,
      browserSupportsWebSocket: typeof WebSocket !== 'undefined',
      networkOnline: navigator.onLine,
      lastHeartbeatReceived: this.lastHeartbeatReceived.get(taskId),
      timeSinceLastHeartbeat: this.lastHeartbeatReceived.get(taskId) 
        ? Date.now() - this.lastHeartbeatReceived.get(taskId)! 
        : null
    };
    
    // Add more detailed logging to help diagnose issues
    console.log(`[WebSocketService] Connection diagnostics report:`);
    console.log(`  - Connection state tracked by frontend: ${diagnostics.connectionState}`);
    console.log(`  - Connection object exists: ${diagnostics.connectionExists}`);
    console.log(`  - Time since last heartbeat: ${diagnostics.timeSinceLastHeartbeat}ms`);
    console.log(`  - Network online: ${diagnostics.networkOnline}`);
    
    // Check existing connection if any
    if (this.connections.has(taskId)) {
      const ws = this.connections.get(taskId);
      diagnostics.webSocketReadyState = ws?.readyState;
      diagnostics.webSocketReadyStateText = this.getReadyStateText(ws?.readyState);
      console.log(`  - WebSocket ready state: ${diagnostics.webSocketReadyStateText}`);
    }
    
    // Test new connection without attaching it
    try {
      console.log(`[WebSocketService] Testing new WebSocket connection to ${this.baseUrl}/${taskId}/ws`);
      const testWs = new WebSocket(`${this.baseUrl}/${taskId}/ws`);
      
      // Set up promise to wait for open or error
      const connectionTestResult = await new Promise<{success: boolean, details: string, error?: string}>((resolve) => {
        // Set timeout for connection test
        const timeout = setTimeout(() => {
          testWs.close();
          resolve({ success: false, details: 'Connection test timed out after 5 seconds' });
        }, 5000);
        
        testWs.onopen = () => {
          clearTimeout(timeout);
          testWs.close(1000, 'Diagnostic test complete');
          resolve({ success: true, details: 'New connection test successful' });
        };
        
        testWs.onerror = (error) => {
          clearTimeout(timeout);
          resolve({ 
            success: false, 
            details: 'Error establishing test connection', 
            error: String(error)
          });
        };
      });
      
      diagnostics.connectionTestResult = connectionTestResult;
      console.log(`  - Test connection result: ${connectionTestResult.success ? 'Success' : 'Failed'}`);
      console.log(`  - Test details: ${connectionTestResult.details}`);
    } catch (error) {
      diagnostics.connectionTestResult = {
        success: false,
        details: 'Exception while testing connection',
        error: String(error)
      };
      console.log(`  - Test connection result: Failed (exception)`);
      console.log(`  - Test error: ${String(error)}`);
    }
    
    // If tests show potential problems, log more detailed info
    if (!diagnostics.connectionExists || 
        (diagnostics.webSocketReadyState !== WebSocket.OPEN) || 
        !diagnostics.connectionTestResult?.success) {
      console.warn('[WebSocketService] Connection diagnostics detected possible issues:');
      console.warn(JSON.stringify(diagnostics, null, 2));
    }
    
    return diagnostics;
  }
  
  private getReadyStateText(readyState?: number): string {
    if (readyState === undefined) return 'undefined';
    
    switch (readyState) {
      case WebSocket.CONNECTING: return 'CONNECTING (0)';
      case WebSocket.OPEN: return 'OPEN (1)';
      case WebSocket.CLOSING: return 'CLOSING (2)';
      case WebSocket.CLOSED: return 'CLOSED (3)';
      default: return `UNKNOWN (${readyState})`;
    }
  }
}

export default new WebSocketService(); 