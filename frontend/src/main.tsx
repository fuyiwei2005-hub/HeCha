import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import App from './App'
import { ErrorBoundary } from './components/ErrorBoundary'
import './styles.css'
import './product.css'
import './brand.css'
import './motion.css'
import './footer.css'
import './navigation.css'
const client = new QueryClient({defaultOptions: {queries: {retry: false, staleTime: 10000, refetchOnWindowFocus: true}, mutations: {retry: false}}})
const basename = location.pathname.startsWith('/experimental') ? '/experimental' : '/'
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode><ErrorBoundary><QueryClientProvider client={client}><BrowserRouter basename={basename}><App/></BrowserRouter></QueryClientProvider></ErrorBoundary></React.StrictMode>,
)
