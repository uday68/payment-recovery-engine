import { configureStore } from '@reduxjs/toolkit';
import { auditApi } from './auditApi';

export const store = configureStore({
  reducer: {
    [auditApi.reducerPath]: auditApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware().concat(auditApi.middleware),
});

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
