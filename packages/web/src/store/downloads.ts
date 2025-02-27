import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import { websocketService } from '../services/websocket'
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
  async (request: { url: string; format?: DownloadFormat; quality?: AudioQuality }, { dispatch }) => {
    try {
      console.log('Starting download with request:', request);
      const validUrl = ensureValidUrl(request.url)
      console.log('Validated URL:', validUrl);
      
      logApiCall(ENDPOINTS.DOWNLOADS, 'POST', { url: validUrl, format: request.format, quality: request.quality });
      
      let data;
      try {
        // Use makeRequest function from API service instead of direct fetch
        data = await makeRequest(ENDPOINTS.DOWNLOADS, {
          method: 'POST',
          body: JSON.stringify({
            url: validUrl,
            format: request.format || 'mp3',
            quality: request.quality || 'HIGH'
          })
        });
        console.log('API response data:', data);
      } catch (error) {
        console.error('API request failed:', error);
        throw error;
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
        updatedAt: new Date().toISOString()
      }));

      // Subscribe to WebSocket updates
      try {
        console.log('Attempting to connect to WebSocket for task:', taskId);
        await websocketService.subscribeToTask(taskId, (progress: number, status: string) => {
          console.log(`WebSocket update for task ${taskId}:`, { progress, status });
          if (isValidTaskStatus(status)) {
            dispatch(taskUpdated({
              id: taskId,
              progress,
              status,
              updatedAt: new Date().toISOString()
            }))
          }
        });
        console.log('WebSocket subscription successful');
      } catch (error) {
        console.error('Failed to subscribe to WebSocket updates:', error)
      }

      // Get initial task status
      try {
        console.log('Getting initial task status for:', taskId);
        await dispatch(getTaskStatus(taskId))
      } catch (error) {
        console.error('Failed to get initial task status:', error)
      }

      return taskId
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
      if (state.tasks[id]) {
        state.tasks[id] = {
          ...state.tasks[id],
          ...updates
        }
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
        state.activeTaskId = action.payload
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