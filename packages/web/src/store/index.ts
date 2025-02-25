import { configureStore } from '@reduxjs/toolkit'
import downloadsReducer, { DownloadsState } from './downloads'

export interface RootState {
  downloads: DownloadsState
}

export const store = configureStore({
  reducer: {
    downloads: downloadsReducer
  }
})

export type AppDispatch = typeof store.dispatch 