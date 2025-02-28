import React, { useEffect } from 'react'
import styled from 'styled-components'
import { useSelector, useDispatch } from 'react-redux'
import { RootState } from '../store'
import { taskUpdated, DownloadTask } from '../store/downloads'
import websocketService from '../services/websocket'
import { ENDPOINTS, downloadFile } from '../services/api'

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
    transition: width 0.5s ease, background-color 0.3s ease;
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

const SuccessMessage = styled.div`
  color: ${props => props.theme.colors.success};
  margin-top: 0.5rem;
  font-size: 0.875rem;
  padding: 0.5rem;
  background: ${props => props.theme.colors.successBg || 'rgba(25, 135, 84, 0.1)'};
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

const ConnectionStatusBadge = styled.span<{ $status?: 'connecting' | 'connected' | 'disconnected' }>`
  padding: 0.25rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  margin-left: 0.5rem;
  background: ${props => {
    switch (props.$status) {
      case 'connected':
        return props.theme.colors.success + '33'; // Add transparency
      case 'connecting':
        return props.theme.colors.warning + '33';
      case 'disconnected':
        return props.theme.colors.error + '33';
      default:
        return props.theme.colors.background;
    }
  }};
  color: ${props => {
    switch (props.$status) {
      case 'connected':
        return props.theme.colors.success;
      case 'connecting':
        return props.theme.colors.warning;
      case 'disconnected':
        return props.theme.colors.error;
      default:
        return props.theme.colors.textSecondary;
    }
  }};
  border: 1px solid ${props => {
    switch (props.$status) {
      case 'connected':
        return props.theme.colors.success;
      case 'connecting':
        return props.theme.colors.warning;
      case 'disconnected':
        return props.theme.colors.error;
      default:
        return props.theme.colors.border;
    }
  }};
`

const RetryButton = styled.button`
  background: ${props => props.theme.colors.warning};
  color: white;
  border: none;
  border-radius: 4px;
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
  cursor: pointer;
  transition: opacity 0.2s;
  margin-top: 0.5rem;

  &:hover {
    opacity: 0.9;
  }
`

const DetailMessage = styled.div`
  color: ${props => props.theme.colors.textSecondary};
  margin-top: 0.5rem;
  font-size: 0.875rem;
  padding: 0.5rem;
  background: ${props => props.theme.colors.backgroundAlt};
  border-radius: 4px;
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
  
  // Use a ref to keep track of current tasks without triggering effect re-execution
  const tasksRef = React.useRef(tasks);
  
  // Update ref whenever tasks change
  React.useEffect(() => {
    tasksRef.current = tasks;
  }, [tasks]);

  useEffect(() => {
    // Store active subscriptions to clean up later
    const activeTaskIds = Object.keys(tasksRef.current);
    console.log('Setting up WebSocket connections for tasks:', activeTaskIds);
    
    // First cleanup existing connections to prevent duplicates
    activeTaskIds.forEach(taskId => {
      if (websocketService.isSubscribed(taskId)) {
        console.log(`Unsubscribing from task ${taskId} to prevent duplicates`);
        websocketService.unsubscribeFromTask(taskId);
      }
    });
    
    // Create subscriptions for all tasks in the Redux store
    activeTaskIds.forEach(taskId => {
      console.log(`Setting up WebSocket subscription for task ${taskId}`);
      
      const handleTaskUpdate = (data: any) => {
        if (!data) return;
        
        console.log(`WebSocket update for task ${taskId}:`, data);
        
        const taskUpdateData: any = {
          id: taskId,
          updatedAt: new Date().toISOString()
        };
        
        // Extract progress information (ensure progress is always a number)
        if (typeof data.progress === 'number') {
          taskUpdateData.progress = data.progress;
        } else if (typeof data.progress === 'string') {
          // Parse string to number if needed
          taskUpdateData.progress = parseFloat(data.progress) || 0;
        }
        
        // Extract status information if present
        if (data.status) {
          taskUpdateData.status = data.status;
        }
        
        // Extract detailed information if available
        if (data.details) {
          // Store details in local state
          setTaskDetails(prev => {
            const currentDetails = prev[taskId] || {};
            const newDetails = {
              ...currentDetails,
              ...data.details
            };
            
            // Log detailed status updates for debugging
            if (data.details.statusMessage && data.details.statusMessage !== currentDetails.statusMessage) {
              console.log(`Status message updated for task ${taskId}: ${data.details.statusMessage}`);
            }
            
            return {
              ...prev,
              [taskId]: newDetails
            };
          });
        }
        
        // Handle errors
        if (data.error) {
          // Make error messages more user-friendly
          let userFriendlyError = data.error;
          
          // Replace technical error messages with user-friendly ones
          if (data.error.includes("Download completed but tracks saved in /app/downloads")) {
            userFriendlyError = "Your playlist has been downloaded successfully! Click the Download button to get your tracks.";
          } else if (data.error.includes("File not found")) {
            userFriendlyError = "We couldn't find the downloaded file. Please try downloading again.";
          } else if (data.error.includes("Download failed")) {
            userFriendlyError = "Download failed. Please check the URL and try again.";
          }
          
          taskUpdateData.error = userFriendlyError;
        }
        
        // Dispatch the update to Redux
        dispatch(taskUpdated(taskUpdateData));
      };
      
      const handleConnectionStatus = (status: string) => {
        console.log(`WebSocket connection status for task ${taskId}: ${status}`);
        dispatch(taskUpdated({
          id: taskId,
          connectionStatus: status as any,
          updatedAt: new Date().toISOString()
        }));
      };
      
      websocketService.subscribeToTask(taskId, handleTaskUpdate, handleConnectionStatus)
        .catch(error => {
          console.error(`Error setting up WebSocket for task ${taskId}:`, error);
          
          // Update Redux with connection error
          dispatch(taskUpdated({
            id: taskId,
            connectionStatus: 'disconnected',
            updatedAt: new Date().toISOString()
          }));
        });
    });
    
    // Cleanup subscriptions when component unmounts
    return () => {
      activeTaskIds.forEach(taskId => {
        console.log(`Cleaning up WebSocket subscription for task ${taskId}`);
        websocketService.unsubscribeFromTask(taskId);
      });
    };
  }, [dispatch]);

  // Type guard for TaskStatus
  const isValidTaskStatus = (status: string): status is TaskStatus => {
    return ['queued', 'downloading', 'processing', 'complete', 'error'].includes(status);
  };

  const handleDownload = async (taskId: string) => {
    try {
      console.log(`Initiating download for task ${taskId}`, tasks[taskId]);
      
      // Check if we have the output path from the server
      const task = tasks[taskId];
      
      if (!task) {
        console.error(`Task ${taskId} not found in store`);
        return;
      }

      // Redirect to the download URL
      const downloadUrl = ENDPOINTS.DOWNLOAD_FILE(taskId);
      console.log(`Downloading from URL: ${downloadUrl}`);
      
      // Log additional information to help debug
      console.log(`Task details for download:`, {
        id: task.id,
        status: task.status,
        progress: task.progress,
        output_path: task.output_path
      });

      try {
        // Use our specialized downloadFile function
        const response = await downloadFile(downloadUrl);
        
        // Get filename from Content-Disposition header or use default
        let filename = '';
        const contentDisposition = response.headers.get('Content-Disposition');
        if (contentDisposition) {
          const match = contentDisposition.match(/filename="?([^"]+)"?/);
          if (match && match[1]) {
            filename = match[1];
          }
        }
        
        if (!filename) {
          filename = task.title 
            ? `${task.title}.${task.format}` 
            : `download-${taskId}.${task.format}`;
        }
        
        console.log(`Downloading file with name: ${filename}`);
        
        // Convert response to blob
        const blob = await response.blob();
        
        // Create download link
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        
        // Cleanup
        window.URL.revokeObjectURL(url);
        document.body.removeChild(a);
        
        console.log(`Download completed for ${taskId}`);
      } catch (downloadError) {
        console.error('Download error:', downloadError);
        
        // Fallback to opening in a new tab if direct download fails
        console.log('Falling back to new tab download');
        window.open(downloadUrl, '_blank');
      }
    } catch (error) {
      console.error(`Error downloading task ${taskId}:`, error);
      
      // Update task with error information
      dispatch(taskUpdated({
        id: taskId,
        error: error instanceof Error ? error.message : 'Failed to download file',
        updatedAt: new Date().toISOString()
      }));
    }
  };

  const toggleExpanded = (taskId: string) => {
    setExpandedTasks(prev => ({
      ...prev,
      [taskId]: !prev[taskId]
    }));
  };

  // Function to reconnect a specific task
  const handleReconnect = async (taskId: string) => {
    try {
      console.log(`Attempting to reconnect WebSocket for task ${taskId}`);
      
      // First check if the task still exists
      if (!tasksRef.current[taskId]) {
        console.warn(`Cannot reconnect non-existent task with ID: ${taskId}`);
        return;
      }
      
      // First unsubscribe to clean up any existing connection
      websocketService.unsubscribeFromTask(taskId);
      
      // Create connection status callback
      const connectionStatusCallback = (status: 'connecting' | 'connected' | 'disconnected') => {
        console.log(`Connection status update for task ${taskId}: ${status}`);
        
        // Only dispatch if task still exists
        if (tasksRef.current[taskId]) {
          dispatch(taskUpdated({
            id: taskId,
            connectionStatus: status,
            updatedAt: new Date().toISOString()
          }));
        }
      };
      
      // Set status to connecting
      dispatch(taskUpdated({
        id: taskId,
        connectionStatus: 'connecting',
        updatedAt: new Date().toISOString()
      }));
      
      // Resubscribe to WebSocket updates
      await websocketService.subscribeToTask(taskId, (data: any) => {
        // Skip ping/pong and connection status messages
        if (data.type === 'ping' || data.type === 'pong' || data.type === 'connection_status') {
          return;
        }
        
        console.log(`Received WebSocket data for task ${taskId}:`, data);
        
        // First check if the task still exists in Redux store
        if (!tasksRef.current[taskId]) {
          console.warn(`Received WebSocket data for non-existent task with ID: ${taskId}`);
          return;
        }
        
        // Extract properties from data
        const { progress, status, error, details } = data;
        
        // Create update object with only fields that changed
        const update: Partial<DownloadTask> & { id: string } = { id: taskId };
        
        if (progress !== undefined) {
          update.progress = progress;
        }
        
        if (status && isValidTaskStatus(status)) {
          update.status = status;
        }
        
        if (error) {
          update.error = error;
        }
        
        // Update Redux if we have changes
        if (Object.keys(update).length > 1) { // More than just the ID
          update.updatedAt = new Date().toISOString();
          dispatch(taskUpdated(update));
        }
        
        // Store additional details locally if present
        if (details) {
          setTaskDetails(prev => ({
            ...prev,
            [taskId]: {
              ...prev[taskId],
              ...details
            }
          }));
        }
      }, connectionStatusCallback);
      
      console.log(`Reconnection attempt for task ${taskId} successful`);
    } catch (error) {
      console.error(`Failed to reconnect WebSocket for task ${taskId}:`, error);
      dispatch(taskUpdated({
        id: taskId,
        connectionStatus: 'disconnected',
        updatedAt: new Date().toISOString()
      }));
    }
  };

  if (Object.keys(tasks).length === 0) {
    return (
      <DownloadListContainer>
        <p>No downloads yet. Try downloading a YouTube video or Spotify track!</p>
      </DownloadListContainer>
    );
  }

  return (
    <DownloadListContainer>
      {Object.values(tasks)
        .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
        .map(task => (
          <DownloadItem key={task.id}>
            <TaskTitle>
              {task.title || 'Download in progress...'}
              <ConnectionStatusBadge $status={task.connectionStatus}>
                {task.connectionStatus || 'unknown'}
              </ConnectionStatusBadge>
            </TaskTitle>
            
            <TaskSubtitle>
              {task.author ? `By ${task.author}` : ''}
              {task.format && ` • ${task.format.toUpperCase()}`}
              {task.quality && ` • ${task.quality}`}
            </TaskSubtitle>
            
            <ProgressBar $progress={task.progress} />
            
            <TaskActions>
              <StatusBadge $status={task.status}>
                {task.status.charAt(0).toUpperCase() + task.status.slice(1)}
              </StatusBadge>
              
              {task.status === 'complete' && (
                <DownloadButton 
                  onClick={() => handleDownload(task.id)}
                  disabled={task.connectionStatus === 'disconnected'}
                >
                  Download
                </DownloadButton>
              )}
            </TaskActions>
            
            {/* Display detailed status message if available */}
            {taskDetails[task.id]?.statusMessage && task.status !== 'complete' && task.status !== 'error' && (
              <DetailMessage>
                {taskDetails[task.id].statusMessage}
              </DetailMessage>
            )}
            
            {task.error && task.error.includes("Your playlist has been downloaded successfully") ? (
              <SuccessMessage>
                {task.error}
              </SuccessMessage>
            ) : task.error && (
              <ErrorMessage>
                {task.error}
                {task.connectionStatus === 'disconnected' && (
                  <div>Connection lost. Please reload the page to retry.</div>
                )}
              </ErrorMessage>
            )}
            
            {task.connectionStatus === 'disconnected' && !task.error && (
              <ErrorMessage>
                WebSocket connection lost. Real-time updates unavailable.
                <RetryButton onClick={() => handleReconnect(task.id)}>
                  Reconnect
                </RetryButton>
              </ErrorMessage>
            )}
            
            <ExpandButton onClick={() => toggleExpanded(task.id)}>
              {expandedTasks[task.id] ? 'Hide Details' : 'Show Details'}
            </ExpandButton>
            
            {expandedTasks[task.id] && (
              <DetailPanel>
                <DetailItem>
                  <DetailLabel>URL:</DetailLabel>
                  <DetailValue>{task.url}</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Task ID:</DetailLabel>
                  <DetailValue>{task.id}</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Created:</DetailLabel>
                  <DetailValue>{new Date(task.createdAt).toLocaleString()}</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Updated:</DetailLabel>
                  <DetailValue>{new Date(task.updatedAt).toLocaleString()}</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Status:</DetailLabel>
                  <DetailValue>{task.status}</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Progress:</DetailLabel>
                  <DetailValue>{task.progress}%</DetailValue>
                </DetailItem>
                <DetailItem>
                  <DetailLabel>Connection:</DetailLabel>
                  <DetailValue>{task.connectionStatus || 'unknown'}</DetailValue>
                </DetailItem>
                {taskDetails[task.id]?.strategy && (
                  <DetailItem>
                    <DetailLabel>Strategy:</DetailLabel>
                    <DetailValue>{taskDetails[task.id].strategy}</DetailValue>
                  </DetailItem>
                )}
                {taskDetails[task.id]?.statusMessage && (
                  <DetailItem>
                    <DetailLabel>Status:</DetailLabel>
                    <DetailValue>{taskDetails[task.id].statusMessage}</DetailValue>
                  </DetailItem>
                )}
                {task.output_path && (
                  <DetailItem>
                    <DetailLabel>Output Path:</DetailLabel>
                    <DetailValue>{task.output_path}</DetailValue>
                  </DetailItem>
                )}
              </DetailPanel>
            )}
          </DownloadItem>
        ))}
    </DownloadListContainer>
  );
}; 