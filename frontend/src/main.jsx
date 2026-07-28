import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.jsx'
import './index.css'

// Apply the saved theme before first paint to avoid a flash of default colors.
document.documentElement.dataset.theme = localStorage.getItem('mc-theme') ?? 'light'

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
