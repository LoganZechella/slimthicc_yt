import { Provider } from 'react-redux'
import { ThemeProvider } from 'styled-components'
import { store } from './store'
import { darkTheme } from './theme'
import { GlobalStyle } from './theme/globalStyle'
import { DownloadForm } from './components/DownloadForm'
import { DownloadList } from './components/DownloadList'
import { AppContainer, MainContent } from './components/styled'

function App() {
  return (
    <Provider store={store}>
      <ThemeProvider theme={darkTheme}>
        <GlobalStyle />
        <AppContainer>
          <MainContent>
            <h1>SlimThicc Music Downloader</h1>
            <DownloadForm />
            <DownloadList />
          </MainContent>
        </AppContainer>
      </ThemeProvider>
    </Provider>
  )
}

export default App
