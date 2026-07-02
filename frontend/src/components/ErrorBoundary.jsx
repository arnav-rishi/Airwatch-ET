import { Component } from 'react'

export default class ErrorBoundary extends Component {
  state = { hasError: false }

  static getDerivedStateFromError() {
    return { hasError: true }
  }

  componentDidCatch(error, info) {
    console.error('Caught by ErrorBoundary:', error, info)
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="h-screen flex items-center justify-center bg-[#0f1117] text-slate-300">
          <div className="text-center space-y-3">
            <p className="text-lg font-semibold">Something went wrong loading this view.</p>
            <button onClick={() => window.location.reload()}
              className="bg-blue-600 px-4 py-2 rounded-lg text-white text-sm">
              Reload
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
