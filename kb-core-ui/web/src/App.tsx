import { useCallback, useEffect, useState } from "react"
import { Outlet } from "react-router-dom"
import { FileTree } from "./components/FileTree/FileTree"
import { Header } from "./components/Header/Header"
import { CommandPalette } from "./components/Search/CommandPalette"
import "./App.css"

function App() {
  const [searchOpen, setSearchOpen] = useState(false)

  const openSearch = useCallback(() => setSearchOpen(true), [])
  const closeSearch = useCallback(() => setSearchOpen(false), [])

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setSearchOpen((open) => !open)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [])

  return (
    <div className="app-shell">
      <Header onOpenSearch={openSearch} />
      <div className="app-body">
        <aside className="app-sidebar">
          <FileTree />
        </aside>
        <main className="app-main scroll-y">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={searchOpen} onClose={closeSearch} />
    </div>
  )
}

export default App
