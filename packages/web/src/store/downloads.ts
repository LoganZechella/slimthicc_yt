import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit'
import { websocketService } from '../services/websocket'

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

async function makeRequest(url: string, options: RequestInit = {}) {
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    })

    const data = await response.json().catch(() => ({}))
    
    if (!response.ok) {
      throw new Error(data.detail || `Request failed with status ${response.status}`)
    }

    return data
  } catch (error) {
    if (error instanceof Error) {
      throw error
    }
    throw new Error('An unexpected error occurred')
  }
}

export const startDownload = createAsyncThunk(
  'downloads/startDownload',
  async (request: { url: string; format?: DownloadFormat; quality?: AudioQuality }, { dispatch }) => {
    try {
      const validUrl = ensureValidUrl(request.url)
      
      const data = await makeRequest('/api/v1/downloads/', {
        method: 'POST',
        body: JSON.stringify({
          url: validUrl,
          format: request.format || 'mp3',
          quality: request.quality || 'HIGH'
        })
      })
      
      const taskId = data.task_id as string

      // Create initial task state
      dispatch(taskCreated({
        id: taskId,
        url: validUrl,
        status: 'queued',
        progress: 0,
        format: request.format || 'mp3',
        quality: request.quality || 'HIGH',
        createdAt: new Date().toISOString(),
        updatedAt: new Date().toISOString()
      }))

      // Subscribe to WebSocket updates
      try {
        await websocketService.subscribeToTask(taskId, (progress: number, status: string) => {
          if (isValidTaskStatus(status)) {
            dispatch(taskUpdated({
              id: taskId,
              progress,
              status,
              updatedAt: new Date().toISOString()
            }))
          }
        })
      } catch (error) {
        console.error('Failed to subscribe to WebSocket updates:', error)
      }

      // Get initial task status
      try {
        await dispatch(getTaskStatus(taskId))
      } catch (error) {
        console.error('Failed to get initial task status:', error)
      }

      return taskId
    } catch (error) {
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
    return await makeRequest(`/api/v1/downloads/${taskId}`) as DownloadTask
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