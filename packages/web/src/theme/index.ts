export const darkTheme = {
  colors: {
    primary: '#1DB954', // Spotify green
    background: '#121212',
    surface: '#282828',
    text: '#FFFFFF',
    textSecondary: '#B3B3B3',
    error: '#FF4B4B',
    success: '#1ED760',
    border: '#404040'
  },
  spacing: {
    xs: '4px',
    sm: '8px',
    md: '16px',
    lg: '24px',
    xl: '32px'
  },
  borderRadius: {
    sm: '4px',
    md: '8px',
    lg: '16px',
    pill: '9999px'
  },
  typography: {
    fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif",
    h1: {
      fontSize: '2.5rem',
      fontWeight: 700,
      lineHeight: 1.2
    },
    h2: {
      fontSize: '2rem',
      fontWeight: 600,
      lineHeight: 1.25
    },
    body: {
      fontSize: '1rem',
      fontWeight: 400,
      lineHeight: 1.5
    },
    small: {
      fontSize: '0.875rem',
      fontWeight: 400,
      lineHeight: 1.5
    }
  },
  transitions: {
    fast: '150ms ease',
    normal: '250ms ease',
    slow: '350ms ease'
  },
  shadows: {
    sm: '0 1px 2px rgba(0, 0, 0, 0.05)',
    md: '0 4px 6px rgba(0, 0, 0, 0.1)',
    lg: '0 10px 15px rgba(0, 0, 0, 0.1)'
  }
} as const

export type Theme = typeof darkTheme 