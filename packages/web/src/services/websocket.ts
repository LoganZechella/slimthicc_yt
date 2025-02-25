export class WebSocketService {
  private connections: Map<string, WebSocket> = new Map()
  private callbacks: Map<string, (progress: number, status: string, error?: string, details?: any) => void> = new Map()
  private maxReconnectAttempts = 5
  private reconnectDelay = 1000 // 1 second

  constructor() {
    // No need for baseUrl as we'll use relative paths with Vite proxy
  }

  private getWebSocketUrl(taskId: string): string {
    // Get the current protocol (http or https)
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    // Get the host (hostname:port)
    const host = window.location.host;
    // Construct the WebSocket URL
    return `${protocol}//${host}/api/v1/downloads/${taskId}/ws`;
  }

  async subscribeToTask(taskId: string, callback: (progress: number, status: string, error?: string, details?: any) => void) {
    try {
      console.log(`Connecting to WebSocket: ${this.getWebSocketUrl(taskId)}`)
      const socket = new WebSocket(this.getWebSocketUrl(taskId))
      let reconnectAttempts = 0

      socket.onopen = () => {
        console.log('WebSocket connected successfully')
        this.connections.set(taskId, socket)
        this.callbacks.set(taskId, callback)
      }

      socket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'progress') {
            // Extract additional details if available
            const details = {
              strategy: data.strategy,
              statusMessage: data.statusMessage,
              fileInfo: data.fileInfo,
              ...data.details
            };
            
            // Call the callback with all available information
            callback(data.progress, data.status, data.error, details)
            
            // Log detailed information for debugging
            console.log(`Task ${taskId} update:`, {
              progress: data.progress,
              status: data.status,
              details
            });
          }
        } catch (error) {
          console.error('Error processing WebSocket message:', error)
        }
      }

      socket.onerror = (error) => {
        console.error('WebSocket error:', error)
        if (reconnectAttempts < this.maxReconnectAttempts) {
          reconnectAttempts++
          console.log(`Attempting to reconnect (${reconnectAttempts}/${this.maxReconnectAttempts})...`)
          setTimeout(() => {
            this.subscribeToTask(taskId, callback)
          }, this.reconnectDelay * reconnectAttempts)
        } else {
          console.error('Max reconnection attempts reached')
          callback(0, 'error', 'Connection failed after multiple attempts')
        }
      }

      socket.onclose = () => {
        console.log('WebSocket connection closed')
        this.connections.delete(taskId)
        this.callbacks.delete(taskId)
      }

    } catch (error) {
      console.error('Failed to subscribe to task:', error)
      throw error
    }
  }

  unsubscribeFromTask(taskId: string): void {
    try {
      if (this.connections.has(taskId)) {
        const socket = this.connections.get(taskId)
        if (socket && socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: 'unsubscribe', taskId }))
        }
        this.connections.delete(taskId)
        this.callbacks.delete(taskId)
      }
    } catch (error) {
      console.error('Error unsubscribing from task:', error)
    }
  }

  disconnect(): void {
    this.connections.clear()
    this.callbacks.clear()
  }
}

// Create a singleton instance
export const websocketService = new WebSocketService() 