import { createGlobalStyle } from 'styled-components'
import { Theme } from '.'

export const GlobalStyle = createGlobalStyle<{ theme: Theme }>`
  *, *::before, *::after {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
  }

  html {
    font-size: 16px;
  }

  body {
    font-family: ${({ theme }) => theme.typography.fontFamily};
    background-color: ${({ theme }) => theme.colors.background};
    color: ${({ theme }) => theme.colors.text};
    line-height: ${({ theme }) => theme.typography.body.lineHeight};
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }

  h1, h2, h3, h4, h5, h6 {
    margin: 0;
    font-weight: 700;
  }

  h1 {
    font-size: ${({ theme }) => theme.typography.h1.fontSize};
    line-height: ${({ theme }) => theme.typography.h1.lineHeight};
    margin-bottom: ${({ theme }) => theme.spacing.lg};
  }

  h2 {
    font-size: ${({ theme }) => theme.typography.h2.fontSize};
    line-height: ${({ theme }) => theme.typography.h2.lineHeight};
    margin-bottom: ${({ theme }) => theme.spacing.md};
  }

  p {
    margin-bottom: ${({ theme }) => theme.spacing.md};
  }

  button {
    font-family: inherit;
    border: none;
    cursor: pointer;
    background: none;
    color: inherit;

    &:disabled {
      cursor: not-allowed;
      opacity: 0.6;
    }
  }

  input, textarea {
    font-family: inherit;
    border: none;
    outline: none;
  }

  a {
    color: ${({ theme }) => theme.colors.primary};
    text-decoration: none;
    transition: color ${({ theme }) => theme.transitions.fast};

    &:hover {
      color: ${({ theme }) => theme.colors.text};
    }
  }

  /* For WebKit browsers (Chrome, Safari) */
  ::-webkit-scrollbar {
    width: 8px;
    height: 8px;
  }

  ::-webkit-scrollbar-track {
    background: ${({ theme }) => theme.colors.background};
  }

  ::-webkit-scrollbar-thumb {
    background: ${({ theme }) => theme.colors.border};
    border-radius: ${({ theme }) => theme.borderRadius.pill};

    &:hover {
      background: ${({ theme }) => theme.colors.textSecondary};
    }
  }
` 