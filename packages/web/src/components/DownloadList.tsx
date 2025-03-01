import React, { useEffect, useState } from 'react'
import styled from 'styled-components'
import { useSelector, useDispatch } from 'react-redux'
import { WebSocketService } from '../services/websocket'
import { RootState } from '../store'
import { taskUpdated, taskRemoved, DownloadTask } from '../store/downloads'

// Create the websocket service singleton
const websocketService = new WebSocketService();

// Define task status types
type DownloadTaskStatus = 'queued' | 'downloading' | 'processing' | 'complete' | 'error';

const isCompletedStatus = (status: DownloadTaskStatus): boolean => {
  return ['complete', 'error'].includes(status);
}

// Styled Components
const DownloadListContainer = styled.div`
  margin-top: 1rem;
  width: 100%;
`

const DownloadItem = styled.div<{ status: DownloadTaskStatus }>`
  border: 1px solid ${props => props.status === 'error' ? '#ff9494' : '#e0e0e0'};
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
  background-color: ${props => {
    if (props.status === 'complete') return '#f0fff0';
    if (props.status === 'error') return '#fff0f0';
    return '#ffffff';
  }};
  transition: all 0.3s ease;
`

const ProgressBar = styled.div<{ progress: number }>`
  height: 8px;
  background-color: #e0e0e0;
  border-radius: 4px;
  margin: 1rem 0;
  position: relative;
  overflow: hidden;

  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    width: ${props => `${props.progress}%`};
    background-color: #4caf50;
    border-radius: 4px;
    transition: width 0.3s ease;
  }
`

const StatusBadge = styled.span<{ status: DownloadTaskStatus }>`
  display: inline-block;
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.8rem;
  margin-left: 0.5rem;
  background-color: ${props => {
    switch (props.status) {
      case 'queued': return '#ffeb3b';
      case 'downloading': return '#2196f3';
      case 'complete': return '#4caf50';
      case 'error': return '#f44336';
      default: return '#e0e0e0';
    }
  }};
  color: ${props => {
    switch (props.status) {
      case 'queued': return '#000000';
      default: return '#ffffff';
    }
  }};
`

const TaskTitle = styled.h3`
  margin: 0;
  font-size: 1.2rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
`

const TaskSubtitle = styled.div`
  color: #666;
  font-size: 0.9rem;
  margin-top: 0.5rem;
`

const ErrorMessage = styled.div`
  color: #f44336;
  margin-top: 0.5rem;
  padding: 0.5rem;
  background-color: #ffebee;
  border-radius: 4px;
  font-size: 0.9rem;
`

const SuccessMessage = styled.div`
  color: #4caf50;
  margin-top: 0.5rem;
  padding: 0.5rem;
  background-color: #e8f5e9;
  border-radius: 4px;
  font-size: 0.9rem;
`

const DownloadButton = styled.button`
  background-color: #4caf50;
  color: white;
  border: none;
  padding: 0.5rem 1rem;
  border-radius: 4px;
  cursor: pointer;
  margin-top: 0.5rem;
  transition: background-color 0.3s ease;

  &:hover {
    background-color: #388e3c;
  }

  &:disabled {
    background-color: #cccccc;
    cursor: not-allowed;
  }
`

const ConnectionStatus = styled.div<{ connected: boolean }>`
  font-size: 0.8rem;
  color: ${props => props.connected ? '#4caf50' : '#f44336'};
  margin-top: 0.25rem;
`

const DownloadList: React.FC = () => {
  const [connectionStates, setConnectionStates] = useState<Record<string, 'connecting' | 'connected' | 'disconnected'>>({})
  const dispatch = useDispatch()
  const tasksRecord = useSelector((state: RootState) => state.downloads.tasks)
  const tasks = Object.values(tasksRecord)
  
  // Track additional task metadata locally
  const [taskMetadata, setTaskMetadata] = useState<Record<string, {
    total_files?: number;
    completed_files?: number;
    total_size?: number;
    downloaded_size?: number;
    description?: string;
  }>>({})
  
  // Cleanup function for completed and errored tasks
  const cleanupTask = (taskId: string, status: DownloadTaskStatus) => {
    // If the task is completed or errored and has been connected, unsubscribe after a delay
    if (isCompletedStatus(status) && connectionStates[taskId]) {
      console.log(`[DownloadList] Task ${taskId} is ${status}, scheduling WebSocket cleanup in 5 seconds`)
      setTimeout(() => {
        console.log(`[DownloadList] Cleaning up WebSocket for completed/errored task ${taskId}`)
        websocketService.unsubscribeFromTask(taskId)
        // Update connection state
        setConnectionStates(prev => ({
          ...prev,
          [taskId]: 'disconnected'
        }))
      }, 5000) // Give it 5 seconds to receive final messages
    }
  }

  // Subscribe to WebSocket updates for all tasks
  useEffect(() => {
    // Subscribe to active tasks
    tasks.forEach((task) => {
      const isAlreadySubscribed = Object.keys(connectionStates).includes(task.id)
      
      // Don't resubscribe if we're already subscribed
      if (isAlreadySubscribed) {
        return;
      }
      
      // Only subscribe to pending or in-progress tasks, not completed/errored ones
      if (!isCompletedStatus(task.status)) {
        console.log(`[DownloadList] Subscribing to WebSocket for task ${task.id}`)
        
        // Keep track of connection state
        setConnectionStates(prev => ({
          ...prev,
          [task.id]: 'connecting'
        }))
        
        // Subscribe to task updates
        websocketService.subscribeToTask(
          task.id,
          (data: any) => {
            console.log(`[DownloadList] Received WebSocket update for task ${task.id}:`, data)
            
            // Extract standard task fields vs metadata
            const { 
              total_files, 
              completed_files, 
              total_size, 
              downloaded_size,
              description,
              ...taskFields 
            } = data;
            
            // Update task state in Redux
            dispatch(taskUpdated({
              id: task.id,
              ...taskFields,
              updatedAt: new Date().toISOString()
            }))
            
            // Store additional metadata locally
            if (total_files || completed_files || total_size || downloaded_size || description) {
              setTaskMetadata(prev => ({
                ...prev,
                [task.id]: {
                  ...prev[task.id],
                  total_files,
                  completed_files,
                  total_size,
                  downloaded_size,
                  description
                }
              }))
            }
            
            // Trigger cleanup if the task is completed or errored
            if (data.status && isCompletedStatus(data.status)) {
              cleanupTask(task.id, data.status);
            }
          },
          (status: 'connecting' | 'connected' | 'disconnected') => {
            console.log(`[DownloadList] WebSocket connection status for task ${task.id}:`, status)
            // Update connection state
            setConnectionStates(prev => ({
              ...prev,
              [task.id]: status
            }))
          }
        )
      } else {
        console.log(`[DownloadList] Not subscribing to completed/errored task ${task.id}`)
      }
    })
    
    // Cleanup when component unmounts
    return () => {
      console.log('[DownloadList] Cleaning up WebSocket connections')
      tasks.forEach((task) => {
        console.log(`[DownloadList] Unsubscribing from task ${task.id} during cleanup`)
        websocketService.unsubscribeFromTask(task.id)
      })
    }
  }, [tasks.map(task => task.id).join(',')]) // Only re-run when task IDs change
  
  // Format bytes to human readable format
  const formatBytes = (bytes: number, decimals = 2) => {
    if (bytes === 0) return '0 Bytes'
    const k = 1024
    const dm = decimals < 0 ? 0 : decimals
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i]
  }

  // Handle download button click
  const handleDownload = (task: DownloadTask) => {
    if (task.status === 'complete') {
      // Create a URL for the file
      const url = `/api/v1/downloads/${task.id}/file`
      
      // Create an anchor element and trigger download
      const a = document.createElement('a')
      a.href = url
      a.download = task.title || 'download'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
    }
  }

  // Reset all tasks
  const handleResetAll = () => {
    // Unsubscribe from all tasks first
    tasks.forEach((task) => {
      console.log(`[DownloadList] Unsubscribing from task ${task.id} during reset`)
      websocketService.unsubscribeFromTask(task.id)
      // Remove task from Redux
      dispatch(taskRemoved(task.id))
    })
    
    // Reset connection states
    setConnectionStates({})
    // Reset metadata
    setTaskMetadata({})
  }

  return (
    <DownloadListContainer>
      {tasks.length > 0 && (
        <div style={{ marginBottom: '1rem', textAlign: 'right' }}>
          <button 
            onClick={handleResetAll}
            style={{ 
              backgroundColor: '#f44336',
              color: 'white',
              border: 'none',
              padding: '0.5rem 1rem',
              borderRadius: '4px',
              cursor: 'pointer'
            }}
          >
            Clear All
          </button>
        </div>
      )}
      
      {tasks.map((task) => {
        // Get the metadata for this task
        const metadata = taskMetadata[task.id] || {};
        
        return (
          <DownloadItem key={task.id} status={task.status as DownloadTaskStatus}>
            <TaskTitle>
              {task.title || 'Download'} 
              <StatusBadge status={task.status as DownloadTaskStatus}>
                {task.status.replace('_', ' ')}
              </StatusBadge>
            </TaskTitle>
            
            <TaskSubtitle>
              {metadata.description || task.url}
              <ConnectionStatus connected={connectionStates[task.id] === 'connected'}>
                WebSocket: {connectionStates[task.id] || 'disconnected'}
              </ConnectionStatus>
            </TaskSubtitle>
            
            {task.status === 'downloading' && (
              <ProgressBar progress={task.progress || 0} />
            )}
            
            {metadata.total_files && metadata.total_files > 0 && (
              <div>
                Files: {metadata.completed_files || 0} / {metadata.total_files}
              </div>
            )}
            
            {metadata.total_size && metadata.total_size > 0 && (
              <div>
                Size: {formatBytes(metadata.downloaded_size || 0)} / {formatBytes(metadata.total_size)}
              </div>
            )}
            
            {task.error && (
              <ErrorMessage>
                {task.error}
              </ErrorMessage>
            )}
            
            {task.status === 'complete' && (
              <SuccessMessage>
                Download completed successfully! Click the button below to download the file.
                <div>
                  <DownloadButton onClick={() => handleDownload(task)}>
                    Download File
                  </DownloadButton>
                </div>
              </SuccessMessage>
            )}
          </DownloadItem>
        );
      })}
    </DownloadListContainer>
  )
}

export { DownloadList } 