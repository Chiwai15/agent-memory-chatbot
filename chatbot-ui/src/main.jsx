import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

// Temporarily disable StrictMode to debug session persistence issues
// StrictMode causes intentional double-mounting in dev, which can trigger useState initializers twice
createRoot(document.getElementById('root')).render(
  <App />
  // <StrictMode>
  //   <App />
  // </StrictMode>,
)
