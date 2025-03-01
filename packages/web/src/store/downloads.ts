import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import websocketService from '../services/websocket'
import { ENDPOINTS, makeRequest, logApiCall } from '../services/api'

export type AudioQuality = 'HIGH' | 'MEDIUM' | 'LOW'
export type DownloadFormat = 'mp3' | 'm4a'

export interface DownloadTask {
  id: string
  url: string
  title?: string
  author?: string
  status: 'queued' | 'downloading' | 'processing' | 'complete' | 'error'
  progress: number
  format: DownloadFormat
  quality: AudioQuality
  createdAt: string
  updatedAt: string
  error?: string
  output_path?: string
  connectionStatus?: 'connecting' | 'connected' | 'disconnected'
}

export interface DownloadsState {
  tasks: Record<string, DownloadTask>
  activeTaskId: string | null
  loading: boolean
  error: string | null
}

const initialState: DownloadsState = {
  tasks: {},
  activeTaskId: null,
  loading: false,
  error: null
}

function ensureValidUrl(url: string): string {
  // Remove any leading/trailing whitespace
  url = url.trim()

  // If URL already has a protocol, return as is
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }

  // Check if it's a Spotify or YouTube URL
  if (url.includes('spotify.com') || url.includes('youtu.be') || url.includes('youtube.com')) {
    return `https://${url}`
  }

  throw new Error('Invalid URL. Please enter a valid Spotify or YouTube URL.')
}

export const startDownload = createAsyncThunk(
  'downloads/startDownload',
  async (request: { url: string; format?: DownloadFormat; quality?: AudioQuality }, { dispatch, getState }) => {
    try {
      // Clean up existing WebSocket connections to prevent resource leaks
      const state = getState() as { downloads: DownloadsState };
      const existingTasks = state.downloads.tasks;
      
      // Unsubscribe from all completed or errored tasks
      Object.values(existingTasks).forEach(task => {
        if (task.status === 'complete' || task.status === 'error') {
          console.log(`Cleaning up WebSocket connection for completed task ${task.id}`);
          websocketService.unsubscribeFromTask(task.id);
        }
      });

      console.log('Starting download with request:', request);
      const validUrl = ensureValidUrl(request.url)
      console.log('Validated URL:', validUrl);
      
      // Construct the data payload
      const payload = {
        url: validUrl,
        format: request.format || 'mp3',
        quality: request.quality || 'HIGH'
      };
      
      // Log the API call
      logApiCall(ENDPOINTS.DOWNLOADS, 'POST', payload);
      
      let data;
      try {
        // Use makeRequest function from API service 
        data = await makeRequest(ENDPOINTS.DOWNLOADS, {
          method: 'POST',
          body: JSON.stringify(payload)
        });
        console.log('API response data:', data);
      } catch (error) {
        console.error('API request failed:', error);
        // If we're in a production environment, try the relative URL path directly as fallback
        if (import.meta.env.PROD) {
          console.log('Attempting fallback to relative URL');
          try {
            // Try with relative URL as fallback
            data = await makeRequest('/api/v1/downloads', {
              method: 'POST',
              body: JSON.stringify(payload)
            });
            console.log('Fallback successful, API response data:', data);
          } catch (fallbackError) {
            console.error('Fallback API request also failed:', fallbackError);
            throw fallbackError;
          }
        } else {
          throw error;
        }
      }
      
      // Validate required fields
      if (!data) {
        console.error('Invalid response data:', data);
        throw new Error('Server returned invalid response: empty data');
      }
      
      // Use either task_id or id field (task_id is for legacy compatibility)
      let taskId = data.task_id || data.id;
      
      // If neither id nor task_id is present, try to get it from the URL
      if (!taskId && data.url) {
        // Try to extract ID from the URL for Spotify or YouTube
        const urlObj = new URL(data.url);
        const pathParts = urlObj.pathname.split('/');
        if (pathParts.length > 2) {
          taskId = pathParts[pathParts.length - 1];
          console.log('Extracted task ID from URL:', taskId);
        }
      }
      
      // Last resort: generate a random ID
      if (!taskId) {
        taskId = 'task_' + Math.random().toString(36).substring(2, 15);
        console.warn('Generated random task ID as none was provided:', taskId);
      }
      
      console.log('Using task ID:', taskId);

      // Create initial task state with title from response if available
      dispatch(taskCreated({
        id: taskId,
        url: validUrl,
        title: data.title || undefined,
        author: data.artists || data.author || undefined,
        status: 'queued',
        progress: 0,
        format: request.format || 'mp3',
        quality: request.quality || 'HIGH',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString(),
        connectionStatus: 'connecting'
      }));

      // Subscribe to WebSocket updates
      try {
        console.log('Attempting to connect to WebSocket for task:', taskId);
        
        // Create connection status callback
        const connectionStatusCallback = (status: 'connecting' | 'connected' | 'disconnected') => {
          console.log(`WebSocket connection status for task ${taskId}: ${status}`);
          dispatch(taskUpdated({
            id: taskId,
            connectionStatus: status,
            updatedAt: new Date().toISOString()
          }));
          
          // If disconnected, update task status to indicate connection issues
          if (status === 'disconnected') {
            // Only update if it's not already complete or error
            const currentTask = dispatch(getTaskStatus(taskId)) as any;
            if (currentTask && !['complete', 'error'].includes(currentTask.status)) {
              dispatch(taskUpdated({
                id: taskId,
                status: 'queued',
                error: 'Lost connection to server. Reconnecting automatically...',
                updatedAt: new Date().toISOString()
              }));
              
              // After disconnection, try to get a new status update after a short delay
              // This helps recover when a connection drops but the task might still be progressing on the server
              setTimeout(async () => {
                try {
                  console.log(`Requesting updated status for task ${taskId} after disconnection`);
                  await dispatch(getTaskStatus(taskId));
                } catch (statusError) {
                  console.error(`Failed to get updated status for task ${taskId} after disconnection:`, statusError);
                }
              }, 3000); // Wait 3 seconds before trying
            }
          } else if (status === 'connected') {
            // When connection is established, clear any error messages about connection issues
            const currentTask = dispatch(getTaskStatus(taskId)) as any;
            if (currentTask && currentTask.error && currentTask.error.includes('connection')) {
              dispatch(taskUpdated({
                id: taskId,
                error: undefined, // Clear connection-related errors
                updatedAt: new Date().toISOString()
              }));
            }
          }
        };
        
        await websocketService.subscribeToTask(taskId, (data: any) => {
          // Skip non-status update messages
          if (data.type === 'ping' || data.type === 'pong' || data.type === 'connection_status') {
            return;
          }
          
          console.log(`WebSocket update for task ${taskId}:`, data);
          
          // Extract fields from the data object
          const { progress, status, error, details } = data;
          
          // Construct an update with only the fields that are present
          const update: Partial<DownloadTask> & { id: string } = { id: taskId };
          
          if (progress !== undefined) {
            update.progress = progress;
          }
          
          if (status && isValidTaskStatus(status)) {
            update.status = status;
            
            // Clean up WebSocket when download is completed or errored
            if (status === 'complete' || status === 'error') {
              console.log(`Download task ${taskId} is now ${status}, scheduling WebSocket cleanup`);
              // Schedule cleanup after a short delay to ensure all final messages are received
              setTimeout(() => {
                console.log(`Performing delayed cleanup for completed task ${taskId}`);
                websocketService.unsubscribeFromTask(taskId);
              }, 3000); // 3 second delay
            }
          }
          
          if (error) {
            update.error = error;
          }
          
          if (details?.title) {
            update.title = details.title;
          }
          
          if (details?.author) {
            update.author = details.author;
          }
          
          if (details?.output_path) {
            update.output_path = details.output_path;
          }
          
          // Only dispatch if we have updates
          if (Object.keys(update).length > 1) { // More than just the ID
            update.updatedAt = new Date().toISOString();
            dispatch(taskUpdated(update));
          }
        }, connectionStatusCallback);
        
        console.log('WebSocket subscription successful for task:', taskId);
      } catch (error) {
        console.error(`Failed to subscribe to WebSocket updates for task ${taskId}:`, error);
        dispatch(taskUpdated({
          id: taskId,
          connectionStatus: 'disconnected',
          error: 'Failed to establish WebSocket connection for updates. Please refresh the page.',
          updatedAt: new Date().toISOString()
        }));
      }

      // Get initial task status
      try {
        console.log('Getting initial task status for:', taskId);
        await dispatch(getTaskStatus(taskId))
      } catch (error) {
        console.error('Failed to get initial task status:', error)
      }

      return { taskId, url: validUrl };
    } catch (error) {
      console.error('Error in startDownload thunk:', error);
      if (error instanceof Error) {
        throw error
      }
      throw new Error('An unexpected error occurred')
    }
  }
)

export const getTaskStatus = createAsyncThunk(
  'downloads/getTaskStatus',
  async (taskId: string) => {
    logApiCall(ENDPOINTS.DOWNLOAD(taskId), 'GET');
    return await makeRequest(ENDPOINTS.DOWNLOAD(taskId)) as DownloadTask
  }
)

// Type guard for task status
function isValidTaskStatus(status: string): status is DownloadTask['status'] {
  return ['queued', 'downloading', 'processing', 'complete', 'error'].includes(status)
}

const downloadsSlice = createSlice({
  name: 'downloads',
  initialState,
  reducers: {
    taskCreated: (state, action: PayloadAction<DownloadTask>) => {
      const task = action.payload
      state.tasks[task.id] = task
      state.activeTaskId = task.id
    },
    taskUpdated: (state, action: PayloadAction<Partial<DownloadTask> & { id: string }>) => {
      const { id, ...updates } = action.payload
      // Only update if the task exists to prevent React error #185
      if (state.tasks[id]) {
        state.tasks[id] = {
          ...state.tasks[id],
          ...updates
        }
      } else {
        console.warn(`Attempted to update non-existent task with ID: ${id}`)
      }
    },
    taskRemoved: (state, action: PayloadAction<string>) => {
      const taskId = action.payload
      delete state.tasks[taskId]
      if (state.activeTaskId === taskId) {
        state.activeTaskId = null
      }
    }
  },
  extraReducers: (builder) => {
    builder
      .addCase(startDownload.pending, (state) => {
        state.loading = true
        state.error = null
      })
      .addCase(startDownload.fulfilled, (state, action) => {
        state.loading = false
        state.activeTaskId = action.payload.taskId
      })
      .addCase(startDownload.rejected, (state, action) => {
        state.loading = false
        state.error = action.error.message || 'Failed to start download'
      })
      .addCase(getTaskStatus.fulfilled, (state, action) => {
        const task = action.payload
        state.tasks[task.id] = task
      })
  }
})

export const { taskCreated, taskUpdated, taskRemoved } = downloadsSlice.actions
export default downloadsSlice.reducer 