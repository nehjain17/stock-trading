import React, { useState, useEffect } from 'react'
import './App.css'

function App() {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    // Fetch data from backend
    const fetchData = async () => {
      setLoading(true)
      try {
        const response = await fetch('/api/health')
        const result = await response.json()
        setData(result)
      } catch (error) {
        console.error('Error fetching data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  return (
    <div className="App">
      <header className="App-header">
        <h1>Stock Trading Application</h1>
        <p>Status: {loading ? 'Loading...' : data?.status || 'Not connected'}</p>
      </header>
    </div>
  )
}

export default App
