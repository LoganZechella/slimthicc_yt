import { WS_URL } from './api';

export class WebSocketService {
  private connections: Map<string, WebSocket> = new Map()
  private callbacks: Map<string, Function> = new Map()
  private baseUrl: string

  constructor() {
    // Use the exported WS_URL from the API service
    this.baseUrl = `${WS_URL}/downloads`;
    
    console.log('WebSocket service initialized with base URL:', this.baseUrl);
  }

  subscribeToTask(taskId: string, callback: Function): Promise<void> {
    // If already subscribed, just update the callback
    if (this.callbacks.has(taskId)) {
      console.log(`Updating existing callback for task ${taskId}`)
      this.callbacks.set(taskId, callback)
      return Promise.resolve()
    }

    const wsUrl = `${this.baseUrl}/${taskId}/ws`
    console.log(`Connecting to WebSocket: ${wsUrl}`)

    // Store the callback
    this.callbacks.set(taskId, callback)

    // Create a new WebSocket connection
    return new Promise((resolve, reject) => {
      try {
        const ws = new WebSocket(wsUrl)
        
        ws.onopen = () => {
          console.log(`WebSocket connection opened for task ${taskId}`)
          this.connections.set(taskId, ws)
          resolve()
        }
        
        ws.onmessage = (event) => {
          console.log(`WebSocket message received for task ${taskId}:`, event.data)
          try {
            const data = JSON.parse(event.data)
            const { progress, status, error, details } = data
            
            // Log the data for debugging
            console.log(`Task ${taskId} update:`, { progress, status, error, details })
            
            // Special handling for complete status
            if (status === 'complete') {
              console.log(`Task ${taskId} is complete!`, data)
              // Force progress to 100% on completion
              const callback = this.callbacks.get(taskId)
              if (callback) {
                callback(100, status, error, details)
              }
            } else {
              // Call the callback with the update
              const callback = this.callbacks.get(taskId)
              if (callback) {
                callback(progress, status, error, details)
              }
            }
          } catch (err) {
            console.error(`Error processing WebSocket message for task ${taskId}:`, err, event.data)
          }
        }
        
        ws.onerror = (error) => {
          console.error(`WebSocket error for task ${taskId}:`, error)
          // Do not reject here, try to handle errors gracefully
        }
        
        ws.onclose = (event) => {
          console.log(`WebSocket connection closed for task ${taskId}:`, event.code, event.reason)
          
          // If connection was closed abnormally and we still care about this task
          if (event.code !== 1000 && this.callbacks.has(taskId)) {
            console.log(`Attempting to reconnect WebSocket for task ${taskId}`)
            // Try to reconnect after a short delay
            setTimeout(() => {
              this.subscribeToTask(taskId, this.callbacks.get(taskId) as Function)
                .catch(err => console.error(`Failed to reconnect WebSocket for task ${taskId}:`, err))
            }, 2000)
          } else {
            // Clean up if closed normally
            this.connections.delete(taskId)
          }
        }
      } catch (error) {
        console.error(`Error creating WebSocket for task ${taskId}:`, error)
        reject(error)
      }
    })
  }

  unsubscribeFromTask(taskId: string): void {
    const ws = this.connections.get(taskId)
    if (ws) {
      // Send an unsubscribe message if the connection is open
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'unsubscribe' }))
      }
      
      // Close the connection
      ws.close()
      
      // Remove from maps
      this.connections.delete(taskId)
      this.callbacks.delete(taskId)
      
      console.log(`Unsubscribed from task ${taskId}`)
    }
  }

  disconnect(): void {
    // Close all connections
    this.connections.forEach((ws, taskId) => {
      ws.close()
      console.log(`Closed WebSocket for task ${taskId}`)
    })
    
    // Clear maps
    this.connections.clear()
    this.callbacks.clear()
    
    console.log('Disconnected all WebSocket connections')
  }
}

export const websocketService = new WebSocketService() 