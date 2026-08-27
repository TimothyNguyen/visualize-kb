import { Link } from "react-router-dom"
import "./HomeView.css"

export function HomeView() {
  return (
    <div className="home-view">
      <h1>KB Core UI</h1>
      <p>Interactive explorer for KB Core knowledge graphs.</p>
      <p className="home-hint">
        Pick a file from the tree on the left, press <kbd>⌘K</kbd> to search for a symbol, or open the{" "}
        <Link to="/graph">full call graph</Link>.
      </p>
    </div>
  )
}
