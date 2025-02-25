import styled from 'styled-components'

export const AppContainer = styled.div`
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: ${({ theme }) => theme.spacing.xl};
`

export const MainContent = styled.main`
  width: 100%;
  max-width: 800px;
  display: flex;
  flex-direction: column;
  gap: ${({ theme }) => theme.spacing.lg};
`

export const Card = styled.div`
  background-color: ${({ theme }) => theme.colors.surface};
  border-radius: ${({ theme }) => theme.borderRadius.md};
  padding: ${({ theme }) => theme.spacing.lg};
  box-shadow: ${({ theme }) => theme.shadows.md};
`

export const Button = styled.button<{ variant?: 'primary' | 'secondary' }>`
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: ${({ theme }) => `${theme.spacing.sm} ${theme.spacing.lg}`};
  border-radius: ${({ theme }) => theme.borderRadius.pill};
  font-weight: 600;
  transition: all ${({ theme }) => theme.transitions.fast};
  background-color: ${({ theme, variant = 'primary' }) =>
    variant === 'primary' ? theme.colors.primary : theme.colors.surface};
  color: ${({ theme, variant = 'primary' }) =>
    variant === 'primary' ? theme.colors.text : theme.colors.textSecondary};

  &:hover:not(:disabled) {
    transform: translateY(-1px);
    background-color: ${({ theme, variant = 'primary' }) =>
      variant === 'primary' ? theme.colors.success : theme.colors.border};
  }

  &:active:not(:disabled) {
    transform: translateY(0);
  }
`

export const Input = styled.input`
  width: 100%;
  padding: ${({ theme }) => theme.spacing.md};
  background-color: ${({ theme }) => theme.colors.surface};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.md};
  color: ${({ theme }) => theme.colors.text};
  transition: border-color ${({ theme }) => theme.transitions.fast};

  &:focus {
    border-color: ${({ theme }) => theme.colors.primary};
  }

  &::placeholder {
    color: ${({ theme }) => theme.colors.textSecondary};
  }
`

export const Select = styled.select`
  width: 100%;
  padding: ${({ theme }) => theme.spacing.md};
  background-color: ${({ theme }) => theme.colors.surface};
  border: 1px solid ${({ theme }) => theme.colors.border};
  border-radius: ${({ theme }) => theme.borderRadius.md};
  color: ${({ theme }) => theme.colors.text};
  transition: border-color ${({ theme }) => theme.transitions.fast};
  cursor: pointer;

  &:focus {
    border-color: ${({ theme }) => theme.colors.primary};
  }

  option {
    background-color: ${({ theme }) => theme.colors.surface};
    color: ${({ theme }) => theme.colors.text};
  }
`

export const ProgressBar = styled.div<{ progress: number }>`
  width: 100%;
  height: 8px;
  background-color: ${({ theme }) => theme.colors.surface};
  border-radius: ${({ theme }) => theme.borderRadius.pill};
  overflow: hidden;
  position: relative;

  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    height: 100%;
    width: ${({ progress }) => `${progress}%`};
    background-color: ${({ theme }) => theme.colors.primary};
    transition: width ${({ theme }) => theme.transitions.normal};
  }
`

export const ErrorMessage = styled.p`
  color: ${({ theme }) => theme.colors.error};
  font-size: ${({ theme }) => theme.typography.small.fontSize};
  margin-top: ${({ theme }) => theme.spacing.xs};
`

export const SuccessMessage = styled.p`
  color: ${({ theme }) => theme.colors.success};
  font-size: ${({ theme }) => theme.typography.small.fontSize};
  margin-top: ${({ theme }) => theme.spacing.xs};
` 