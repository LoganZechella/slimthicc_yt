import React, { useEffect } from 'react'
import styled from 'styled-components'
import { useSelector, useDispatch } from 'react-redux'
import { RootState } from '../store'
import { taskUpdated, DownloadTask } from '../store/downloads'
import { websocketService } from '../services/websocket'

const DownloadListContainer = styled.div`
  margin-top: 2rem;
  width: 100%;
  max-width: 800px;
`

const DownloadItem = styled.div`
  background: ${props => props.theme.colors.surface};
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 1rem;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
`

const ProgressBar = styled.div<{ $progress: number }>`
  width: 100%;
  height: 4px;
  background: ${props => props.theme.colors.background};
  border-radius: 2px;
  margin: 0.5rem 0;
  overflow: hidden;

  &::after {
    content: '';
    display: block;
    width: ${props => props.$progress}%;
    height: 100%;
    background: ${props => {
      if (props.$progress === 100) return props.theme.colors.success;
      return props.theme.colors.primary;
    }};
    transition: width 0.3s ease;
  }
`

type TaskStatus = 'queued' | 'downloading' | 'processing' | 'complete' | 'error';

const StatusBadge = styled.span<{ $status: TaskStatus }>`
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.875rem;
  background: ${props => {
    switch (props.$status) {
      case 'complete':
        return props.theme.colors.success;
      case 'error':
        return props.theme.colors.error;
      case 'downloading':
        return props.theme.colors.primary;
      case 'processing':
        return props.theme.colors.warning;
      default:
        return props.theme.colors.background;
    }
  }};
  color: white;
`

const TaskTitle = styled.h3`
  margin: 0 0 0.5rem 0;
  font-size: 1rem;
  color: ${props => props.theme.colors.text};
`

const TaskSubtitle = styled.div`
  font-size: 0.875rem;
  color: ${props => props.theme.colors.textSecondary};
  margin-bottom: 0.5rem;
`

const ErrorMessage = styled.div`
  color: ${props => props.theme.colors.error};
  margin-top: 0.5rem;
  font-size: 0.875rem;
  padding: 0.5rem;
  background: ${props => props.theme.colors.errorBg};
  border-radius: 4px;
`

const DownloadButton = styled.button`
  background: ${props => props.theme.colors.success};
  color: white;
  border: none;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: opacity 0.2s;

  &:hover {
    opacity: 0.9;
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`

const TaskActions = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 0.5rem;
`

const DetailPanel = styled.div`
  margin-top: 0.75rem;
  padding: 0.75rem;
  background: ${props => props.theme.colors.backgroundAlt};
  border-radius: 4px;
  font-size: 0.875rem;
  color: ${props => props.theme.colors.textSecondary};
`

const DetailItem = styled.div`
  margin-bottom: 0.5rem;
  display: flex;
  align-items: flex-start;
  
  &:last-child {
    margin-bottom: 0;
  }
`

const DetailLabel = styled.span`
  font-weight: 500;
  margin-right: 0.5rem;
  min-width: 100px;
`

const DetailValue = styled.span`
  word-break: break-word;
`

const ExpandButton = styled.button`
  background: none;
  border: none;
  color: ${props => props.theme.colors.primary};
  font-size: 0.875rem;
  cursor: pointer;
  padding: 0.25rem 0.5rem;
  margin-top: 0.5rem;
  text-decoration: underline;
  
  &:hover {
    opacity: 0.8;
  }
`

const StatusMessage = styled.div`
  font-size: 0.875rem;
  color: ${props => props.theme.colors.textSecondary};
  margin-top: 0.5rem;
`

interface TaskDetails {
  strategy?: string;
  statusMessage?: string;
  fileInfo?: {
    size?: number;
    path?: string;
    type?: string;
  };
  [key: string]: any;
}

export const DownloadList: React.FC = () => {
  const dispatch = useDispatch()
  const tasks = useSelector((state: RootState) => state.downloads.tasks) as Record<string, DownloadTask>
  const [expandedTasks, setExpandedTasks] = React.useState<Record<string, boolean>>({})
  const [taskDetails, setTaskDetails] = React.useState<Record<string, TaskDetails>>({})

  useEffect(() => {
    // Subscribe to WebSocket updates for each task
    Object.keys(tasks).forEach(taskId => {
      websocketService.subscribeToTask(taskId, (progress: number, status: string, error?: string, details?: any) => {
        const task = tasks[taskId]
        if (task && isValidTaskStatus(status)) {
          // Update task in Redux store
          dispatch(taskUpdated({
            ...task,
            progress,
            status,
            error,
            updatedAt: new Date().toISOString()
          }))
          
          // Store additional details locally
          if (details) {
            setTaskDetails(prev => ({
              ...prev,
              [taskId]: {
                ...prev[taskId],
                ...details
              }
            }))
          }
        }
      })
    })

    // Cleanup subscriptions
    return () => {
      Object.keys(tasks).forEach(taskId => {
        websocketService.unsubscribeFromTask(taskId)
      })
    }
  }, [tasks, dispatch])

  // Type guard for TaskStatus
  const isValidTaskStatus = (status: string): status is TaskStatus => {
    return ['queued', 'downloading', 'processing', 'complete', 'error'].includes(status)
  }

  const handleDownload = async (taskId: string) => {
    try {
      const response = await fetch(`/api/v1/downloads/${taskId}/file`)
      if (!response.ok) {
        const errorText = await response.text()
        throw new Error(`Download failed: ${errorText}`)
      }
      
      // Get the filename from the Content-Disposition header if available
      const contentDisposition = response.headers.get('Content-Disposition')
      let filename = 'download'
      if (contentDisposition) {
        const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition)
        if (matches != null && matches[1]) {
          filename = matches[1].replace(/['"]/g, '')
        }
      }
      
      // Create a blob from the response and trigger download
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)
    } catch (error) {
      console.error('Error downloading file:', error)
      // Show error message to the user
      dispatch(taskUpdated({
        id: taskId,
        error: error instanceof Error ? error.message : 'Failed to download file',
        status: 'error'
      }))
    }
  }

  const toggleTaskExpanded = (taskId: string) => {
    setExpandedTasks(prev => ({
      ...prev,
      [taskId]: !prev[taskId]
    }))
  }

  const getStatusDetails = (task: DownloadTask, details?: TaskDetails) => {
    // If we have a specific status message from the server, use it
    if (details?.statusMessage) {
      return details.statusMessage;
    }
    
    // Otherwise, use default messages based on status
    switch (task.status) {
      case 'downloading':
        return `Downloading audio${details?.strategy ? ` using ${details.strategy}` : ''}...`;
      case 'processing':
        return 'Processing audio file...';
      case 'complete':
        return 'Download complete! Click the download button to save the file.';
      case 'error':
        return task.error || 'An error occurred during download.';
      default:
        return 'Waiting to start download...';
    }
  }

  const formatDate = (dateString: string) => {
    try {
      const date = new Date(dateString);
      return date.toLocaleString();
    } catch (e) {
      return dateString;
    }
  }

  const formatFileSize = (bytes?: number) => {
    if (bytes === undefined) return 'Unknown';
    
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    
    return `${size.toFixed(1)} ${units[unitIndex]}`;
  }

  if (Object.keys(tasks).length === 0) {
    return (
      <DownloadListContainer>
        <div style={{ textAlign: 'center', color: '#666', padding: '2rem' }}>
          No downloads yet
        </div>
      </DownloadListContainer>
    )
  }

  return (
    <DownloadListContainer>
      {Object.entries(tasks).map(([id, task]) => {
        const details = taskDetails[id];
        
        return (
          <DownloadItem key={id}>
            <TaskTitle>{task.title || task.url}</TaskTitle>
            {task.title && <TaskSubtitle>{task.url}</TaskSubtitle>}
            <ProgressBar $progress={task.progress} />
            <TaskActions>
              <StatusBadge $status={task.status}>
                {task.status}
              </StatusBadge>
              <div>
                <span style={{ marginRight: '1rem' }}>{task.progress.toFixed(1)}%</span>
                {task.status === 'complete' && (
                  <DownloadButton onClick={() => handleDownload(id)}>
                    Download
                  </DownloadButton>
                )}
              </div>
            </TaskActions>
            
            <StatusMessage>
              {getStatusDetails(task, details)}
              <ExpandButton onClick={() => toggleTaskExpanded(id)}>
                {expandedTasks[id] ? 'Hide Details' : 'Show Details'}
              </ExpandButton>
            </StatusMessage>
            
            {expandedTasks[id] && (
              <DetailPanel>
                <DetailItem>
                  <DetailLabel>Task ID:</DetailLabel>
                  <DetailValue>{id}</DetailValue>
                </DetailItem>
                {task.author && (
                  <DetailItem>
                    <DetailLabel>Author:</DetailLabel>
                    <DetailValue>{task.author}</DetailValue>
                  </DetailItem>
                )}
                <DetailItem>
                  <DetailLabel>Created:</DetailLabel>
                  <DetailValue>{formatDate(task.createdAt)}</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Updated:</DetailLabel>
                  <DetailValue>{formatDate(task.updatedAt)}</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Format:</DetailLabel>
                  <DetailValue>{task.format.toUpperCase()} ({task.quality})</DetailValue>
                </DetailItem>
                {details?.strategy && (
                  <DetailItem>
                    <DetailLabel>Strategy:</DetailLabel>
                    <DetailValue>{details.strategy}</DetailValue>
                  </DetailItem>
                )}
                {details?.fileInfo && (
                  <>
                    <DetailItem>
                      <DetailLabel>File Size:</DetailLabel>
                      <DetailValue>{formatFileSize(details.fileInfo.size)}</DetailValue>
                    </DetailItem>
                    {details.fileInfo.type && (
                      <DetailItem>
                        <DetailLabel>File Type:</DetailLabel>
                        <DetailValue>{details.fileInfo.type}</DetailValue>
                      </DetailItem>
                    )}
                  </>
                )}
                {task.output_path && (
                  <DetailItem>
                    <DetailLabel>Output Path:</DetailLabel>
                    <DetailValue>{task.output_path}</DetailValue>
                  </DetailItem>
                )}
                {task.error && (
                  <DetailItem>
                    <DetailLabel>Error:</DetailLabel>
                    <DetailValue>{task.error}</DetailValue>
                  </DetailItem>
                )}
              </DetailPanel>
            )}
            
            {task.error && !expandedTasks[id] && (
              <ErrorMessage>
                {task.error}
              </ErrorMessage>
            )}
          </DownloadItem>
        );
      })}
    </DownloadListContainer>
  )
} 