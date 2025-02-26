import { useState, FormEvent } from 'react'
import styled from 'styled-components'
import { startDownload, AudioQuality, DownloadFormat } from '../store/downloads'
import { useAppDispatch } from '../hooks/useAppDispatch'
import { Card, Input, Select, Button, ErrorMessage } from './styled'

const FormContainer = styled(Card)`
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.md};
`

const FormRow = styled.div`
  display: flex;
  gap: ${({ theme }) => theme.spacing.md};

  @media (max-width: 600px) {
    flex-direction: column;
  }
`

const SelectContainer = styled.div`
  flex: 1;
`

export const DownloadForm = () => {
  const dispatch = useAppDispatch()
  const [url, setUrl] = useState('')
  const [format, setFormat] = useState<DownloadFormat>('mp3')
  const [quality, setQuality] = useState<AudioQuality>('HIGH')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError(null)
    console.log('Form submission started', { url, format, quality })

    if (!url.trim()) {
      setError('Please enter a URL')
      console.log('URL validation failed: empty URL')
      return
    }

    try {
      setIsSubmitting(true)
      console.log('Starting download process with dispatch', { url, format, quality })
      const result = await dispatch(startDownload({ url, format, quality }))
      console.log('Download dispatch result:', result)
      setUrl('')
    } catch (err) {
      console.error('Error during download submission:', err)
      setError(err instanceof Error ? err.message : 'Failed to start download')
    } finally {
      setIsSubmitting(false)
      console.log('Form submission completed')
    }
  }

  return (
    <FormContainer as="form" onSubmit={handleSubmit}>
      <Input
        type="url"
        value={url}
        onChange={(e) => setUrl(e.target.value)}
        placeholder="Enter YouTube or Spotify playlist URL"
        disabled={isSubmitting}
      />
      
      <FormRow>
        <SelectContainer>
          <Select
            value={format}
            onChange={(e) => setFormat(e.target.value as DownloadFormat)}
            disabled={isSubmitting}
          >
            <option value="mp3">MP3</option>
            <option value="m4a">M4A</option>
          </Select>
        </SelectContainer>

        <SelectContainer>
          <Select
            value={quality}
            onChange={(e) => setQuality(e.target.value as AudioQuality)}
            disabled={isSubmitting}
          >
            <option value="HIGH">320 kbps</option>
            <option value="MEDIUM">192 kbps</option>
            <option value="LOW">128 kbps</option>
          </Select>
        </SelectContainer>

        <Button type="submit" disabled={isSubmitting}>
          {isSubmitting ? 'Starting...' : 'Start Download'}
        </Button>
      </FormRow>

      {error && <ErrorMessage>{error}</ErrorMessage>}
    </FormContainer>
  )
} 